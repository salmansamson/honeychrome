import sys
import numpy as np
import colorcet as cc

from PySide6.QtWidgets import QApplication, QLabel
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtCore import Qt

def colormap_to_qimage(cmap_name, width=256, height=20):
    """
    Convert a colorcet colormap to a horizontal swatch QImage.
    """
    cmap = cc.cm[cmap_name]
    # colorcet returns RGB tuples in 0–1 range → convert to uint8
    data = np.array([cmap(i) for i in np.linspace(0, 1, width)])
    data = (data[:, :3] * 255).astype(np.uint8)  # drop alpha if present

    # Repeat rows vertically to form a swatch
    img_array = np.repeat(data[np.newaxis, :, :], height, axis=0)

    # Convert to bytes for QImage
    h, w, _ = img_array.shape
    bytes_per_line = w * 3
    qimg = QImage(
        img_array.data,
        w,
        h,
        bytes_per_line,
        QImage.Format_RGB888
    )
    return qimg.copy()  # copy to detach from numpy buffer

def main():
    app = QApplication(sys.argv)

    cmap_name = 'fire'  # choose any colorcet colormap
    qimage = colormap_to_qimage(cmap_name)
    qpixmap = QPixmap.fromImage(qimage)

    label = QLabel()
    label.setPixmap(qpixmap)
    label.setAlignment(Qt.AlignCenter)
    label.show()

    sys.exit(app.exec())

if __name__ == "__main__":
    main()
