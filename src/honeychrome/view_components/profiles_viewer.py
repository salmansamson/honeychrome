from PySide6.QtCore import QPointF, QRectF, Qt, QRect, QSize, QPoint, Slot
from PySide6.QtWidgets import QFrame, QVBoxLayout, QLayout, QWidget, QHBoxLayout, QLabel, QSizePolicy
import pyqtgraph as pg

from honeychrome.settings import heading_style, line_colors


# --------------------- Flow Layout -------------------------
# (Standard Qt FlowLayout implementation)
class FlowLayout(QLayout):
    def __init__(self, parent=None, margin=6, spacing=6):
        super().__init__(parent)
        self.itemList = []
        self.setContentsMargins(margin, margin, margin, margin)
        self.setSpacing(spacing)

    def clear(self):
        for i in reversed(range(self.count())):
            item = self.takeAt(i)
            w = item.widget()
            if w is not None:
                w.setParent(None)
                w.deleteLater()

    def addItem(self, item):
        self.itemList.append(item)

    def count(self):
        return len(self.itemList)

    def itemAt(self, index):
        if 0 <= index < len(self.itemList):
            return self.itemList[index]
        return None

    def takeAt(self, index):
        if 0 <= index < len(self.itemList):
            return self.itemList.pop(index)
        return None

    def expandingDirections(self):
        return Qt.Orientations(Qt.Orientation(0))

    def hasHeightForWidth(self):
        return True

    def heightForWidth(self, width):
        height = self.doLayout(QRect(0, 0, width, 0), testOnly=True)
        return height

    def setGeometry(self, rect):
        super().setGeometry(rect)
        self.doLayout(rect, testOnly=False)

    def sizeHint(self):
        return QSize(400, 200)

    def doLayout(self, rect, testOnly=False):
        x = rect.x()
        y = rect.y()
        lineHeight = 0

        for item in self.itemList:
            wid = item.widget()
            spaceX = self.spacing()
            spaceY = self.spacing()
            nextX = x + item.sizeHint().width() + spaceX

            if nextX - spaceX > rect.right():
                x = rect.x()
                y = y + lineHeight + spaceY
                nextX = x + item.sizeHint().width() + spaceX
                lineHeight = 0

            if not testOnly:
                item.setGeometry(QRect(QPoint(x, y), item.sizeHint()))

            x = nextX
            lineHeight = max(lineHeight, item.sizeHint().height())

        return y + lineHeight - rect.y()


# --------------------- Legend Entry -------------------------
class LegendEntry(QWidget):
    """A single legend row: colored square + label."""
    def __init__(self, color, text):
        super().__init__()
        layout = QHBoxLayout(self)
        layout.setContentsMargins(2, 2, 2, 2)
        layout.setSpacing(5)

        colorBox = QLabel()
        colorBox.setFixedSize(14, 14)
        colorBox.setStyleSheet(f"background-color: {color}; border:1px solid #444;")
        layout.addWidget(colorBox)

        nameLabel = QLabel(text)
        layout.addWidget(nameLabel)

        self.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Maximum)




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
                # p.setPen(QPen(QColor("white")))
                p.drawText(text_rect, int(align), text)

            else:
                # Non-rotated text fallback
                # p.setPen(QPen(QColor("white")))
                p.drawText(rect, int(flags), text)

            p.restore()
        p.restore()

class ProfilesViewer(QFrame):
    def __init__(self, bus, controller, pen_width=2, parent=None):
        super().__init__(parent)

        # connect
        self.bus = bus
        self.controller = controller
        self.pen_width = pen_width

        if self.bus:
            self.bus.showSelectedProfiles.connect(self.plot_profiles)
            self.bus.spectralControlAdded.connect(self.plot_latest_profile)

        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.title = QLabel("Profiles Viewer")
        self.layout.addWidget(self.title)
        self.title.setStyleSheet(heading_style)

        # ---- Flowing Legend ----
        self.legendContainer = QWidget()
        self.legendLayout = FlowLayout(self.legendContainer)
        self.layout.addWidget(self.legendContainer)

        # Create the PyQtGraph widget
        bottom_axis_vertical_tick_labels = BottomAxisVerticalTickLabels()
        self.plot_widget = pg.PlotWidget(axisItems={'bottom': bottom_axis_vertical_tick_labels})
        self.layout.addWidget(self.plot_widget, stretch=1)
        vb = self.plot_widget.getViewBox()
        vb.setMouseEnabled(False, False)
        vb.setMenuEnabled(False)  # disable right-click menu

        # Configure the plot
        self.plot_widget.setLabel('left', 'Intensity')
        self.plot_widget.setLabel('bottom', 'All Fluorescence')
        self.plot_widget.showGrid(x=True, y=True, alpha=0.3)
        self.plot_widget.addLegend()

        # Store plot items for potential updates
        self.plot_items = {}

        if self.controller.experiment.process['profiles']:
            self.plot_profiles([])

    def show_context_menu(self, event):
        # Empty method to completely disable context menu
        pass

    @Slot()
    def plot_latest_profile(self):
        spectral_model = self.controller.experiment.process['spectral_model']
        if spectral_model:
            control = spectral_model[-1]['label']
            if control:
                if control in self.controller.experiment.process['profiles']:
                    self.plot_profiles([control], show_legend=False)

    @Slot(list)
    def plot_profiles(self, profile_list, show_legend=True):

        # Clear previous plots
        self.plot_widget.clear()
        self.plot_items.clear()
        self.legendLayout.clear()

        profiles = self.controller.experiment.process['profiles']

        x = list(range(len(self.controller.filtered_raw_fluorescence_channel_ids)))
        ticks = [[(m, self.controller.experiment.settings['raw']['event_channels_pnn'][n]) for m, n in
                   enumerate(self.controller.filtered_raw_fluorescence_channel_ids)], []]
        self.plot_widget.getAxis('bottom').setTicks(ticks)


        # Plot each profile
        if profile_list:
            pass
        else:
            profile_list = list(profiles.keys())

        profile_list = [p for p in profile_list if p]
        for i, profile_name in enumerate(profile_list):
            if profile_name in profiles:
                color = line_colors[i % len(line_colors)]
                pen = pg.mkPen(color=color, width=self.pen_width)
                plot_item = self.plot_widget.plot(x, profiles[profile_name], pen=pen)
                self.plot_items[profile_name] = plot_item
                if show_legend:
                    entry = LegendEntry(color, profile_name)
                    self.legendLayout.addWidget(entry)

        # self.plot_widget.autoRange()
        self.plot_widget.setXRange(0, len(self.controller.filtered_raw_fluorescence_channel_ids))  # Set custom x-axis range
        self.plot_widget.setYRange(0, 1)  # Set custom y-axis range



if __name__ == '__main__':
    from PySide6.QtWidgets import QApplication, QVBoxLayout
    import sys

    app = QApplication(sys.argv)

    from honeychrome.controller import Controller
    from pathlib import Path
    from event_bus import EventBus

    bus = EventBus()
    kc = Controller()
    base_directory = Path.home() / 'spectral_cytometry'
    experiment_name = base_directory / '20240620 Spectral Symposium-poor cell unmixed'
    experiment_path = experiment_name.with_suffix('.kit')
    kc.load_experiment(experiment_path) # note this loads first sample too and runs calculate all histograms and statistics

    plot_frame = ProfilesViewer(bus, kc)

    # Plot the profiles
    plot_frame.plot_profiles([])
    plot_frame.show()

    plot_frame.resize(950, 600)
    sys.exit(app.exec())