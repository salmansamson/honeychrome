from PySide6.QtCore import Qt, QTimer, QPointF, QRectF, QObject, QEvent, QPoint
from PySide6.QtGui import QFont, QPen, QColor, QCursor, QWheelEvent, QMouseEvent
from PySide6.QtWidgets import QApplication, QMenu, QScrollArea
import pyqtgraph as pg

import logging
logger = logging.getLogger(__name__)

import warnings
warnings.filterwarnings("ignore", message="t.core.qobject.connect: QObject::connect(QStyleHints, QStyleHints): unique connections require a pointer to member function of a QObject subclass")

class ZoomAxis(pg.AxisItem):
    def __init__(self, orientation, viewbox, angle=0, **kwargs):
        self.angle = angle
        self._label_padding = 15
        super().__init__(orientation, **kwargs)

        self.setAcceptHoverEvents(True)  # needed for hover detection
        self.vb = viewbox
        self.orientation = orientation
        self.initial_pos = None
        self._last_pos = None
        self._pending_delta = 0
        self.zoom_timer = QTimer()
        self.zoom_timer.setInterval(60)  # update rate in ms
        self.zoomZero = 0
        self.fullRange = (0, 1.1)
        self.limits = (0, 1)

        # Give extra space by default to prevent clipping
        self.setStyle(tickTextOffset=30, tickLength=5)

    def setTicks(self, ticks, angle=0):
        """Override setTicks to optionally update rotation angle."""
        if angle is not None:
            self.angle = angle
            # Adjust spacing dynamically with rotation (cast to int)
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
                text_rect = QRectF(0, -rect.height()/2, rect.width(), rect.height())
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


    def hoverEnterEvent(self, event):
        QApplication.setOverrideCursor(Qt.CursorShape.PointingHandCursor)

    def hoverLeaveEvent(self, event):
        QApplication.restoreOverrideCursor()

    def mousePressEvent(self, ev):
        if ev.button() == Qt.MouseButton.LeftButton:
            self.initial_pos = ev.pos()
            self._last_pos = self.initial_pos
            self._pending_delta = 0
            self.zoom_timer.start()
            ev.accept()
        else:
            ev.ignore()

    def mouseMoveEvent(self, ev):
        if self._last_pos is None:
            ev.ignore()
            return

        delta = ev.pos() - self._last_pos
        self._last_pos = ev.pos()

        if self.orientation == 'bottom':
            self._pending_delta += delta.x()
        elif self.orientation == 'left':
            self._pending_delta += delta.y()

        ev.accept()

        if QApplication.overrideCursor() == Qt.CursorShape.PointingHandCursor:
            QApplication.setOverrideCursor(Qt.CursorShape.ClosedHandCursor)


    def mouseReleaseEvent(self, ev):
        self._last_pos = None
        self._pending_delta = 0
        self.zoom_timer.stop()
        ev.accept()

        QApplication.restoreOverrideCursor()

class WheelEventFilter(QObject):
    def eventFilter(self, obj, event):
        if event.type() == QEvent.Wheel:
            # Find the scroll area
            scroll_area = self.find_parent_scroll_area(obj)
            if scroll_area and scroll_area.isVisible():
                # Create a new wheel event for the scroll area
                pos = scroll_area.mapFromGlobal(QCursor.pos())
                wheel_event = QWheelEvent(pos, QCursor.pos(), QPoint(),
                    QPoint(0, event.angleDelta().y()), event.buttons(), event.modifiers(), event.phase(),
                    event.inverted())
                QApplication.sendEvent(scroll_area.viewport(), wheel_event)
                return True
        return False

    def find_parent_scroll_area(self, widget):
        parent = widget.parent()
        while parent:
            if isinstance(parent, QScrollArea):
                return parent
            parent = parent.parent()
        return None

class NoPanViewBox(pg.ViewBox):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, enableMouse=True, **kwargs)
        self.setMouseMode(self.PanMode)
        self.setMouseEnabled(x=False, y=False)

    def mouseDragEvent(self, ev, axis=None):
        ev.ignore()  # 🔒 Disable all panning and dragging in plot area

    def wheelEvent(self, ev, axis=None):
        ev.ignore()  # 🔒 Disable mouse wheel zoom

class InteractiveLabel(pg.LabelItem):
    def __init__(self, text="", parent_plot=None, angle=0, **kwargs):
        super().__init__(text, angle=angle, **kwargs)
        self.setAcceptHoverEvents(True)
        self._default_font = self.item.font()
        self._hover_font = QFont(self._default_font)
        self._hover_font.setUnderline(True)
        self.leftClickMenuItems = []
        self.rightClickMenuItems = []
        self.leftItemSelected = None
        self.rightItemSelected = None
        self.leftClickMenuFunction = None
        self.rightClickMenuFunction = None
        self.parent_plot = parent_plot

    def hoverEnterEvent(self, event):
        self.item.setFont(self._hover_font)
        QApplication.setOverrideCursor(Qt.CursorShape.PointingHandCursor)

    def hoverLeaveEvent(self, event):
        self.item.setFont(self._default_font)
        QApplication.restoreOverrideCursor()

    def mousePressEvent(self, event):
        self.parent_plot.select_plot_on_parent_grid()
        if event.button() == Qt.MouseButton.RightButton:
            self.show_right_context_menu(event.screenPos())
        elif event.button() == Qt.MouseButton.LeftButton:
            self.selectable_menu_activates_function(event.screenPos())  # can choose to differentiate

    def selectable_menu_activates_function(self, pos):
        menu = QMenu()
        actions = {}

        for n, item in enumerate(self.leftClickMenuItems):
            if item == 'Count':
                menu.addSeparator()
                action = menu.addAction(item)
                actions[action] = item
            elif item == 'All Fluorescence':
                menu.addSeparator()
                action = menu.addAction(item)
                actions[action] = item
            else:
                action = menu.addAction(item)
                action.setCheckable(True)
                if n == self.leftItemSelected:
                    action.setChecked(True)
                actions[action] = n
        chosen_action = menu.exec(pos)

        if chosen_action:
            self.leftItemSelected = actions[chosen_action]
            func = self.leftClickMenuFunction
            func(self.leftItemSelected, self.parent())
            logger.info(f"{func} called with option {self.leftItemSelected} parent {self.parent()}")


    def show_right_context_menu(self, pos):
        menu = QMenu()
        actions = {}

        for n, item in enumerate(self.rightClickMenuItems):
            action = menu.addAction(item)
            action.setCheckable(True)
            if n == self.rightItemSelected:
                action.setChecked(True)
            actions[action] = n
        chosen_action = menu.exec(pos)

        if chosen_action:
            self.rightItemSelected = actions[chosen_action]
            func = self.rightClickMenuFunction
            func(self.rightItemSelected, self.parent())
            logger.info(f"{func} called with option {self.rightItemSelected} parent {self.parent()}")
