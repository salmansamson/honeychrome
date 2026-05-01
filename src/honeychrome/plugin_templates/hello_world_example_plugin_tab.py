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

from PySide6.QtWidgets import QWidget, QVBoxLayout, QScrollArea, QPushButton, QLabel
from PySide6.QtCore import Qt

plugin_name = 'Hello World Plugin'

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


        # --- Add some GUI elements to show functionality ---
        self.label = QLabel('')
        self.label.setTextFormat(Qt.RichText)
        self.label.setWordWrap(True)

        self.refresh_button = QPushButton('Refresh')
        self.refresh_button.setToolTip('Runs a method "refresh"')
        self.refresh_button.clicked.connect(self.refresh)

        self.popup_button = QPushButton('Send signal to make popup')
        self.popup_button.setToolTip('Uses the signal bus to communicate with a function elsewhere in Honeychrome')
        self.popup_button.clicked.connect(lambda: self.bus.popupMessage.emit('Hello World!'))

        main_layout.addWidget(self.popup_button)
        main_layout.addWidget(self.refresh_button)
        main_layout.addWidget(self.label)

        self.refresh()

    def refresh(self):
        # put some data from the controller into the label
        import json

        self.label.setText(f'''
        <h1>Hello world!</h1>
        
        <p>Cytometry data can be accessed from the controller object (and the experiment object from controller.experiment):</p>
        
        <ul>
            <li> controller.experiment_dir: <pre>{self.controller.experiment_dir}</pre> </li>
            <li> controller.current_sample_path: <pre>{self.controller.current_sample_path}</pre> </li>
            <li> controller.expreriment.samples: <pre>{json.dumps(self.controller.experiment.samples, indent=2)}</pre> </li>
        </ul>
        ''')
