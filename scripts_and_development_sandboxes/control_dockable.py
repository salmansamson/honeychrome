from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QPushButton, QSlider,
    QSpinBox, QHBoxLayout, QVBoxLayout, QDockWidget, QLabel
)
from PySide6.QtCore import Qt


class ControlPanel(QWidget):
    def __init__(self):
        super().__init__()

        layout = QVBoxLayout(self)

        # Regular button
        self.button = QPushButton("Click Me")
        self.button.clicked.connect(lambda: print("Button clicked"))
        layout.addWidget(self.button)

        # Toggle button
        self.toggle_button = QPushButton("Toggle Me")
        self.toggle_button.setCheckable(True)
        self.toggle_button.toggled.connect(
            lambda checked: print(f"Toggle is {'On' if checked else 'Off'}")
        )
        layout.addWidget(self.toggle_button)

        # Slider + SpinBox
        slider_layout = QHBoxLayout()
        self.slider = QSlider(Qt.Horizontal)
        self.slider.setRange(0, 100)
        self.spinbox = QSpinBox()
        self.spinbox.setRange(0, 100)

        # Sync slider and spinbox
        self.slider.valueChanged.connect(self.spinbox.setValue)
        self.spinbox.valueChanged.connect(self.slider.setValue)

        slider_layout.addWidget(QLabel("Value:"))
        slider_layout.addWidget(self.slider)
        slider_layout.addWidget(self.spinbox)
        layout.addLayout(slider_layout)

        layout.addStretch()


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()

        self.setWindowTitle("Dockable Control Panel")
        self.resize(800, 600)

        # Central widget placeholder
        central = QLabel("Main Content Area")
        central.setAlignment(Qt.AlignCenter)
        self.setCentralWidget(central)

        # Create dock widget
        self.dock = QDockWidget("Controls", self)
        self.dock.setAllowedAreas(Qt.LeftDockWidgetArea | Qt.RightDockWidgetArea)

        self.control_panel = ControlPanel()
        self.dock.setWidget(self.control_panel)

        self.addDockWidget(Qt.RightDockWidgetArea, self.dock)


if __name__ == "__main__":
    import sys

    app = QApplication(sys.argv)
    win = MainWindow()
    win.show()
    sys.exit(app.exec())
