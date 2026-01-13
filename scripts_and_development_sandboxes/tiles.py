from PySide6.QtWidgets import QApplication, QWidget, QGridLayout, QLabel
from PySide6.QtGui import QColor, QPalette
from PySide6.QtCore import Qt
import sys


class GridWidget(QWidget):
    def __init__(self, n_columns, tiles):
        super().__init__()
        self.n_columns = n_columns
        self.tiles = tiles
        self.init_ui()

    def init_ui(self):
        layout = QGridLayout()
        layout.setSpacing(5)

        # Track which grid cells are occupied
        occupied = []
        row = 0

        def fits(row, col, w, h):
            """Check if tile of size (w,h) fits at (row,col)."""
            for r in range(row, row + h):
                for c in range(col, col + w):
                    if c >= self.n_columns or (r, c) in occupied:
                        return False
            return True

        def occupy(row, col, w, h):
            """Mark cells as occupied."""
            for r in range(row, row + h):
                for c in range(col, col + w):
                    occupied.append((r, c))

        # Place each tile
        for tile_data in self.tiles:
            w = tile_data.get("width", 1)
            h = tile_data.get("height", 1)
            color = tile_data.get("color", "#cccccc")
            label_text = tile_data.get("label", "")

            placed = False
            # Try to find first spot where it fits
            while not placed:
                for col in range(self.n_columns):
                    if fits(row, col, w, h):
                        # Create tile widget
                        tile = QLabel(label_text)
                        tile.setAlignment(Qt.AlignCenter)
                        tile.setAutoFillBackground(True)
                        palette = tile.palette()
                        palette.setColor(QPalette.Window, QColor(color))
                        tile.setPalette(palette)

                        # Add widget spanning w columns × h rows
                        layout.addWidget(tile, row, col, h, w)
                        occupy(row, col, w, h)
                        placed = True
                        break
                if not placed:
                    row += 1  # move down a row and try again

        self.setLayout(layout)


if __name__ == "__main__":
    app = QApplication(sys.argv)

    # Example tile definitions: width, height are in grid cells
    tiles = [
        {"width": 2, "height": 1, "color": "#e74c3c", "label": "A"},
        {"width": 1, "height": 2, "color": "#2ecc71", "label": "B"},
        {"width": 1, "height": 1, "color": "#3498db", "label": "C"},
        {"width": 1, "height": 1, "color": "#3498db", "label": "C1"},
        {"width": 1, "height": 1, "color": "#3498db", "label": "C2"},
        {"width": 1, "height": 1, "color": "#f1c40f", "label": "D"},
        {"width": 2, "height": 2, "color": "#9b59b6", "label": "E"},
        {"width": 1, "height": 1, "color": "#1abc9c", "label": "F"},
    ]

    window = GridWidget(n_columns=4, tiles=tiles)
    window.setWindowTitle("Grid-Filling Tiles (integer cell units)")
    window.resize(500, 400)
    window.show()

    sys.exit(app.exec())
