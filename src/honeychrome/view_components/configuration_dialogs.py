import importlib
import sys
from pathlib import Path

from PySide6.QtWidgets import (QApplication, QMainWindow, QPushButton, QWidget, QVBoxLayout, QDialog, QScrollArea, QFormLayout, QLineEdit, QCheckBox, QSpinBox, QDoubleSpinBox, QDialogButtonBox, QComboBox, QLabel, QButtonGroup)
from PySide6.QtCore import Qt, QSettings

from honeychrome.settings import (colourmap_choice, graphics_export_formats, colormap_name, graphics_export_format, cytometry_plot_width_target,
                      tile_size_nxn_grid, subsample, hist_bins, density_cutoff, trigger_channel, adc_channels, width_channels, height_channels,
                      use_dummy_instrument, magnitude_ceilings, magnitude_ceiling, raw_settings, unmixed_settings, experiments_folder,
                      magnitude_ceilings_int, spectral_positive_gate_percent, spectral_negative_gate_percent, report_include_raw, report_include_unmixed, report_include_process)
import honeychrome.settings as settings


import sys
import numpy as np
import colorcet as cc

from PySide6.QtWidgets import QApplication, QLabel
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtCore import Qt

def colormap_to_qimage(cmap_name, width=256, height=20):
    """
    Convert a colorcet colormap to a horizontal swatch QImage.
    """
    cmap = cc.cm[cmap_name]
    # colorcet returns RGB tuples in 0–1 range → convert to uint8
    data = np.array([cmap(i) for i in np.linspace(0, 1, width)])
    data = (data[:, :3] * 255).astype(np.uint8)  # drop alpha if present

    # Repeat rows vertically to form a swatch
    img_array = np.repeat(data[np.newaxis, :, :], height, axis=0)

    # Convert to bytes for QImage
    h, w, _ = img_array.shape
    bytes_per_line = w * 3
    qimg = QImage(
        img_array.data,
        w,
        h,
        bytes_per_line,
        QImage.Format_RGB888
    )
    return qimg.copy()  # copy to detach from numpy buffer


class AppConfigDialog(QDialog):
    def __init__(self, parent=None, bus=None):
        super().__init__(parent)
        self.setWindowTitle("Application Configuration")
        self.resize(700, 700)
        self.settings = QSettings("honeychrome", "app_configuration")
        self.bus = bus

        main_layout = QVBoxLayout(self)

        # --- Scroll Area ---
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)

        container = QWidget()
        form = QFormLayout(container)
        form.setSpacing(10)

        # --- Settings Widgets ---
        self.colourmap_combo = QComboBox()
        self.colourmap_combo.addItems(colourmap_choice)
        form.addRow("Colourmap (visit colorcet.com for definitions):", self.colourmap_combo)

        self.swatch = QLabel()
        form.addWidget(self.swatch)
        self.colourmap_combo.currentTextChanged.connect(self.set_swatch)

        self.graphics_export_format_combo = QComboBox()
        self.graphics_export_format_combo.addItems(graphics_export_formats)
        form.addRow("Graphics Export Format:", self.graphics_export_format_combo)

        self.cytometry_plot_size_spin = QSpinBox()
        self.cytometry_plot_size_spin.setRange(100, 600)
        self.cytometry_plot_size_spin.setSingleStep(50)
        form.addRow("Cytometry Plot Size (pixels):", self.cytometry_plot_size_spin)

        self.nxn_tile_size_spin = QSpinBox()
        self.nxn_tile_size_spin.setRange(20, 300)
        self.nxn_tile_size_spin.setSingleStep(10)
        form.addRow("NxN plots tile size (pixels):", self.nxn_tile_size_spin)

        self.subsample_number_spin = QSpinBox()
        self.subsample_number_spin.setRange(1000, 1_000_000)
        self.subsample_number_spin.setSingleStep(1000)
        form.addRow("Number of events to export if 'Subsample' enabled (pixels):", self.subsample_number_spin)

        self.histogram_resolution_spin = QSpinBox()
        self.histogram_resolution_spin.setRange(50, 400)
        self.histogram_resolution_spin.setSingleStep(50)
        form.addRow("Histogram resolution (bin count):", self.histogram_resolution_spin)

        self.density_cutoff_spin = QSpinBox()
        self.density_cutoff_spin.setRange(0, 1000)
        self.density_cutoff_spin.setSingleStep(10)
        form.addRow("Density cutoff (bin value):", self.density_cutoff_spin)
        self.density_cutoff_spin.setToolTip('Bin value threshold for first level of colourmap (below this level is transparent). Set to 0 for 1/255 of maximum value.')

        self.spectral_positive_gate_percent_spin = QSpinBox()
        self.spectral_positive_gate_percent_spin.setRange(0, 50)
        self.spectral_positive_gate_percent_spin.setSingleStep(1)
        form.addRow("Spectral control positive gate (brightest % of events):", self.spectral_positive_gate_percent_spin)

        self.spectral_negative_gate_percent_spin = QSpinBox()
        self.spectral_negative_gate_percent_spin.setRange(0, 50)
        self.spectral_negative_gate_percent_spin.setSingleStep(1)
        form.addRow("Spectral control negative gate (brightest % of events):", self.spectral_negative_gate_percent_spin)

        self.report_include_raw_cb = QCheckBox("Raw Data")
        self.report_include_unmixed_cb = QCheckBox("Unmixed Data")
        self.report_include_process_cb = QCheckBox("Spectral Process")
        form.addRow("Include raw data in sample report", self.report_include_raw_cb)
        form.addRow("Include unmixed data in sample report", self.report_include_unmixed_cb)
        form.addRow("Include spectral process in sample report", self.report_include_process_cb)

        scroll.setWidget(container)
        main_layout.addWidget(scroll)

        # Buttons
        buttons = QDialogButtonBox(
            QDialogButtonBox.Ok |
            QDialogButtonBox.Cancel |
            QDialogButtonBox.RestoreDefaults
        )
        buttons.accepted.connect(self.handle_accept)
        buttons.rejected.connect(self.reject)
        buttons.button(QDialogButtonBox.RestoreDefaults).clicked.connect(self.reset_to_defaults)
        main_layout.addWidget(buttons, alignment=Qt.AlignRight)

        # Load settings on start
        self.load_settings()

    # ----------------------------
    # Settings Load / Save Methods
    # ----------------------------

    def set_swatch(self, cmap_name):
        qimage = colormap_to_qimage(cmap_name)
        qpixmap = QPixmap.fromImage(qimage)
        self.swatch.setPixmap(qpixmap)

    def load_settings(self):
        colourmap_retrieved = str(self.settings.value("colourmap", colormap_name))
        index = self.colourmap_combo.findText(colourmap_retrieved)
        if index >= 0:
            self.colourmap_combo.setCurrentIndex(index)

        graphics_export_format_retrieved = str(self.settings.value("graphics_export_format", graphics_export_format))
        index = self.graphics_export_format_combo.findText(graphics_export_format_retrieved)
        if index >= 0:
            self.graphics_export_format_combo.setCurrentIndex(index)

        self.cytometry_plot_size_spin.setValue(self.settings.value("cytometry_plot_size", cytometry_plot_width_target, type=int))
        self.nxn_tile_size_spin.setValue(self.settings.value("nxn_tile_size", tile_size_nxn_grid, type=int))
        self.subsample_number_spin.setValue(self.settings.value("subsample_number", subsample, type=int))
        self.histogram_resolution_spin.setValue(self.settings.value("histogram_resolution", hist_bins, type=int))
        self.density_cutoff_spin.setValue(self.settings.value("density_cutoff", density_cutoff, type=int))
        self.spectral_positive_gate_percent_spin.setValue(self.settings.value("spectral_positive_gate_percent", spectral_positive_gate_percent, type=int))
        self.spectral_negative_gate_percent_spin.setValue(self.settings.value("spectral_negative_gate_percent", spectral_negative_gate_percent, type=int))

        self.report_include_raw_cb.setChecked(self.settings.value("report_include_raw", report_include_raw, type=bool))
        self.report_include_unmixed_cb.setChecked(self.settings.value("report_include_unmixed", report_include_unmixed, type=bool))
        self.report_include_process_cb.setChecked(self.settings.value("report_include_process", report_include_process, type=bool))

    def save_settings(self):
        self.settings.setValue("colourmap", self.colourmap_combo.currentText())
        self.settings.setValue("graphics_export_format", self.graphics_export_format_combo.currentText())
        self.settings.setValue("cytometry_plot_size", self.cytometry_plot_size_spin.value())
        self.settings.setValue("nxn_tile_size", self.nxn_tile_size_spin.value())
        self.settings.setValue("subsample_number", self.subsample_number_spin.value())
        self.settings.setValue("histogram_resolution", self.histogram_resolution_spin.value())
        self.settings.setValue("density_cutoff", self.density_cutoff_spin.value())
        self.settings.setValue("spectral_positive_gate_percent", self.spectral_positive_gate_percent_spin.value())
        self.settings.setValue("spectral_negative_gate_percent", self.spectral_negative_gate_percent_spin.value())
        self.settings.setValue("report_include_raw", self.report_include_raw_cb.isChecked())
        self.settings.setValue("report_include_unmixed", self.report_include_unmixed_cb.isChecked())
        self.settings.setValue("report_include_process", self.report_include_process_cb.isChecked())

    def handle_accept(self):
        self.save_settings()
        self.accept()
        importlib.reload(settings)
        self.bus.reloadExpRequested.emit()

    def reset_to_defaults(self):
        index = self.colourmap_combo.findText(colormap_name)
        if index >= 0:
            self.colourmap_combo.setCurrentIndex(index)
        index = self.graphics_export_format_combo.findText(graphics_export_format)
        if index >= 0:
            self.graphics_export_format_combo.setCurrentIndex(index)
        self.cytometry_plot_size_spin.setValue(cytometry_plot_width_target)
        self.nxn_tile_size_spin.setValue(tile_size_nxn_grid)
        self.subsample_number_spin.setValue(subsample)
        self.histogram_resolution_spin.setValue(hist_bins)
        self.density_cutoff_spin.setValue(density_cutoff)
        self.spectral_positive_gate_percent_spin.setValue(spectral_positive_gate_percent)
        self.spectral_negative_gate_percent_spin.setValue(spectral_negative_gate_percent)
        self.report_include_raw_cb.setChecked(report_include_raw)
        self.report_include_unmixed_cb.setChecked(report_include_unmixed)
        self.report_include_process_cb.setChecked(report_include_process)


class InstrumentConfigDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Instrument Configuration: restart application for changes to take effect")
        self.resize(700, 700)
        self.settings = QSettings("honeychrome", "instrument_configuration")

        main_layout = QVBoxLayout(self)

        # --- Scroll Area ---
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)

        container = QWidget()
        form = QFormLayout(container)
        form.setSpacing(10)

        # --- Settings Widgets ---
        self.trigger_channel_combo = QComboBox()
        self.trigger_channel_combo.addItems(adc_channels)
        form.addRow("Trigger Channel:", self.trigger_channel_combo)

        self.width_channel_combo = QComboBox()
        self.width_channel_combo.addItems(adc_channels)
        form.addRow("Width Channel:", self.width_channel_combo)

        self.height_channel_combo = QComboBox()
        self.height_channel_combo.addItems(adc_channels)
        form.addRow("Height Channel:", self.height_channel_combo)

        self.use_dummy_instrument = QCheckBox("Use Dummy Instrument:")
        form.addRow(self.use_dummy_instrument)

        scroll.setWidget(container)
        main_layout.addWidget(scroll)

        # Buttons
        buttons = QDialogButtonBox(
            QDialogButtonBox.Ok |
            QDialogButtonBox.Cancel |
            QDialogButtonBox.RestoreDefaults
        )
        buttons.accepted.connect(self.handle_accept)
        buttons.rejected.connect(self.reject)
        buttons.button(QDialogButtonBox.RestoreDefaults).clicked.connect(self.reset_to_defaults)
        main_layout.addWidget(buttons, alignment=Qt.AlignRight)

        # Load settings on start
        self.load_settings()

    # ----------------------------
    # Settings Load / Save Methods
    # ----------------------------

    def load_settings(self):
        trigger_channel_retrieved = str(self.settings.value("trigger_channel", trigger_channel)) # there can only be one trigger channel
        index = self.trigger_channel_combo.findText(trigger_channel_retrieved)
        if index >= 0:
            self.trigger_channel_combo.setCurrentIndex(index)

        width_channel_retrieved = str(self.settings.value("width_channel", width_channels[0])) # there can be more than one width channel, but currently only allowing one
        index = self.width_channel_combo.findText(width_channel_retrieved)
        if index >= 0:
            self.width_channel_combo.setCurrentIndex(index)

        height_channel_retrieved = str(self.settings.value("height_channel", height_channels)) # there can be more than one height channel, but currently only allowing one
        index = self.height_channel_combo.findText(height_channel_retrieved)
        if index >= 0:
            self.height_channel_combo.setCurrentIndex(index)

        self.use_dummy_instrument.setChecked(self.settings.value("use_dummy_instrument", use_dummy_instrument, type=bool))

    def save_settings(self):
        self.settings.setValue("trigger_channel", self.trigger_channel_combo.currentText())
        self.settings.setValue("width_channel", self.width_channel_combo.currentText())
        self.settings.setValue("height_channel", self.height_channel_combo.currentText())
        self.settings.setValue("use_dummy_instrument", self.use_dummy_instrument.isChecked())

    def handle_accept(self):
        self.save_settings()
        self.accept()

    def reset_to_defaults(self):
        index = self.trigger_channel_combo.findText(trigger_channel)
        if index >= 0:
            self.trigger_channel_combo.setCurrentIndex(index)
        index = self.width_channel_combo.findText(width_channels[0])
        if index >= 0:
            self.width_channel_combo.setCurrentIndex(index)
        index = self.height_channel_combo.findText(height_channels[0])
        if index >= 0:
            self.height_channel_combo.setCurrentIndex(index)
        self.use_dummy_instrument.setChecked(use_dummy_instrument)



class ExperimentSettings(QDialog):
    def __init__(self, experiment, bus, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Experiment Settings")
        self.resize(700, 700)
        self.settings = experiment.settings
        self.bus = bus

        main_layout = QVBoxLayout(self)

        # --- Scroll Area ---
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)

        container = QWidget()
        form = QFormLayout(container)
        form.setSpacing(10)

        # --- Settings Widgets ---
        self.raw_samples_subdirectory_lineedit = QLineEdit()
        form.addRow("Raw Samples Subfolder (relative to experiment folder):", self.raw_samples_subdirectory_lineedit)

        self.single_stain_controls_subdirectory_lineedit = QLineEdit()
        form.addRow("Single Stain Controls Subfolder (relative to experiment folder):", self.single_stain_controls_subdirectory_lineedit)

        self.unmixed_samples_subdirectory_lineedit = QLineEdit()
        form.addRow("Unmixed Samples Subfolder (relative to experiment folder):", self.unmixed_samples_subdirectory_lineedit)

        self.magnitude_ceiling_combo = QComboBox()
        self.magnitude_ceiling_combo.addItems(magnitude_ceilings)
        form.addRow("Magnitude Ceiling of Raw Channels (traditionally a large power of 2):", self.magnitude_ceiling_combo)


        scroll.setWidget(container)
        main_layout.addWidget(scroll)

        # Buttons
        buttons = QDialogButtonBox(
            QDialogButtonBox.Ok |
            QDialogButtonBox.Cancel |
            QDialogButtonBox.RestoreDefaults
        )
        buttons.accepted.connect(self.handle_accept)
        buttons.rejected.connect(self.reject)
        buttons.button(QDialogButtonBox.RestoreDefaults).clicked.connect(self.reset_to_defaults)
        main_layout.addWidget(buttons, alignment=Qt.AlignRight)

        # Load settings on start
        self.load_settings()

    # ----------------------------
    # Settings Load / Save Methods
    # ----------------------------

    def load_settings(self):
        self.raw_samples_subdirectory_lineedit.setText(self.settings['raw']['raw_samples_subdirectory'])
        self.single_stain_controls_subdirectory_lineedit.setText(self.settings['raw']['single_stain_controls_subdirectory'])
        self.unmixed_samples_subdirectory_lineedit.setText(self.settings['unmixed']['unmixed_samples_subdirectory'])

        if self.settings['raw']['magnitude_ceiling'] in magnitude_ceilings_int:
            index = magnitude_ceilings_int.index(self.settings['raw']['magnitude_ceiling'])
            if index >= 0:
                self.magnitude_ceiling_combo.setCurrentIndex(index)

    def save_settings(self):
        self.settings['raw']['raw_samples_subdirectory'] = self.raw_samples_subdirectory_lineedit.text()
        self.settings['raw']['single_stain_controls_subdirectory'] = self.single_stain_controls_subdirectory_lineedit.text()
        self.settings['unmixed']['unmixed_samples_subdirectory'] = self.unmixed_samples_subdirectory_lineedit.text()

        magnitude_ceiling_choice = magnitude_ceilings_int[self.magnitude_ceiling_combo.currentIndex()]
        self.settings['raw']['magnitude_ceiling'] = magnitude_ceiling_choice
        self.settings['unmixed']['magnitude_ceiling'] = magnitude_ceiling_choice

    def handle_accept(self):
        self.save_settings()
        if self.bus:
            self.bus.sampleTreeUpdated.emit()
            self.bus.axesReset.emit([self.settings['raw']['event_channels_pnn'][index] for index in self.settings['raw']['fluorescence_channel_ids']])
            self.bus.axesReset.emit([self.settings['raw']['event_channels_pnn'][index] for index in self.settings['raw']['scatter_channel_ids']])
            # self.bus.axesReset.emit([self.settings['unmixed']['event_channels_pnn'][index] for index in self.settings['unmixed']['fluorescence_channel_ids']])
            # self.bus.axesReset.emit([self.settings['unmixed']['event_channels_pnn'][index] for index in self.settings['unmixed']['scatter_channel_ids']])
        self.accept()

    def reset_to_defaults(self):
        self.raw_samples_subdirectory_lineedit.setText(raw_settings['raw_samples_subdirectory'])
        self.single_stain_controls_subdirectory_lineedit.setText(raw_settings['single_stain_controls_subdirectory'])
        self.unmixed_samples_subdirectory_lineedit.setText(unmixed_settings['unmixed_samples_subdirectory'])

        index = magnitude_ceilings_int.index(raw_settings['magnitude_ceiling'])
        if index >= 0:
            self.magnitude_ceiling_combo.setCurrentIndex(index)

if __name__ == '__main__':
    from honeychrome.experiment_model import ExperimentModel
    from honeychrome.view_components.event_bus import EventBus

    base_directory = Path.home() / experiments_folder

    experiment = ExperimentModel()
    experiment_name = base_directory / 'test experiment'
    experiment_path = experiment_name.with_suffix('.kit')
    experiment.create(experiment_path)

    bus = EventBus()

    class MainWindow(QMainWindow):
        def __init__(self):
            super().__init__()
            self.setWindowTitle("Settings Dialogs Test")
            self.resize(700, 700)

            btn0 = QPushButton("Application Configuration")
            btn0.clicked.connect(self.app_config)

            btn1 = QPushButton("Instrument Configuration")
            btn1.clicked.connect(self.instrument_config)

            btn2 = QPushButton("Experiment Settings")
            btn2.clicked.connect(self.expt_settings)

            central = QWidget()
            layout = QVBoxLayout(central)
            layout.addWidget(btn0)
            layout.addWidget(btn1)
            layout.addWidget(btn2)
            self.setCentralWidget(central)

        def app_config(self):
            dialog = AppConfigDialog(self)
            dialog.exec()

        def instrument_config(self):
            dialog = InstrumentConfigDialog(self)
            dialog.exec()

        def expt_settings(self):
            dialog = ExperimentSettings(experiment, bus, self)
            dialog.exec()

    app = QApplication(sys.argv)

    # Optional: define organization/application for QSettings globally
    QSettings.setDefaultFormat(QSettings.IniFormat)

    window = MainWindow()
    window.show()
    sys.exit(app.exec())
