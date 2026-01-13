from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QSplitter, QTextEdit, QPushButton,
    QHBoxLayout, QVBoxLayout, QSlider, QCheckBox, QFrame, QMenuBar
)

from PySide6.QtCore import Qt
import sys

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Splitter with Control Panel")
        self.resize(600, 400)

        # --- Main content ---
        self.main_content = QTextEdit("Main content here")

        # --- Control panel ---
        self.control_panel = QFrame()
        self.control_panel.setFrameShape(QFrame.StyledPanel)
        self.control_panel.setMaximumHeight(70)  # fixed height

        # Layout for controls
        control_layout = QHBoxLayout()
        control_layout.setContentsMargins(5, 5, 5, 5)
        control_layout.setSpacing(10)

        # Add some buttons
        for i in range(1, 3):
            btn = QPushButton(f"Button {i}")
            btn.setFixedSize(100, 30)
            control_layout.addWidget(btn)

        # Add a slider
        slider = QSlider(Qt.Horizontal)
        slider.setFixedWidth(150)
        control_layout.addWidget(slider)

        # Add a checkbox
        checkbox = QCheckBox("Enable feature")
        control_layout.addWidget(checkbox)

        self.control_panel.setLayout(control_layout)

        # --- Splitter ---
        self.splitter = QSplitter(Qt.Vertical)
        self.splitter.addWidget(self.main_content)
        self.splitter.addWidget(self.control_panel)
        self.splitter.setSizes([300, 70])  # initial sizes

        # Set splitter as central widget
        container = QWidget()
        layout = QVBoxLayout()
        layout.addWidget(self.splitter)
        container.setLayout(layout)
        self.setCentralWidget(container)

        # --- Menu bar toggle ---
        menu_bar = QMenuBar()
        view_menu = menu_bar.addMenu("View")
        toggle_panel_action = QAction("Show Control Panel", self)
        toggle_panel_action.setCheckable(True)
        toggle_panel_action.setChecked(True)
        toggle_panel_action.triggered.connect(self.toggle_control_panel)
        view_menu.addAction(toggle_panel_action)
        self.setMenuBar(menu_bar)

    def toggle_control_panel(self, checked):
        """Show/hide the bottom control panel in the splitter."""
        self.control_panel.setVisible(checked)
        # Optionally, adjust splitter sizes to keep layout nice
        if checked:
            self.splitter.setSizes([self.height() - 70, 70])
        else:
            self.splitter.setSizes([self.height(), 0])

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
