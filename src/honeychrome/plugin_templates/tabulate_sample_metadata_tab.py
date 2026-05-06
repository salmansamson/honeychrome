"""
Honeychrome Plugin Template
---------------------------
This module defines the interface for a Honeychrome tabbed plugin.

Required Attributes:
    plugin_name (str): The display name used for the tab in the main window.
    PluginWidget (class): the widget to be displayed in the tab

Technical Requirements:
    - Framework: PySide6 (Qt for Python)
"""
from datetime import datetime
from pathlib import Path
import colorcet as cc
import numpy as np

from PySide6.QtWidgets import QWidget, QVBoxLayout, QScrollArea, QLabel
from PySide6.QtCore import Qt
from honeychrome.view_components.clear_layout import clear_layout
from honeychrome.view_components.copyable_table_widget import CopyableTableWidget

plugin_name = 'Tabulate Sample Metadata'
table_headers = ['Key', 'Value']

class PluginWidget(QWidget):
    """
    The main UI container for the plugin.

    Required arguments:
        bus: the signals to communicate with the rest of the honeychrome app
        controller: the honeychrome controller including all ephemeral data, the experiment model and sample. In particular:
            controller.experiment: the experiment model (the honeychrome data)
            controller.current_sample: flowkit.Sample object containing the current sample (raw data)
            cytometry data dictionaries: (see definition in controller)
                controller.data_for_cytometry_plots_raw: ephemeral data for raw cytometry
                controller.data_for_cytometry_plots_process: ephemeral data for spectral process cytometry
                controller.data_for_cytometry_plots_unmixed: ephemeral data for unmixed cytometry

    This plugin displays the sample's metadata in a table, using the flowkit.Sample.get_metadata method.

    """
    def __init__(self, bus=None, controller=None, parent=None):
        super().__init__(parent)
        self.bus = bus
        self.controller = controller

        # --- Create widget, scroll area and layouts to hold the plugin content ---
        self.label = QLabel(plugin_name)

        # the content widget goes in a scroll widget, which goes in the PluginWidget
        self.content_widget = QWidget()
        main_layout = QVBoxLayout(self.content_widget)

        # make this widget scrollable and resizeable
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOn)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setWidget(self.content_widget)

        overall_layout = QVBoxLayout(self)
        overall_layout.addWidget(self.label_disabled)
        overall_layout.addWidget(scroll)

        # --- Add gui objects ---

        output_widget = QWidget()
        self.output_layout = QVBoxLayout(output_widget)

        main_layout.addWidget(self.label)
        main_layout.addWidget(QLabel('Select a sample to view its metadata.'))
        main_layout.addWidget(output_widget)
        main_layout.addStretch()

        # connect signals:
        # loadSampleRequested: if user selects a sample from sample browser, run tabulate_metadata
        self.bus.loadSampleRequested.connect(self.tabulate_metadata)

    def tabulate_metadata(self, sample_path):
        # re-iniitialise if user selects this tab
        if self.controller.current_mode == plugin_name:

            # generate and add table widget
            table_data = self.controller.current_sample.get_metadata()
            table_widget = CopyableTableWidget(table_data, table_headers)

            clear_layout(self.output_layout)
            self.output_layout.addWidget(table_widget)

