import sys
from PySide6.QtWidgets import QApplication, QMainWindow, QTreeView, QStyle
from PySide6.QtCore import QAbstractItemModel, QModelIndex, Qt
from PySide6.QtGui import QIcon

from view_components.icon_loader import icon


class IconItem:
    def __init__(self, name, icon=None):
        self.name = name
        self.icon = icon  # This is a QIcon!
        self.children = []
        self.parent = None

    def add_child(self, child):
        child.parent = self
        self.children.append(child)


class IconTreeModel(QAbstractItemModel):
    def __init__(self):
        super().__init__()
        self._root_item = IconItem("Root")

    def setup_data(self, style):
        # Create items with QIcons
        documents = IconItem("Documents", icon('rectangle'))
        documents.add_child(IconItem("report.pdf", style.standardIcon(QStyle.SP_FileIcon)))
        documents.add_child(IconItem("notes.txt", style.standardIcon(QStyle.SP_FileIcon)))

        pictures = IconItem("Pictures", style.standardIcon(QStyle.SP_DirIcon))
        pictures.add_child(IconItem("photo1.jpg", style.standardIcon(QStyle.SP_FileIcon)))
        pictures.add_child(IconItem("photo2.png", style.standardIcon(QStyle.SP_FileIcon)))

        system = IconItem("System", style.standardIcon(QStyle.SP_ComputerIcon))
        system.add_child(IconItem("Local Disk (C:)", style.standardIcon(QStyle.SP_DriveHDIcon)))
        system.add_child(IconItem("Local Disk (D:)", style.standardIcon(QStyle.SP_DriveHDIcon)))

        # Add to root
        self._root_item.add_child(documents)
        self._root_item.add_child(pictures)
        self._root_item.add_child(system)

    def index(self, row, column, parent=QModelIndex()):
        if not self.hasIndex(row, column, parent):
            return QModelIndex()

        parent_item = self._root_item if not parent.isValid() else parent.internalPointer()

        if row < len(parent_item.children):
            return self.createIndex(row, column, parent_item.children[row])
        return QModelIndex()

    def parent(self, index):
        if not index.isValid():
            return QModelIndex()

        child_item = index.internalPointer()
        parent_item = child_item.parent

        if parent_item == self._root_item:
            return QModelIndex()

        return self.createIndex(self.get_row(parent_item), 0, parent_item)

    def get_row(self, item):
        if item.parent:
            return item.parent.children.index(item)
        return 0

    def rowCount(self, parent=QModelIndex()):
        parent_item = self._root_item if not parent.isValid() else parent.internalPointer()
        return len(parent_item.children)

    def columnCount(self, parent=QModelIndex()):
        return 1

    def data(self, index, role=Qt.ItemDataRole):
        if not index.isValid():
            return None

        item = index.internalPointer()

        row = index.row()
        col = index.column()

        if role == Qt.DisplayRole:
            return item.name
        elif role == Qt.DecorationRole:
            # ONLY return icons for column 0 (Name column)
            if col == 0:
                return item.icon

        return None


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Hierarchical QAbstractItemModel with QIcons")
        self.resize(400, 500)

        # Create model
        model = IconTreeModel()
        model.setup_data(self.style())

        # Create and setup tree view
        tree_view = QTreeView()
        tree_view.setModel(model)
        tree_view.expandAll()

        self.setCentralWidget(tree_view)


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())