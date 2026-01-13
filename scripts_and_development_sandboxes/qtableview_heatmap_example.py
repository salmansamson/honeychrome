import sys
import numpy as np

from PySide6.QtCore import Qt, QAbstractTableModel, QModelIndex, QObject, QEvent
from PySide6.QtWidgets import QApplication, QTableView, QStyledItemDelegate, QLineEdit
from PySide6.QtGui import QColor

import pyqtgraph as pg


# ---------------------------
# ColorCET colormap
# ---------------------------
cmap = pg.colormap.get('CET-L8')

def value_to_cet_color(value, vmin, vmax):
    if vmax == vmin:
        t = 0.5
    else:
        t = (value - vmin) / (vmax - vmin)
    r, g, b, _ = cmap.map(np.array([t]))[0]
    return QColor(int(r), int(g), int(b))



# ---------------------------
# Model
# ---------------------------
class HeatmapModel(QAbstractTableModel):
    def __init__(self, data, horizontal_headers, vertical_headers):
        super().__init__()
        self.data_array = data.astype(float)
        self.horizontal_headers = horizontal_headers
        self.vertical_headers = vertical_headers

    def rowCount(self, parent=None):
        return self.data_array.shape[0]

    def columnCount(self, parent=None):
        return self.data_array.shape[1]

    def data(self, index, role):
        if not index.isValid():
            return None

        value = self.data_array[index.row(), index.column()]

        if role == Qt.DisplayRole:
            return f"{value:.2f}"

        if role == Qt.EditRole:
            return value

        if role == Qt.BackgroundRole:
            vmin = float(self.data_array.min())
            vmax = float(self.data_array.max())
            return value_to_cet_color(value, vmin, vmax)

        return None

    def setData(self, index, value, role):
        if role == Qt.EditRole:
            try:
                v = float(value)
            except ValueError:
                return False

            self.data_array[index.row(), index.column()] = v
            self.dataChanged.emit(index, index,
                                  [Qt.DisplayRole, Qt.BackgroundRole])
            return True
        return False

    def flags(self, index):
        r, c = index.row(), index.column()

        if r == c:  # hide & disable
            return Qt.ItemIsEnabled

        return Qt.ItemIsSelectable | Qt.ItemIsEditable | Qt.ItemIsEnabled

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if role == Qt.DisplayRole:
            if orientation == Qt.Horizontal:
                return self.horizontal_headers[section]
            elif orientation == Qt.Vertical:
                return self.vertical_headers[section]
        return None

# ---------------------------
# Delegate: select text on editing
# ---------------------------
class HeatmapDelegate(QStyledItemDelegate):
    def createEditor(self, parent, option, index):
        editor = QLineEdit(parent)
        return editor

    def setEditorData(self, editor, index):
        val = index.model().data(index, Qt.EditRole)
        editor.setText(str(val))
        editor.selectAll()

    def paint(self, painter, option, index):
        r, c = index.row(), index.column()

        # Hide diagonal: paint background color of table with no text
        if r == c:
            painter.fillRect(option.rect, option.palette.window())  # blank area
            return  # skip default painting

        # Normal painting for all other cells
        super().paint(painter, option, index)

# ---------------------------
# Wheel handler (event filter)
# ---------------------------
class WheelEditor(QObject):
    def __init__(self, view, model):
        super().__init__()
        self.view = view
        self.model = model

    def eventFilter(self, obj, event):
        if event.type() == QEvent.Wheel:
            pos = event.position().toPoint()
            index = self.view.indexAt(pos)

            if not index.isValid():
                return False

            # ignore diagonal cells
            if index.row() == index.column():
                return True

            old = self.model.data(index, Qt.EditRole)
            if old is None:
                return True

            step = 0.1 if event.angleDelta().y() > 0 else -0.1
            new_value = float(old) + step

            self.model.setData(index, new_value, Qt.EditRole)
            return True  # consume wheel event

        return False


# -----------------------------------------------------
# Main Application
# -----------------------------------------------------


data = np.random.randn(5, 64)

app = QApplication(sys.argv)

view = QTableView()
delegate = HeatmapDelegate()
view.setItemDelegate(delegate)

# Define headers and data
horizontal_headers = ['Product', 'Category', 'Price']
vertical_headers = ['Item 1', 'Item 2', 'Item 3']

data = np.array([
    [1, 4, 3],
    [2.5, 5, 7],
    [6, 8.2, 9]
])

# Create and set model
model = HeatmapModel(data, horizontal_headers, vertical_headers)
view.setModel(model)

# Equal column widths
view.horizontalHeader().setDefaultSectionSize(60)
view.verticalHeader().setDefaultSectionSize(60)

# Wheel editor
wheel_handler = WheelEditor(view, model)
view.viewport().installEventFilter(wheel_handler)

view.setWindowTitle("Editable Heatmap with Wheel Editing, CET Colormap")
view.show()

sys.exit(app.exec())
