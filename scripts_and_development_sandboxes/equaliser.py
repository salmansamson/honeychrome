import sys
from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QSlider, QSpinBox, QLabel,
                               QPushButton)
from PySide6.QtCore import Qt


class SimpleEqualizer(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Simple Equalizer")
        self.setGeometry(100, 100, 400, 600)

        # Preset configurations
        self.presets = {"Flat": [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
            "Bass Boost": [6, 5, 4, 3, 2, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0]}

        self.bands = []

        central_widget = QWidget()
        main_layout = QVBoxLayout()

        # Title
        title = QLabel("16-Band Equalizer")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        main_layout.addWidget(title)

        # Create 16 bands stacked vertically
        for i in range(16):
            band_widget = self.create_band(i)
            self.bands.append(band_widget)
            main_layout.addWidget(band_widget)

        # Preset buttons
        presets_layout = QHBoxLayout()

        flat_btn = QPushButton("Flat")
        flat_btn.clicked.connect(lambda: self.apply_preset("Flat"))

        bass_btn = QPushButton("Bass Boost")
        bass_btn.clicked.connect(lambda: self.apply_preset("Bass Boost"))

        reset_btn = QPushButton("Reset All")
        reset_btn.clicked.connect(self.reset_all)

        presets_layout.addWidget(flat_btn)
        presets_layout.addWidget(bass_btn)
        presets_layout.addWidget(reset_btn)

        main_layout.addLayout(presets_layout)
        central_widget.setLayout(main_layout)
        self.setCentralWidget(central_widget)

    def create_band(self, band_num):
        """Create a single band with horizontal slider and spinbox"""
        band_widget = QWidget()
        layout = QHBoxLayout()

        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Band label
        band_label = QLabel(f"Band {band_num + 1}:")
        band_label.setFixedWidth(60)

        # Horizontal slider
        slider = QSlider(Qt.Orientation.Horizontal)
        slider.setRange(-12, 12)
        slider.setValue(0)
        slider.valueChanged.connect(lambda value: self.on_band_change(band_num, value))

        # Spin box
        spinbox = QSpinBox()
        spinbox.setRange(-12, 12)
        spinbox.setValue(0)
        spinbox.valueChanged.connect(slider.setValue)
        slider.valueChanged.connect(spinbox.setValue)

        # Add widgets to layout
        layout.addWidget(band_label)
        layout.addWidget(slider)
        layout.addWidget(spinbox)

        band_widget.setLayout(layout)
        return band_widget

    def on_band_change(self, band_num, value):
        """Handle band value changes"""
        print(f"Band {band_num + 1} changed to {value} dB")

    def apply_preset(self, preset_name):
        """Apply a preset to all bands"""
        if preset_name in self.presets:
            values = self.presets[preset_name]
            for i, band_widget in enumerate(self.bands):
                slider = band_widget.findChild(QSlider)
                if slider and i < len(values):
                    slider.setValue(values[i])
            print(f"Applied preset: {preset_name}")

    def reset_all(self):
        """Reset all bands to 0 dB"""
        for band_widget in self.bands:
            slider = band_widget.findChild(QSlider)
            if slider:
                slider.setValue(0)
        print("All bands reset to 0 dB")


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = SimpleEqualizer()
    window.show()
    sys.exit(app.exec_())