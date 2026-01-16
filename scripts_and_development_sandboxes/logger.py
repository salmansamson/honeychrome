import logging
import sys
import warnings
from io import StringIO
from pathlib import Path


class StreamToLogger:
    """Redirect stream to logger"""

    def __init__(self, logger, log_level=logging.INFO):
        self.logger = logger
        self.log_level = log_level
        self.linebuf = ''

    def write(self, buf):
        for line in buf.rstrip().splitlines():
            if line.rstrip():
                self.logger.log(self.log_level, line.rstrip())

    def flush(self):
        pass

    def isatty(self):
        return False


def setup_logging(log_file):
    """Set up logging to both console and file, capturing all outputs"""

    # Create logger
    logger = logging.getLogger()
    logger.setLevel(logging.DEBUG)

    # Remove existing handlers to avoid duplicates
    logger.handlers.clear()

    # Create formatter
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')

    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(formatter)

    # File handler
    file_handler = logging.FileHandler(log_file, mode='w')
    file_handler.setLevel(logging.DEBUG)  # Log everything to file
    file_handler.setFormatter(formatter)

    # Add handlers
    logger.addHandler(console_handler)
    logger.addHandler(file_handler)

    # 1. Redirect stdout and stderr to logger
    sys.stdout = StreamToLogger(logger, logging.INFO)
    sys.stderr = StreamToLogger(logger, logging.ERROR)

    # 2. Override print() function
    original_print = __builtins__.print

    def custom_print(*args, **kwargs):
        # Create a string from the print arguments
        output = ' '.join(str(arg) for arg in args)
        # Log the output
        logger.info(f"Print: {output}")
        # Also call original print if needed
        if kwargs.get('file', None) is None:  # Only intercept default stdout prints
            original_print(*args, **kwargs)

    __builtins__.print = custom_print

    # 3. Capture warnings
    def warning_to_log(message, category, filename, lineno, file=None, line=None):
        logger.warning(f"Warning: {category.__name__}: {message} (at {filename}:{lineno})")

    warnings.showwarning = warning_to_log
    logging.captureWarnings(True)  # This captures warnings module warnings

    # Set warnings to always show
    warnings.simplefilter('always')

    # 4. Capture uncaught exceptions
    def handle_exception(exc_type, exc_value, exc_traceback):
        logger.error("Uncaught exception", exc_info=(exc_type, exc_value, exc_traceback))

    sys.excepthook = handle_exception

    # 5. Capture all logging from third-party libraries
    logging.getLogger('').handlers = logger.handlers
    logging.getLogger('').setLevel(logging.DEBUG)

    return logger


# Usage
logger = setup_logging('honeychrome.log')

# Test the setup
if __name__ == "__main__":
    print("This print statement will be logged!")
    print("Another print statement")

    # Generate a warning
    warnings.warn("This is a test warning")

    # Generate an error to stderr
    import traceback

    try:
        raise ValueError("Test exception")
    except:
        traceback.print_exc()

    # Test logger directly
    logger.info("Direct logger message")
    logger.warning("Direct warning message")
    logger.error("Direct error message")