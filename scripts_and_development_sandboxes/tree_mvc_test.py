from PySide6.QtWidgets import (
    QApplication, QMainWindow, QTreeView, QWidget, QVBoxLayout
)
from PySide6.QtCore import Qt, QAbstractItemModel, QModelIndex


class TreeItem:
    def __init__(self, key, value, parent=None):
        self.key = key
        self.value = value
        self.parent_item = parent
        self.child_items = []

    def append_child(self, item):
        self.child_items.append(item)

    def child(self, row):
        return self.child_items[row]

    def child_count(self):
        return len(self.child_items)

    def column_count(self):
        return 2  # key and value

    def row(self):
        if self.parent_item:
            return self.parent_item.child_items.index(self)
        return 0

    def parent(self):
        return self.parent_item


class DictTreeModel(QAbstractItemModel):
    def __init__(self, data=None, parent=None):
        super().__init__(parent)
        self.root_item = TreeItem("Root", "")
        if data:
            self.setup_model_data(data, self.root_item)

    def setup_model_data(self, data, parent_item):
        if isinstance(data, dict):
            for key, value in data.items():
                if isinstance(value, (dict, list)):
                    item = TreeItem(str(key), "", parent_item)
                    parent_item.append_child(item)
                    self.setup_model_data(value, item)
                else:
                    item = TreeItem(str(key), str(value), parent_item)
                    parent_item.append_child(item)
        elif isinstance(data, list):
            for index, value in enumerate(data):
                if isinstance(value, (dict, list)):
                    item = TreeItem(f"[{index}]", "", parent_item)
                    parent_item.append_child(item)
                    self.setup_model_data(value, item)
                else:
                    item = TreeItem(f"[{index}]", str(value), parent_item)
                    parent_item.append_child(item)
        else:
            # Single value, not dict or list
            item = TreeItem(str(data), "", parent_item)
            parent_item.append_child(item)

    def columnCount(self, parent=QModelIndex()):
        return 2

    def rowCount(self, parent=QModelIndex()):
        if not parent.isValid():
            parent_item = self.root_item
        else:
            parent_item = parent.internalPointer()
        return parent_item.child_count()

    def index(self, row, column, parent=QModelIndex()):
        if not self.hasIndex(row, column, parent):
            return QModelIndex()

        if not parent.isValid():
            parent_item = self.root_item
        else:
            parent_item = parent.internalPointer()

        child_item = parent_item.child(row)
        if child_item:
            return self.createIndex(row, column, child_item)
        return QModelIndex()

    def parent(self, index):
        if not index.isValid():
            return QModelIndex()

        child_item = index.internalPointer()
        parent_item = child_item.parent()

        if parent_item == self.root_item or parent_item is None:
            return QModelIndex()

        return self.createIndex(parent_item.row(), 0, parent_item)

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid():
            return None

        item = index.internalPointer()

        if role == Qt.DisplayRole:
            if index.column() == 0:
                return item.key
            elif index.column() == 1:
                return item.value

        return None

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if orientation == Qt.Horizontal and role == Qt.DisplayRole:
            return ["Key", "Value"][section]
        return None

    def flags(self, index):
        if not index.isValid():
            return Qt.NoItemFlags
        return Qt.ItemIsEnabled | Qt.ItemIsSelectable

    def set_dict(self, data):
        self.beginResetModel()
        self.root_item = TreeItem("Root", "")
        self.setup_model_data(data, self.root_item)
        self.endResetModel()


class DictTreeViewer(QWidget):
    def __init__(self):
        super().__init__()
        self.tree_view = QTreeView()
        self.model = DictTreeModel()
        self.tree_view.setModel(self.model)

        layout = QVBoxLayout()
        layout.addWidget(self.tree_view)
        self.setLayout(layout)

    def set_data(self, new_dict):
        self.model.set_dict(new_dict)
        self.tree_view.expandAll()


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.viewer = DictTreeViewer()
        self.setCentralWidget(self.viewer)

        self.setWindowTitle("Nested Dict Viewer (Key + Value)")
        self.resize(600, 400)

        # Initial data
        data = {
            "Fruits": {
                "Citrus": ["Orange", "Lemon"],
                "Berries": ["Strawberry", "Blueberry"]
            },
            "Vegetables": {
                "Root": ["Carrot", "Beetroot"],
                "Leafy": ["Spinach", "Lettuce"]
            },
            "Colors": {
                "Primary": {"Red": "#FF0000", "Blue": "#0000FF"},
                "Secondary": ["Green", "Orange"]
            }
        }
        self.viewer.set_data(data)


if __name__ == "__main__":
    import sys

    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
