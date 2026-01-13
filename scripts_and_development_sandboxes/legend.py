import sys
import random
from PySide6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QSizePolicy, QLayout
)
from PySide6.QtCore import Qt, QPoint, QRect, QSize
import pyqtgraph as pg


# --------------------- Flow Layout -------------------------
# (Standard Qt FlowLayout implementation)
class FlowLayout(QLayout):
    def __init__(self, parent=None, margin=6, spacing=6):
        super().__init__(parent)
        self.itemList = []
        self.setContentsMargins(margin, margin, margin, margin)
        self.setSpacing(spacing)

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


# --------------------- Main Window -------------------------
class ExampleWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("PySide6 + PyQtGraph – Wrapping Legend Below Plot")

        mainLayout = QVBoxLayout(self)

        # ---- Plot ----
        self.plot = pg.PlotWidget()
        self.plot.showGrid(x=True, y=True, alpha=0.3)
        mainLayout.addWidget(self.plot, stretch=1)

        # ---- Flowing Legend ----
        self.legendContainer = QWidget()
        self.legendLayout = FlowLayout(self.legendContainer)
        mainLayout.addWidget(self.legendContainer)

        self.add_many_lines(40)

    def add_many_lines(self, n):
        x = list(range(100))
        for i in range(n):
            y = [random.random() + j * 0.005 * i for j in x]
            color = pg.intColor(i, hues=n)
            pen = pg.mkPen(color=color, width=2)

            self.plot.plot(x, y, pen=pen)

            hex_color = pg.mkColor(color).name()
            entry = LegendEntry(hex_color, f"Line {i}")
            self.legendLayout.addWidget(entry)


if __name__ == "__main__":
    app = QApplication(sys.argv)
    w = ExampleWindow()
    w.resize(950, 600)
    w.show()
    app.exec()
