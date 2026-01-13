import sys
import numpy as np
from PySide6.QtWidgets import QApplication, QMainWindow, QTableView, QVBoxLayout, QWidget
from PySide6.QtCore import QAbstractTableModel, Qt, QModelIndex, QSize
from PySide6.QtGui import QColor, QPixmap, QPainter, QImage, QPalette
import colorcet as cc

resolution = 200

class HeatmapTableModel(QAbstractTableModel):
    def __init__(self, data=None):
        super().__init__()
        self._data = data if data is not None else self.generate_sample_data()
        self._pixmap_cache = {}
        self._pixmap_size = QSize(100, 100)

        app = QApplication.instance()
        palette = app.palette()
        base_color = palette.color(QPalette.ColorRole.Base)
        is_dark = base_color.value() < 128

        self.colormap_name = "rainbow4"
        self.colormap = self.get_colorcet_colormap(self.colormap_name)

        if is_dark:
            background_colour = QColor(0,0,0,255)
        else:
            background_colour = QColor(255,255,255,255)
        self.colormap[0] = background_colour
        pass

    def get_colorcet_colormap(self, name):
        """Get a colormap from colorcet and convert to Qt-friendly format"""
        cmap_colors = getattr(cc, name)
        qt_colors = []
        for color in cmap_colors:
            if isinstance(color, str):
                qt_colors.append(QColor(color))
            else:
                r, g, b = [int(c * 255) for c in color]
                qt_colors.append(QColor(r, g, b))
        return qt_colors

    def generate_sample_data(self):
        """Generate sample data with some zero/low values to see transparency"""
        data = []
        patterns = ['random', 'gradient', 'circle', 'stripes', 'sparse']

        for i in range(6):
            row = []
            for j in range(5):
                pattern = patterns[(i + j) % len(patterns)]

                if pattern == 'random':
                    heatmap_data = np.random.rand(resolution, resolution)

                elif pattern == 'gradient':
                    x = np.linspace(0, 1, resolution)
                    y = np.linspace(0, 1, resolution)
                    xx, yy = np.meshgrid(x, y)
                    heatmap_data = (xx + yy) / 2

                elif pattern == 'circle':
                    x = np.linspace(-1, 1, resolution)
                    y = np.linspace(-1, 1, resolution)
                    xx, yy = np.meshgrid(x, y)
                    heatmap_data = 1 - np.sqrt(xx ** 2 + yy ** 2)
                    heatmap_data = np.clip(heatmap_data, 0, 1)

                elif pattern == 'stripes':
                    x = np.linspace(0, 1, resolution)
                    y = np.linspace(0, 1, resolution)
                    xx, yy = np.meshgrid(x, y)
                    heatmap_data = np.sin(xx * np.pi * 4) * 0.5 + 0.5

                elif pattern == 'sparse':
                    # Create sparse data with many zeros
                    heatmap_data = np.random.rand(resolution, resolution) * 0.3  # Mostly low values
                    # Add some high values
                    high_indices = np.random.choice(400, 40, replace=False)
                    heatmap_data.flat[high_indices] = np.random.rand(40) * 0.7 + 0.3

                row.append(heatmap_data)
            data.append(row)
        return data

    def rowCount(self, parent=QModelIndex()):
        return len(self._data)

    def columnCount(self, parent=QModelIndex()):
        return len(self._data[0]) if self._data else 0

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid():
            return None

        if role == Qt.DecorationRole:
            return self.get_cached_pixmap(index)

        elif role == Qt.ToolTipRole:
            heatmap_data = self._data[index.row()][index.column()]
            low_values = np.sum(heatmap_data < self.background_threshold)
            total_values = heatmap_data.size
            return (f"Min: {np.min(heatmap_data):.3f}\n"
                    f"Max: {np.max(heatmap_data):.3f}\n"
                    f"Mean: {np.mean(heatmap_data):.3f}\n"
                    f"Transparent pixels: {low_values}/{total_values}")

        return None

    def get_cached_pixmap(self, index):
        cache_key = (index.row(), index.column())
        if cache_key not in self._pixmap_cache:
            heatmap_data = self._data[index.row()][index.column()]
            pixmap = self.create_heatmap_pixmap(heatmap_data)
            self._pixmap_cache[cache_key] = pixmap
        return self._pixmap_cache[cache_key]

    def create_heatmap_pixmap(self, data):
        """Fastest approach using pure NumPy operations"""
        height, width = data.shape

        # Normalize
        data_min = np.min(data)
        data_max = np.max(data)
        data_range = data_max - data_min

        if data_range > 0:
            normalized = (data - data_min) / data_range
        else:
            normalized = np.full_like(data, 0.5)

        indices = (normalized * (len(self.colormap) - 1)).astype(np.int32)
        indices = np.clip(indices, 0, len(self.colormap) - 1)

        # Create color lookup table
        color_table = np.array([[c.red(), c.green(), c.blue(), c.alpha()] for c in self.colormap], dtype=np.uint8)

        # Vectorized lookup
        rgb_array = color_table[indices]

        # Convert to ARGB32 format expected by QImage
        argb_array = np.zeros((height, width), dtype=np.uint32)
        argb_array = (rgb_array[:, :, 3].astype(np.uint32) << 24) | (rgb_array[:, :, 0].astype(np.uint32) << 16) | (
                    rgb_array[:, :, 1].astype(np.uint32) << 8) | (rgb_array[:, :, 2].astype(np.uint32))

        scaled_image = QImage(argb_array.data, width, height, QImage.Format_ARGB32).scaled(self._pixmap_size, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        # Create QImage from memory
        return QPixmap.fromImage(scaled_image)

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Heatmap Table View")
        self.setGeometry(100, 100, 1000, 700)

        self.table_view = QTableView()
        self.model = HeatmapTableModel()
        self.table_view.setModel(self.model)

        self.table_view.verticalHeader().setDefaultSectionSize(120)
        self.table_view.horizontalHeader().setDefaultSectionSize(120)

        central_widget = QWidget()
        layout = QVBoxLayout(central_widget)
        layout.addWidget(self.table_view)
        self.setCentralWidget(central_widget)

        self.pregenerate_pixmaps()

    def pregenerate_pixmaps(self):
        for row in range(self.model.rowCount()):
            for col in range(self.model.columnCount()):
                self.model.get_cached_pixmap(self.model.index(row, col))


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()

    # Example: Change transparency settings
    # window.model.set_transparency(True, 0.2)  # Make values < 0.2 transparent
    # window.model.set_transparency(False)  # Disable transparency

    sys.exit(app.exec())



##

