'''
Honeychrome - open source cytometry data acquisition and analysis software
'''
# from honeychrome.tools import DepthFinder # debug module imports here
import honeychrome.dummy_loader

import os
import sys
from pathlib import Path

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication
import multiprocessing as mp
from multiprocessing import shared_memory, Lock
import numpy as np

from honeychrome.settings import experiments_folder

'''
Instrument Communicator:
-Connects to instrument
-Configures instrument
-Listens for start event
-Listens for stop event
'''
from honeychrome.instrument_driver import Instrument

'''
Trace Analyser:
-Listens for start event
-Consumes cached traces
-Calculates peak height, area, width (according to settings) and adds to events cache 
-Copies latest trace with peak measurements
-Signals when new events chunk is ready
'''
from honeychrome.trace_analyst import TraceAnalyser


'''
Controller:
-Initialises Experiment Model
-Creates new experiment
-Loads saved experiment
-Loads sample
-Creates live sample and carries out live analysis
-Sends and receives signals to GUI
'''
from honeychrome.controller import Controller

'''
View:
-Creates GUI widgets
-Serves and updates data from controller
--sample list
--settings
--plots
--histograms
--gates
--spectral model
--instrument control
--oscilloscope
'''
from honeychrome.view import View, logo_icon

import logging
import warnings


class StreamToLogger(object):
    """Redirect a stream (stdout/stderr) to a logger."""
    def __init__(self, logger, level):
        self.logger = logger
        self.level = level
        self.buffer = ""

    def write(self, message):
        if message.rstrip():
            self.logger.log(self.level, message.rstrip())

    def flush(self):
        pass


def setup_logging(log_file):
    """Set up logging to both console and file, and capture all output."""

    # Create logger
    logger = logging.getLogger()
    # logger = logging.getLogger(__name__)  # Only logs from this file
    logging.getLogger('matplotlib').setLevel(logging.WARNING)
    logger.setLevel(logging.DEBUG)
    logger.handlers.clear()

    # Formatter
    formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')

    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(formatter)

    # File handler
    file_handler = logging.FileHandler(log_file, mode='a', encoding='utf-8')
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(formatter)

    # Add handlers
    logger.addHandler(console_handler)
    logger.addHandler(file_handler)

    # Redirect stdout and stderr
    sys.stdout = StreamToLogger(logger, logging.INFO)
    sys.stderr = StreamToLogger(logger, logging.ERROR)

    # Redirect warnings module to logging
    logging.captureWarnings(True)
    warnings.simplefilter("default")  # ensure warnings fire

    # Capture uncaught exceptions
    def handle_exception(exc_type, exc_value, exc_traceback):
        logger.error("Uncaught exception",
                     exc_info=(exc_type, exc_value, exc_traceback))
    sys.excepthook = handle_exception

    return logger


def main():
    # Usage
    (Path.home() / experiments_folder).mkdir(parents=True, exist_ok=True)
    logger = setup_logging(Path.home() / experiments_folder / 'honeychrome.log')

    # # Log messages at different levels
    # logger.debug("Debug message")  # Only to file
    # logger.info("Info message")  # To both console and file
    # logger.warning("Warning message")
    # logger.error("Error message")

    '''
    define objects for communication between processes
    '''
    from honeychrome.instrument_configuration import traces_cache_size, dtype, max_events_in_traces_cache, trace_n_points, n_channels_trace, adc_rate
    from honeychrome.settings import max_events_in_cache, n_channels_per_event, channel_dict, event_channels_pnn
    import honeychrome.settings as settings

    # Allocate shared memory block, plus head and tail indices
    traces_cache_shm = shared_memory.SharedMemory(create=True, size=np.zeros(traces_cache_size, dtype=dtype).nbytes)
    traces_cache_lock = Lock()
    index_head_traces_cache = mp.Value('i', 0)
    index_tail_traces_cache = mp.Value('i', 0)

    events_cache_shm = shared_memory.SharedMemory(create=True,
                                                  size=np.zeros((max_events_in_cache, n_channels_per_event),
                                                                dtype=np.int_).nbytes)
    events_cache_lock = Lock()
    index_head_events_cache = mp.Value('i', 0)
    index_tail_events_cache = mp.Value('i', 0)

    # oscilloscope traces
    oscilloscope_traces_queue = mp.Queue()
    # command pipes
    pipe_experiment_instrument_e, pipe_experiment_instrument_i = mp.Pipe()
    pipe_experiment_analyser_e, pipe_experiment_analyser_a = mp.Pipe()

    '''
    start instrument driver
    '''
    instrument = Instrument(
        use_dummy_instrument=settings.use_dummy_instrument_retrieved,
        traces_cache_name=traces_cache_shm.name,
        traces_cache_lock=traces_cache_lock,
        index_head_traces_cache=index_head_traces_cache,
        index_tail_traces_cache=index_tail_traces_cache,
        pipe_connection=pipe_experiment_instrument_i
    )
    instrument.start()

    '''
    start trace analyser
    '''
    trace_analyser = TraceAnalyser(
        traces_cache_name=traces_cache_shm.name,
        traces_cache_lock=traces_cache_lock,
        index_head_traces_cache=index_head_traces_cache,
        index_tail_traces_cache=index_tail_traces_cache,
        events_cache_name=events_cache_shm.name,
        events_cache_lock=events_cache_lock,
        index_head_events_cache=index_head_events_cache,
        index_tail_events_cache=index_tail_events_cache,
        oscilloscope_traces_queue=oscilloscope_traces_queue,
        pipe_connection=pipe_experiment_analyser_a
    )
    trace_analyser.start()

    '''
    start controller
    '''
    controller = Controller(
            events_cache_name=events_cache_shm.name,
            events_cache_lock=events_cache_lock,
            index_head_events_cache=index_head_events_cache,
            index_tail_events_cache=index_tail_events_cache,
            oscilloscope_traces_queue=oscilloscope_traces_queue,
            pipe_connection_instrument=pipe_experiment_instrument_e,
            pipe_connection_analyser=pipe_experiment_analyser_e)

    '''
    start application and view
    '''
    app = QApplication(sys.argv)

    if sys.platform == 'win32':
        import ctypes
        myappid = 'honeychrome.cytometry.v0.6.0'
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(myappid)

    # Use Fusion style (works consistently across platforms)
    app.setStyle("Fusion")
    # Ensure consistent rounding of fractional scaling factors
    os.environ["QT_SCALE_FACTOR_ROUNDING_POLICY"] = "PassThrough"

    # app.setWindowIcon(QIcon(str(Path(__file__).resolve().parent / 'view_components' / 'assets' / 'cytkit_web_logo.ico')))
    app.setWindowIcon(QIcon(logo_icon))
    app.setDesktopFileName("honeychrome")

    # # debug space usage by highlighting
    # app.setStyleSheet("""
    #     QMainWindow {
    #         background-color: Maroon;
    #     }
    #     QWidget {
    #             /* This background covers the Padding and Content area */
    #             background-color: Indigo;
    #     }
    #     QWidget {
    #         border: 1px solid green;
    #     }
    #     QFrame, QGroupBox {
    #         background-color: Goldenrod;
    #         border: 1px solid blue;
    #     }
    #     QScrollBar {
    #         background: DarkOliveGreen; border: 1px solid red;
    #     }
    # """)

    view = View(
        controller=controller
    )
    controller.bus = view.bus # connect signals coming from controller

    '''
    start QT application
    '''
    print('***** Started Honeychrome *****')
    exit_code = app.exec()

    # end processes, free memory
    print('***** Quitting Honeychrome *****')
    controller.quit_instrument_quit_analyser()
    trace_analyser.join()
    instrument.join()
    traces_cache_shm.close()
    events_cache_shm.close()
    traces_cache_shm.unlink()
    events_cache_shm.unlink()

    sys.exit(exit_code)

if __name__ == '__main__':
    if getattr(sys, 'frozen', False):
        # Running as PyInstaller executable
        import multiprocessing
        multiprocessing.freeze_support()  # Required for Windows
        # On Unix systems, also need:
        if os.name == 'posix':
            import multiprocessing
            multiprocessing.set_start_method('spawn', force=True)

    main()