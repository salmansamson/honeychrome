import sys
from PySide6.QtWidgets import (QApplication, QMainWindow, QStatusBar, QProgressBar, QPushButton, QVBoxLayout, QWidget)
from PySide6.QtCore import QTimer


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("StatusBar with Maximum Width Progress Bar")
        self.setGeometry(100, 100, 600, 400)

        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        layout = QVBoxLayout()
        central_widget.setLayout(layout)

        self.demo_button = QPushButton("Start Demo")
        self.demo_button.clicked.connect(self.start_demo)
        layout.addWidget(self.demo_button)

        self.setup_statusbar()

    def setup_statusbar(self):
        status_bar = QStatusBar()
        self.setStatusBar(status_bar)

        # Create progress bar with maximum width
        self.progress_bar = QProgressBar()
        self.progress_bar.setMaximumWidth(250)  # Maximum width
        self.progress_bar.setMinimum(0)
        self.progress_bar.setMaximum(100)
        self.progress_bar.setValue(50)
        self.progress_bar.setVisible(True)

        status_bar.addPermanentWidget(self.progress_bar)

    def start_demo(self):
        self.statusBar().showMessage("Processing started...")
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)

        self.progress_value = 0
        self.timer = QTimer()
        self.timer.timeout.connect(self.update_progress)
        self.timer.start(100)

    def update_progress(self):
        self.progress_value += 2
        self.progress_bar.setValue(self.progress_value)
        self.statusBar().showMessage(f"Processing... {self.progress_value}% complete")

        if self.progress_value >= 100:
            self.timer.stop()
            self.statusBar().showMessage("Processing completed!", 3000)
            QTimer.singleShot(3000, lambda: self.progress_bar.setVisible(False))


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())