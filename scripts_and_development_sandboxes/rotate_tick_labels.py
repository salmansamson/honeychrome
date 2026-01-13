import sys
import math
from PySide6.QtWidgets import QApplication
import pyqtgraph as pg
from pyqtgraph.Qt import QtCore


class RotatedAxis(pg.AxisItem):
    def __init__(self, orientation, angle=0, justify='right', **kwargs):
        """
        justify: 'center', 'right', or 'left'
        """
        self.angle = angle
        self.justify = justify
        self._label_padding = 20
        super().__init__(orientation, **kwargs)

        # Initial spacing from axis to text
        self.setStyle(tickTextOffset=25)

    def setTicks(self, ticks, angle=None, justify=None):
        if angle is not None:
            self.angle = angle
            extra_offset = int(15 + abs(self.angle) * 0.3)
            self.setStyle(tickTextOffset=extra_offset)
        if justify is not None:
            self.justify = justify
        super().setTicks(ticks)
        self.updateGeometry()
        self.update()

    def drawPicture(self, p, axisSpec, tickSpecs, textSpecs):
        # Draw ticks but not default text
        super().drawPicture(p, axisSpec, tickSpecs, [])

        p.save()
        for rect, flags, text in textSpecs:
            p.save()

            # For bottom axis, move text a bit closer to the axis line
            if self.orientation == 'bottom':
                anchor = QtCore.QPointF(rect.left(), rect.bottom() - 5)
            elif self.orientation == 'top':
                anchor = QtCore.QPointF(rect.left(), rect.top() + 5)
            else:
                anchor = QtCore.QPointF(rect.left(), rect.center().y())

            p.translate(anchor)

            if self.orientation in ['bottom', 'top']:
                p.rotate(-self.angle)
            else:
                p.rotate(self.angle)

            # Alignment inside rotated text box
            if self.justify == 'right':
                align = QtCore.Qt.AlignRight | QtCore.Qt.AlignVCenter
                text_rect = QtCore.QRectF(-rect.width(), -rect.height()/2,
                                          rect.width(), rect.height())
            elif self.justify == 'left':
                align = QtCore.Qt.AlignLeft | QtCore.Qt.AlignVCenter
                text_rect = QtCore.QRectF(0, -rect.height()/2,
                                          rect.width(), rect.height())
            else:
                align = QtCore.Qt.AlignHCenter | QtCore.Qt.AlignVCenter
                text_rect = QtCore.QRectF(-rect.width()/2, -rect.height()/2,
                                          rect.width(), rect.height())

            p.drawText(text_rect, int(align), text)
            p.restore()
        p.restore()

    def sizeHint(self, *args):
        """
        Increase space below axis to prevent clipping of rotated text.
        """
        hint = super().sizeHint(*args)
        angle_rad = math.radians(abs(getattr(self, "angle", 0)))
        extra = int(self._label_padding + 20 * abs(math.sin(angle_rad)))
        if self.orientation in ['bottom', 'top']:
            hint.setHeight(hint.height() + extra)
        else:
            hint.setWidth(hint.width() + extra)
        return hint


# --- Demo ---
app = QApplication(sys.argv)

axis = RotatedAxis('bottom', angle=45, justify='right')
plot = pg.PlotWidget(axisItems={'bottom': axis})
plot.plot([1, 3, 2, 4, 5])

axis.setTicks([[(i, f"Long Label {i}") for i in range(1, 6)]],
              angle=45, justify='right')

plot.show()
app.exec()
