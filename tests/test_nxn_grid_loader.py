from PySide6.QtWidgets import QMainWindow, QWidget, QHBoxLayout, QSplitter, QTabWidget, QVBoxLayout, QScrollArea, \
    QLabel, QFrame
from PySide6.QtCore import Qt


from view_components.nxn_grid import NxNGrid


if __name__ == "__main__":
    import sys
    from PySide6.QtWidgets import QApplication
    from controller import Controller
    from pathlib import Path
    from view_components.event_bus import EventBus

    app =  QApplication(sys.argv)

    kc = Controller()
    base_directory = Path.home() / 'spectral_cytometry'
    experiment_name = base_directory / '20240620 Spectral Symposium-poor cell unmixed'
    experiment_path = experiment_name.with_suffix('.kit')
    kc.load_experiment(experiment_path) # note this loads first sample too and runs calculate all histograms and statistics
    bus = EventBus()


    kc.set_mode('Spectral Process')
    kc.load_sample(kc.experiment.samples['single_stain_controls'][0])

    frame = NxNGrid(bus, kc)
    frame.show()


    exit_code = app.exec()
    sys.exit(exit_code)
