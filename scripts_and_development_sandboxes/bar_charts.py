import sys
import numpy as np
from PySide6.QtWidgets import QApplication, QMainWindow
import pyqtgraph as pg
from PySide6.QtGui import QColor
import pyqtgraph.exporters

class Window(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Grouped Bar Chart with Means, Error Bars, and Raw Data")

        # Example dataset: 3 groups × 2 conditions
        # Each entry contains raw data (to plot markers) and we compute
        # the mean + 95% CI for each bar.
        data = {
            "Group A": {
                "Cond 1": np.random.normal(10, 2, 10),
                "Cond 2": np.random.normal(14, 3, 10),
            },
            "Group B": {
                "Cond 1": np.random.normal(12, 2, 10),
                "Cond 2": np.random.normal(18, 3, 10),
            },
            "Group C": {
                "Cond 1": np.random.normal(9, 2, 10),
                "Cond 2": np.random.normal(15, 4, 10),
            },
        }

        groups = list(data.keys())
        conditions = list(next(iter(data.values())).keys())
        num_groups = len(groups)
        num_conds = len(conditions)

        # Prepare plot
        plot = pg.PlotWidget()
        self.setCentralWidget(plot)
        plot.showGrid(x=True, y=True)
        plot.setLabel("left", "Value")
        plot.setLabel("bottom", "Groups")

        bar_width = 0.3
        group_spacing = 3

        # Compute bar positions
        x_positions = []
        for i in range(num_groups):
            group_x0 = i * group_spacing
            for j in range(num_conds):
                x_positions.append(group_x0 + (j +0.5)*bar_width*2)

        # Flatten metrics
        means = []
        errors = []  # 95% CI half-width
        raw_points = []

        for g in groups:
            for c in conditions:
                values = data[g][c]
                mean = np.mean(values)
                ci_95 = 1.96 * np.std(values) / np.sqrt(len(values))
                means.append(mean)
                errors.append(ci_95)
                raw_points.append(values)

        # 🟦 Draw Bars
        colors = [QColor("#66c2a5"), QColor("#fc8d62")] * num_groups
        bars = pg.BarGraphItem(x=x_positions, height=means, width=bar_width, brushes=colors)
        plot.addItem(bars)

        # Add condition labels under each bar
        for g_i, group in enumerate(groups):
            for c_i, cond in enumerate(conditions):
                # matching the x-position formula
                x = g_i * group_spacing + (c_i + (num_conds - 1) / 2) * bar_width * 2
                text = pg.TextItem(cond, anchor=(1, 0))
                plot.addItem(text)
                text.setPos(x, 0)  # place along bottom at y=0
                text.setRotation(-60)

        # 🔴 Plot individual raw data markers
        for x, vals in zip(x_positions, raw_points):
            n = len(vals)
            xs = x + np.linspace(-bar_width * 0.3, bar_width * 0.3, n)
            plot.plot(xs, vals, pen=None, symbol="o", symbolSize=7, symbolBrush="k")

        # ⚪ Draw error bars (mean ± CI)
        error_item = pg.ErrorBarItem(
            x=np.array(x_positions),
            y=np.array(means),
            top=np.array(errors),
            bottom=np.array(errors),
            beam=0.1
        )
        plot.addItem(error_item)

        # 🏷️ X-axis group labels
        tick_positions = [(i * group_spacing, groups[i]) for i in range(num_groups)]
        ax = plot.getAxis("bottom")
        ax.setTicks([tick_positions])

        # Assuming 'plot' is your PlotWidget
        exporter = pg.exporters.ImageExporter(plot.plotItem)
        exporter.parameters()['width'] = 1000  # optional: set output width
        exporter.export('my_pyqtgraph_plot.png')


if __name__ == "__main__":
    app = QApplication(sys.argv)
    win = Window()
    win.resize(900, 600)
    win.show()
    sys.exit(app.exec())
