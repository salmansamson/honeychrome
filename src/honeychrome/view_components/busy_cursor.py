import sys
import time

from PySide6.QtGui import QCursor
from PySide6.QtWidgets import QApplication, QWidget, QPushButton, QVBoxLayout, QLabel
from PySide6.QtCore import Qt, QRunnable, QThreadPool

class Runnable(QRunnable):
    def __init__(self, fn, finished_callback):
        super().__init__()
        self.fn = fn
        self.finished_callback = finished_callback

    def run(self):
        try:
            self.fn()
        finally:
            self.finished_callback()

import functools
from PySide6.QtCore import QThread, QEventLoop, Qt
from PySide6.QtWidgets import QApplication


class WorkerThread(QThread):
    def __init__(self, func, args, kwargs):
        super().__init__()
        self.func = func
        self.args = args
        self.kwargs = kwargs
        self.result = None
        self.error = None

    def run(self):
        try:
            self.result = self.func(*self.args, **self.kwargs)
        except Exception as e:
            self.error = e


def with_busy_cursor(func):
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        app = QApplication.instance()
        if not app:
            return func(*args, **kwargs)

        # 1. Set the wait cursor
        QApplication.setOverrideCursor(Qt.WaitCursor)

        # 2. Create the thread and an event loop
        thread = WorkerThread(func, args, kwargs)
        loop = QEventLoop()

        # 3. Connect thread finish to the loop's quit
        thread.finished.connect(loop.quit)

        try:
            thread.start()
            loop.exec()  # This blocks here but keeps the UI repainting!
        finally:
            # 4. Clean up
            QApplication.restoreOverrideCursor()
            current_pos = QCursor.pos()
            QCursor.setPos(current_pos)
            app.processEvents()  # Force Windows to update cursor icon

        if thread.error:
            raise thread.error
        return thread.result

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
