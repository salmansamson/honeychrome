import time

import numpy as np
from PySide6.QtCore import QThread, Signal, Slot, QObject, Qt, QTimer
from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel
from queue import Empty
import pyqtgraph as pg

from honeychrome.instrument_configuration import n_time_points_in_event, adc_rate
from honeychrome.settings import analyser_target_repeat_time, line_colors, adc_channels, scatter_channels, fluorescence_channels
from honeychrome.view_components.profiles_viewer import FlowLayout, LegendEntry

import logging
logger = logging.getLogger(__name__)

class OscilloscopeWidget(QWidget):
    _instance = None

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self, controller, bus):
        if not hasattr(self, '_initialized'):
            super().__init__()
            self._initialized = True
            self.controller = controller
            self.bus = bus

            self.setGeometry(10, 10, 800, 700)
            self.setWindowTitle("Oscilloscope Viewer")
            self.layout = QVBoxLayout(self)
            self.layout.setContentsMargins(0, 0, 0, 0)

            self.label = QLabel('')

            self.plot_widget1 = pg.PlotWidget()
            self.plot_widget1.setLabel('left', 'Intensity', units='ADC Units')
            self.plot_widget1.setLabel('bottom', 'Time', units='us')
            self.plot_widget1.showGrid(x=True, y=True, alpha=0.3)

            self.plot_widget2 = pg.PlotWidget()
            self.plot_widget2.setLabel('left', 'Intensity', units='ADC Units')
            self.plot_widget2.setLabel('bottom', 'Time', units='us')
            self.plot_widget2.showGrid(x=True, y=True, alpha=0.3)

            # ---- Flowing Legend ----
            self.legendContainer1 = QWidget()
            self.legendContainer2 = QWidget()
            self.legendLayout1 = FlowLayout(self.legendContainer1)
            self.legendLayout2 = FlowLayout(self.legendContainer2)

            self.layout.addWidget(self.label)
            self.layout.addWidget(self.plot_widget1)
            self.layout.addWidget(self.legendContainer1)
            self.layout.addWidget(self.plot_widget2)
            self.layout.addWidget(self.legendContainer2)

            self.x = np.arange(n_time_points_in_event) / adc_rate

            self.scatter_channel_indices = [i for i,channel in enumerate(adc_channels) if channel in scatter_channels]
            self.fluorescence_channel_indices = [i for i,channel in enumerate(adc_channels) if channel in fluorescence_channels]
            for i in range(len(scatter_channels)):
                color = line_colors[i % len(line_colors)]
                entry = LegendEntry(color, scatter_channels[i])
                self.legendLayout1.addWidget(entry)

            for i in range(len(fluorescence_channels)):
                color = line_colors[i % len(line_colors)]
                entry = LegendEntry(color, fluorescence_channels[i])
                self.legendLayout2.addWidget(entry)

            # Use a timer to check the queue periodically
            self.trace = None
            self.timer = QTimer()
            self.timer.timeout.connect(self.check_queue)
            self.timer.setInterval(int(analyser_target_repeat_time * 1000))
            self.timer.start()

    @Slot()
    def check_queue(self):
        try:
            self.trace = self.controller.oscilloscope_traces_queue.get_nowait()
            self._update_plot()
        except Empty:
            pass

    @Slot(dict)
    def _update_plot(self):
        """Thread-safe method to update the plot"""
        try:
            self.plot_widget1.clear()
            for i in self.scatter_channel_indices:
                color = line_colors[i % len(line_colors)]
                y = self.trace['traces'][i]
                self.plot_widget1.plot(self.x, y, pen=color)
            self.plot_widget2.clear()
            for i in self.fluorescence_channel_indices:
                color = line_colors[i % len(line_colors)]
                y = self.trace['traces'][i]
                self.plot_widget2.plot(self.x, y, pen=color)

            self.label.setText(f"event_id={self.trace['event_id']} time={self.trace['time']}")

        except Exception as e:
            logger.info(f"Error updating plot: {e}")

    def closeEvent(self, event):
        self.timer.stop()
        event.accept()