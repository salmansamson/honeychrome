from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QComboBox, QPushButton
)
max_visible_items = 15

class NewPlotWidget(QWidget):
    # Signal emitted when "Create Plot" is clicked
    # Emits: newPlotRequested(x_axis, y_axis)

    def __init__(self, bus=None, mode=None, data_for_cytometry_plots=None, parent=None):
        super().__init__(parent)
        # connect to data
        self.bus = bus
        self.mode = mode
        self.data_for_cytometry_plots = data_for_cytometry_plots

        self.x_channels = self.data_for_cytometry_plots['pnn'] + ['All Fluorescence']
        self.y_channels = self.y_channels = self.data_for_cytometry_plots['pnn'] + ['Count']

        # --- Widgets ---
        self.x_label = QLabel("X axis:")
        self.x_combo = QComboBox()
        self.x_combo.addItem("")  # placeholder for "no selection"
        self.x_combo.addItems(self.x_channels)
        self.x_combo.setMaxVisibleItems(100)
        self.x_combo.setStyleSheet("""
            QComboBox { 
                combobox-popup: 0; max-height: 700px; min-width: 150px; 
            }
        """)

        self.y_label = QLabel("Y axis:")
        self.y_combo = QComboBox()
        self.y_combo.addItem("")  # placeholder for "no selection"
        self.y_combo.addItems(self.y_channels)
        self.y_combo.setMaxVisibleItems(100)
        self.y_combo.setStyleSheet("""
            QComboBox { 
                combobox-popup: 0; max-height: 700px; min-width: 150px; 
            }
        """)
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
        main_layout.addStretch()
        main_layout.addLayout(x_layout)
        main_layout.addLayout(y_layout)
        main_layout.addWidget(self.create_button)
        main_layout.addStretch()
        self.setLayout(main_layout)

        # --- Connections ---
        self.x_combo.currentTextChanged.connect(self.on_x_changed)
        self.y_combo.currentTextChanged.connect(self.on_y_changed)
        self.create_button.clicked.connect(self.emit_new_plot)

    def on_x_changed(self, x_text: str):
        """Enable Y combo and possibly the button when X is chosen."""
        has_x = bool(x_text.strip())
        if x_text == 'All Fluorescence':
            self.y_combo.setCurrentIndex(0)
            self.y_combo.setEnabled(False)
            self.create_button.setEnabled(True)
        else:
            self.y_combo.setEnabled(has_x)
            self.update_button_state()

    def on_y_changed(self, text: str):
        """Update button state when Y changes."""
        self.update_button_state()

    def update_button_state(self):
        """Enable button only when both X and Y are selected."""
        has_x = bool(self.x_combo.currentText().strip())
        ribbon = self.x_combo.currentText().strip() == 'All Fluorescence'
        has_y = bool(self.y_combo.currentText().strip())
        self.create_button.setEnabled(has_x and (has_y or ribbon))

    def emit_new_plot(self):
        """Emit the selected X and Y channels."""
        x_channel = self.x_combo.currentText().strip()
        y_channel = self.y_combo.currentText().strip()
        ribbon = x_channel == 'All Fluorescence'
        if x_channel and (y_channel or ribbon):
            self.bus.newPlotRequested.emit(x_channel, y_channel)
            self.deleteLater()

if __name__ == "__main__":
    from PySide6.QtWidgets import QApplication
    from pathlib import Path
    from honeychrome.controller import Controller
    from honeychrome.view_components.event_bus import EventBus

    app = QApplication([])

    kc = Controller()
    base_directory = Path.home() / 'spectral_cytometry'
    experiment_name = base_directory / '20240620 Spectral Symposium-poor cell unmixed'
    experiment_path = experiment_name.with_suffix('.kit')
    kc.load_experiment(experiment_path) # note this loads first sample too and runs calculate all histograms and statistics
    kc.current_mode = 'raw'
    kc.initialise_data_for_cytometry_plots()

    widget = NewPlotWidget(
        bus=EventBus(), data_for_cytometry_plots=kc.data_for_cytometry_plots_raw
    )

    def handle_new_plot(x, y):
        print(f"New plot requested: X={x}, Y={y}")

    widget.bus.newPlotRequested.connect(handle_new_plot)
    widget.show()

    app.exec()
