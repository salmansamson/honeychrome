import numpy as np
import pyqtgraph as pg
from pyqtgraph.Qt import QtCore, QtWidgets


class BoundedROIBase:
    """Mixin that prevents an ROI from being dragged entirely outside the ViewBox."""
    def __init__(self, *args, viewbox=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.viewbox = viewbox
        if self.viewbox is not None:
            self.sigRegionChanged.connect(self._keep_partially_in_bounds)
            self.viewbox.sigRangeChanged.connect(lambda *a: self._keep_partially_in_bounds())

    def _keep_partially_in_bounds(self):
        """Allow partial exit, but keep at least part of the ROI visible."""
        if self.viewbox is None:
            return

        vb = self.viewbox
        shape_in_vb = self.mapToView(self.shape())
        shape_bounds = shape_in_vb.boundingRect()

        (vb_xmin, vb_xmax), (vb_ymin, vb_ymax) = vb.viewRange()

        dx = dy = 0

        # Only prevent complete exit: if the entire shape is beyond the boundary, push it back.
        if shape_bounds.right() < vb_xmin:
            dx = vb_xmin - shape_bounds.right()
        elif shape_bounds.left() > vb_xmax:
            dx = vb_xmax - shape_bounds.left()

        if shape_bounds.bottom() < vb_ymin:
            dy = vb_ymin - shape_bounds.bottom()
        elif shape_bounds.top() > vb_ymax:
            dy = vb_ymax - shape_bounds.top()

        if dx or dy:
            self.blockSignals(True)
            self.setPos(self.pos() + QtCore.QPointF(dx, dy))
            self.blockSignals(False)


# Example subclasses for various ROI types
class BoundedRectROI(BoundedROIBase, pg.RectROI):
    pass

class BoundedEllipseROI(BoundedROIBase, pg.EllipseROI):
    pass

class BoundedLineROI(BoundedROIBase, pg.LineROI):
    pass

class BoundedPolygonROI(BoundedROIBase, pg.PolyLineROI):
    pass


if __name__ == "__main__":
    app = QtWidgets.QApplication([])

    win = pg.GraphicsLayoutWidget()
    vb = win.addViewBox()
    vb.setAspectLocked(True)
    vb.setLimits(xMin=0, xMax=100, yMin=0, yMax=100)

    # img = pg.ImageItem(np.random.normal(size=(100, 100)))
    # vb.addItem(img)

    # Create and test multiple ROI types
    rect_roi = BoundedRectROI(pos=(10, 10), size=(20, 20), viewbox=vb, pen='r')
    ellipse_roi = BoundedEllipseROI(pos=(40, 40), size=(30, 20), viewbox=vb, pen='y')
    # line_roi = BoundedLineROI([60, 60], [90, 80], viewbox=vb, pen='c')
    poly_roi = BoundedPolygonROI([[10, 80], [30, 90], [20, 70]], closed=True, viewbox=vb, pen='m')

    vb.addItem(rect_roi)
    vb.addItem(ellipse_roi)
    # vb.addItem(line_roi)
    vb.addItem(poly_roi)

    win.show()
    app.exec()
