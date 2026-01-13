import sys
import numpy as np
from PySide6.QtGui import QPen, QColor
from PySide6.QtWidgets import QFrame, QVBoxLayout
from PySide6.QtCore import QRectF, Slot, QPointF, Qt
import pyqtgraph as pg
import colorcet as cc
from settings import heatmap_colormap_name

colors = cc.palette[heatmap_colormap_name]  # Get the colormap from Colorcet
cmap = pg.ColorMap(pos=np.linspace(0.0, 1.0, len(colors)), color=colors) # Convert Colorcet colormap to PyQtGraph's format
rgba_lut = cmap.getLookupTable(alpha=True)


class BottomAxisVerticalTickLabels(pg.AxisItem):
    def __init__(self, **kwargs):
        self.angle = 90
        self._label_padding = 15
        self.orientation = 'bottom'
        super().__init__(self.orientation, **kwargs)

        # Give extra space by default to prevent clipping
        self.setStyle(tickTextOffset=30, tickLength=5)

    def setTicks(self, ticks):
        extra_offset = int(10 + abs(self.angle) * 0.4)
        self.setStyle(tickTextOffset=extra_offset)
        super().setTicks(ticks)
        self.updateGeometry()
        self.update()

    def drawPicture(self, p, axisSpec, tickSpecs, textSpecs):
        # Draw tick lines normally (skip text)
        super().drawPicture(p, axisSpec, tickSpecs, [])

        # Draw rotated text labels manually
        p.save()
        for rect, flags, text in textSpecs:
            p.save()

            # --- DEBUG VISUALS ---
            # 1. Draw the original (unrotated) text rect in red
            # p.setPen(QPen(QColor("red"), 1, Qt.DashLine))
            # p.drawRect(rect)

            # 2. Draw the tick anchor point in green
            tick_anchor = QPointF(rect.center())
            # p.setPen(QPen(QColor("green"), 3))
            # p.drawPoint(tick_anchor)

            # --- TRANSFORMATIONS ---
            if self.orientation == 'bottom' and self.angle == 90:
                p.translate(tick_anchor)
                p.rotate(-self.angle)

                # 3. Draw local origin axes in blue (X) and magenta (Y)
                # p.setPen(QPen(QColor("blue"), 1))
                # p.drawLine(0, 0, 40, 0)  # X-axis
                # p.setPen(QPen(QColor("magenta"), 1))
                # p.drawLine(0, 0, 0, 40)  # Y-axis

                # 4. Draw the rotated text bounding rect in yellow
                text_rect = QRectF(0, -rect.height() / 2, rect.width(), rect.height())
                # p.setPen(QPen(QColor("yellow"), 1))
                # p.drawRect(text_rect)

                # --- Draw the text ---
                align = Qt.AlignRight | Qt.AlignVCenter
                p.setPen(QPen(QColor("white")))
                p.drawText(text_rect, int(align), text)

            else:
                # Non-rotated text fallback
                p.setPen(QPen(QColor("white")))
                p.drawText(rect, int(flags), text)

            p.restore()
        p.restore()


class HeatmapViewer(QFrame):
    def __init__(self, bus, controller, process_key, parent=None):
        super().__init__(parent)

        # connect
        self.bus = bus
        self.controller = controller
        self.bus.showSelectedProfiles.connect(self.plot_heatmap)
        self.matrix = self.controller.experiment.process[process_key]


        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)

        bottom_axis_vertical_tick_labels = BottomAxisVerticalTickLabels()
        self.plot_widget = pg.PlotWidget(axisItems={'bottom': bottom_axis_vertical_tick_labels})
        self.layout.addWidget(self.plot_widget, stretch=1)

        self.plot_widget.setAspectLocked()

        # Configure the plot
        self.plot_widget.setLabel('left', 'Intensity')
        self.plot_widget.setLabel('bottom', 'All Fluorescence')

        self.img = pg.ImageItem(parent=self)
        self.plot_widget.addItem(self.img)

        # Store plot items for potential updates
        self.plot_items = {}

        # Colormap
        self.img.setLookupTable(rgba_lut)
        # self.img.setLevels([self.matrix.min(), self.matrix.max()])

        if self.matrix:
            self.plot_heatmap([])
        else:
            self.plot_widget.setVisible(False)

    def show_context_menu(self, event):
        # Empty method to completely disable context menu
        pass

    @Slot(list)
    def plot_heatmap(self, y_pnn):
        matrix = np.array(self.matrix)

        x_pnn = self.controller.experiment.settings['raw']['event_channels_pnn']
        x_fl_ids = self.controller.experiment.settings['raw']['fluorescence_channel_ids']
        x_ticks = [[(m+0.5, x_pnn[n]) for m, n in enumerate(x_fl_ids)], []]
        self.plot_widget.getAxis('bottom').setTicks(x_ticks)

        if y_pnn:
            pass
        else:
            y_pnn = self.controller.experiment.settings['unmixed']['event_channels_pnn']

        y_fl_ids = self.controller.experiment.settings['unmixed']['fluorescence_channel_ids']
        y_ticks = [[(m+0.5, y_pnn[n]) for m, n in enumerate(y_fl_ids)], []]
        self.plot_widget.getAxis('left').setTicks(y_ticks)

        self.img.setImage(matrix.T)

        # Correct scaling: each cell is 1×1
        rows, cols = matrix.shape
        self.img.setRect(QRectF(0.0, 0.0, float(cols), float(rows)))

        # self.plot_widget.autoRange()
        self.plot_widget.setXRange(0, self.controller.experiment.settings['raw']['n_fluorophore_channels'])  # Set custom x-axis range
        self.plot_widget.setYRange(0, 1)  # Set custom y-axis range

        # Add data labels on top
        for y in range(rows):
            for x in range(cols):
                value = matrix[y, x]
                text = pg.TextItem(html=f"<span style='color:white;'>{value:0.2g}</span>", anchor=(0.5, 0.5))
                self.plot_widget.addItem(text)
                text.setPos(x + 0.5, y + 0.5)  # center of the cell


if __name__ == '__main__':
    from PySide6.QtWidgets import QApplication
    import sys

    app = QApplication(sys.argv)

    from controller import Controller
    from pathlib import Path
    from event_bus import EventBus

    bus = EventBus()
    kc = Controller()
    base_directory = Path.home() / 'spectral_cytometry'
    experiment_name = base_directory / '20240620 Spectral Symposium-poor cell unmixed'
    experiment_path = experiment_name.with_suffix('.kit')
    kc.load_experiment(experiment_path) # note this loads first sample too and runs calculate all histograms and statistics

    # frame = HeatmapViewer(bus, kc, 'similarity_matrix')
    frame = HeatmapViewer(bus, kc, 'unmixing_matrix')

    # Plot the profiles
    frame.plot_heatmap([])
    frame.show()

    frame.resize(950, 600)
    sys.exit(app.exec())


