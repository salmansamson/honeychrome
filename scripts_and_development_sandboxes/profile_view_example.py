from PySide6.QtWidgets import QFrame, QVBoxLayout
import pyqtgraph as pg



class ProfilePlotWidget(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)

        # Layout
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # PyQtGraph plot widget
        self.plot_widget = pg.PlotWidget()
        self.plot_widget.addLegend()
        layout.addWidget(self.plot_widget)

        # Configure plot aesthetics
        self.plot_widget.showGrid(x=True, y=True)
        self.plot_widget.setBackground('w')

    def plot_profiles(self, profiles: dict[str, list[float]], x_labels: list[str]):
        """
        Plots multiple profiles on the graph.
        profiles: dict(name -> list of y-values)
        x_labels: list of string labels for the X axis
        """
        self.plot_widget.clear()
        self.plot_widget.addLegend()

        # Convert x labels to numeric indices
        x_indices = list(range(len(x_labels)))

        # Set string labels on the X axis
        ax = self.plot_widget.getAxis('bottom')
        ax.setTicks([list(zip(x_indices, x_labels))])

        # Plot each profile
        for name, y_vals in profiles.items():
            if len(y_vals) != len(x_labels):
                raise ValueError(f"Profile '{name}' length does not match x_labels length.")

            self.plot_widget.plot(
                x_indices,
                y_vals,
                pen=pg.mkPen(width=2),
                name=name,
                symbol='o',
                symbolSize=6
            )

profiles = {
    "Profile A": [1, 3, 2, 5],
    "Profile B": [2, 1, 4, 3],
}

x_labels = ["Mon", "Tue", "Wed", "Thu"]

import sys
from PySide6.QtWidgets import QApplication
from controller import Controller
from pathlib import Path
from view_components.event_bus import EventBus

app = QApplication(sys.argv)

widget = ProfilePlotWidget()
widget.plot_profiles(profiles, x_labels)
widget.show()

exit_code = app.exec()
sys.exit(exit_code)