from PySide6.QtCore import QObject, Signal

class Worker(QObject):
    progress = Signal(int)
    finished = Signal()

    def __init__(self, n):
        super().__init__()
        self.n = n

    def run(self):
        for i in range(self.n):
            self.progress.emit(i)
            self.heavy_task()   # do your expensive work here
        self.finished.emit()

    def heavy_task(self):
        # Your CPU-heavy work
        x = 0
        for _ in range(5_000_000):
            x += 1



from PySide6.QtWidgets import QApplication, QProgressBar, QWidget, QVBoxLayout
from PySide6.QtCore import QThread
import sys

class Window(QWidget):
    def __init__(self):
        super().__init__()

        self.progress = QProgressBar()
        layout = QVBoxLayout(self)
        layout.addWidget(self.progress)

        self.start_worker()

    def start_worker(self):
        self.thread = QThread()
        self.worker = Worker(n=100)

        self.worker.moveToThread(self.thread)
        self.worker.progress.connect(self.progress.setValue)
        self.worker.finished.connect(self.and_finally)

        self.thread.started.connect(self.worker.run)
        self.worker.finished.connect(self.thread.quit)

        self.thread.start()

    def and_finally(self):
        print("All heavy tasks completed!")
        # Put any final actions here
        # UI is responsive the whole time

app = QApplication(sys.argv)
window = Window()
window.show()
app.exec()
