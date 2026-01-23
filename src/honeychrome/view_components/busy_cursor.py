import sys
import time

from PySide6.QtWidgets import QApplication, QWidget, QPushButton, QVBoxLayout, QLabel
from PySide6.QtCore import Qt, QRunnable, QThreadPool

#
# class Runnable(QRunnable):
#     def __init__(self, fn, finished_callback):
#         super().__init__()
#         self.fn = fn
#         self.finished_callback = finished_callback
#
#     def run(self):
#         try:
#             self.fn()
#         finally:
#             self.finished_callback()
#
#
# def with_busy_cursor(func):
#     def wrapper(*args, **kwargs):
#         instance = QApplication.instance()
#         if instance is None:
#             return func(*args, **kwargs)
#
#         QApplication.setOverrideCursor(Qt.WaitCursor)
#
#         def cleanup():
#             QApplication.restoreOverrideCursor()
#
#         runnable = Runnable(lambda: func(*args, **kwargs), cleanup)
#         QThreadPool.globalInstance().start(runnable)
#
#     return wrapper

import functools
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt


def with_busy_cursor(func):
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        app = QApplication.instance()
        if not app:
            return func(*args, **kwargs)

        # Set the spinner
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            return func(*args, **kwargs)
        finally:
            # Restore the cursor
            QApplication.restoreOverrideCursor()
            # Force Windows to repaint the cursor immediately
            app.processEvents()

    return wrapper


if __name__ == "__main__":

    class MainWindow(QWidget):
        def __init__(self):
            super().__init__()
            self.setWindowTitle("BusyCursor Decorator (PySide6-safe)")

            self.label = QLabel("Idle")
            self.button = QPushButton("Start Task")
            self.button.clicked.connect(self.run_task)

            layout = QVBoxLayout(self)
            layout.addWidget(self.label)
            layout.addWidget(self.button)

        @with_busy_cursor
        def long_task(self):
            time.sleep(4)

        def run_task(self):
            self.label.setText("Task running...")
            self.long_task()


    app = QApplication(sys.argv)
    w = MainWindow()
    w.show()
    sys.exit(app.exec())
