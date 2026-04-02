"""
Honeychrome Plugin Template
---------------------------
This module defines the interface for a Honeychrome tabbed plugin.

Required Attributes:
    plugin_name (str): The display name used for the tab in the main window.
    plugin_enabled (bool): Toggle to True to load the plugin into the UI.
    PluginWidget (class): the widget to be displayed in the tab

Technical Requirements:
    - Framework: PySide6 (Qt for Python)
"""
from pathlib import Path

from PySide6.QtWidgets import QWidget, QVBoxLayout, QScrollArea, QPushButton, QLabel, QComboBox
from PySide6.QtCore import Qt
from honeychrome.controller_components.functions import get_all_subfolders_recursive
from honeychrome.view_components.ordered_multi_sample_picker import OrderedMultiSamplePicker

plugin_name = 'Data Processing Example Plugin'
plugin_enabled = True

class PluginWidget(QWidget):
    """
    The main UI container for the plugin.

    Required arguments:
        bus: the signals to communicate with the rest of the honeychrome app
        controller: the honeychrome controller including all ephemeral data and the experiment model
    """
    def __init__(self, bus=None, controller=None, parent=None):
        super().__init__(parent)
        self.bus = bus
        self.controller = controller

        # --- Create widget, scroll area and layouts to hold the plugin content ---

        # the content widget goes in a scroll widget, which goes in the PluginWidget
        content_widget = QWidget()
        main_layout = QVBoxLayout(content_widget)

        # make this widget scrollable and resizeable
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOn)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setWidget(content_widget)

        overall_layout = QVBoxLayout(self)
        overall_layout.addWidget(scroll)

        # --- Add objects for a data processing workflow ---
        # Add sample picker
        self.picker = OrderedMultiSamplePicker(title="Choose Source Samples for Processing")

        # --- Add gui elements ---
        self.label = QLabel('Data Processing Example')

        self.build_button = QPushButton('Build model')
        self.build_button.setToolTip('Runs the process on selected samples')
        self.build_button.clicked.connect(self.build)

        main_layout.addWidget(self.label)
        main_layout.addWidget(self.picker)
        main_layout.addStretch()

        self.initialise_sample_list()

    def initialise_sample_list(self):
        all_samples = self.controller.experiment.samples['all_samples']
        source_samples_relative_to_raw = [str(Path(sample).relative_to(self.controller.experiment.settings['raw']['raw_samples_subdirectory']))
                                          for sample in all_samples]
        self.picker.set_items(source_samples_relative_to_raw)

    def build(self):
        print('Build!')