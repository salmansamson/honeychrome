import numpy as np
import colorcet as cc

from PySide6.QtWidgets import QApplication, QLabel
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtCore import Qt


def array_to_qpixmap(arr, cmap_name="fire"):

    arr_norm = (arr - arr.min()) / (arr.max() - arr.min())

    # get a callable colormap (returns Nx3 floats in 0..1)
    cmap = cc.cm[cmap_name]

    # convert normalized values to RGB
    rgb = (cmap(arr_norm)[:, :, :3] * 255).astype(np.uint8)

    h, w, _ = rgb.shape

    qimg = QImage(
        rgb.data, w, h, 3 * w, QImage.Format_RGB888
    ).copy()

    return QPixmap.fromImage(qimg)


if __name__ == "__main__":
    app = QApplication([])

    # example 2D array
    data = np.random.random((300, 400))

    pixmap = array_to_qpixmap(data, "rainbow4")  # try: "rainbow", "bgy", "magma"

    label = QLabel()
    label.setPixmap(pixmap)
    label.show()

    app.exec()
