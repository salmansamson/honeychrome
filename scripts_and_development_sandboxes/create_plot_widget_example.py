from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QComboBox, QPushButton
)
from PySide6.QtCore import Signal


class PlotSelector(QWidget):
    # Signal emitted when "Create Plot" is clicked
    # Emits: newPlotRequested(x_axis, y_axis)
    newPlotRequested = Signal(str, str)

    def __init__(self, x_channels, y_channels, parent=None):
        super().__init__(parent)

        self.x_channels = x_channels
        self.y_channels = y_channels

        # --- Widgets ---
        self.x_label = QLabel("X axis:")
        self.x_combo = QComboBox()
        self.x_combo.addItem("")  # placeholder for "no selection"
        self.x_combo.addItems(self.x_channels)

        self.y_label = QLabel("Y axis:")
        self.y_combo = QComboBox()
        self.y_combo.addItem("")  # placeholder for "no selection"
        self.y_combo.addItems(self.y_channels)
        self.y_combo.setEnabled(False)

        self.create_button = QPushButton("Create Plot")
        self.create_button.setEnabled(False)

        # --- Layout ---
        x_layout = QHBoxLayout()
        x_layout.addWidget(self.x_label)
        x_layout.addWidget(self.x_combo)

        y_layout = QHBoxLayout()
        y_layout.addWidget(self.y_label)
        y_layout.addWidget(self.y_combo)

        main_layout = QVBoxLayout()
        main_layout.addLayout(x_layout)
        main_layout.addLayout(y_layout)
        main_layout.addWidget(self.create_button)
        self.setLayout(main_layout)

        # --- Connections ---
        self.x_combo.currentTextChanged.connect(self.on_x_changed)
        self.y_combo.currentTextChanged.connect(self.on_y_changed)
        self.create_button.clicked.connect(self.emit_new_plot)

    def on_x_changed(self, text: str):
        """Enable Y combo and possibly the button when X is chosen."""
        has_x = bool(text.strip())
        self.y_combo.setEnabled(has_x)
        self.update_button_state()

    def on_y_changed(self, text: str):
        """Update button state when Y changes."""
        self.update_button_state()

    def update_button_state(self):
        """Enable button only when both X and Y are selected."""
        has_x = bool(self.x_combo.currentText().strip())
        has_y = bool(self.y_combo.currentText().strip())
        self.create_button.setEnabled(has_x and has_y)

    def emit_new_plot(self):
        """Emit the selected X and Y channels."""
        x_channel = self.x_combo.currentText().strip()
        y_channel = self.y_combo.currentText().strip()
        if x_channel and y_channel:
            self.newPlotRequested.emit(x_channel, y_channel)

if __name__ == "__main__":
    from PySide6.QtWidgets import QApplication

    app = QApplication([])

    widget = PlotSelector(
        x_channels=["time", "frequency", "index"],
        y_channels=["amplitude", "phase", "intensity"]
    )

    def handle_new_plot(x, y):
        print(f"New plot requested: X={x}, Y={y}")

    widget.newPlotRequested.connect(handle_new_plot)
    widget.show()

    app.exec()
