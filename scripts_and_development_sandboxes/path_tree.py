from PySide6.QtCore import Qt, QModelIndex, QAbstractItemModel


class TreeItem:
    def __init__(self, name, parent=None):
        self.name = name
        self.parent_item = parent
        self.children = []

    def child(self, row):
        return self.children[row]

    def child_count(self):
        return len(self.children)

    def row(self):
        if self.parent_item:
            return self.parent_item.children.index(self)
        return 0

    def append_child(self, item):
        self.children.append(item)

    def get_or_create_child(self, name):
        for c in self.children:
            if c.name == name:
                return c
        new_child = TreeItem(name, parent=self)
        self.children.append(new_child)
        return new_child


class PathTreeModel(QAbstractItemModel):
    def __init__(self, paths, parent=None):
        super().__init__(parent)
        self.root = TreeItem("")

        for path in paths:
            self._add_path(path)

    # ---------------------------------------------------------
    # Build the hierarchy
    # ---------------------------------------------------------
    def _add_path(self, path):
        parts = path.replace("\\", "/").split("/")
        node = self.root
        for part in parts:
            if part.strip():
                node = node.get_or_create_child(part)

    # ---------------------------------------------------------
    # Required Model API
    # ---------------------------------------------------------
    def index(self, row, column, parent=QModelIndex()):
        if not self.hasIndex(row, column, parent):
            return QModelIndex()

        parent_item = parent.internalPointer() if parent.isValid() else self.root
        child_item = parent_item.child(row)
        if child_item:
            return self.createIndex(row, column, child_item)
        return QModelIndex()

    def parent(self, index):
        if not index.isValid():
            return QModelIndex()

        child_item = index.internalPointer()
        parent_item = child_item.parent_item

        if parent_item == self.root or parent_item is None:
            return QModelIndex()

        return self.createIndex(parent_item.row(), 0, parent_item)

    def rowCount(self, parent=QModelIndex()):
        parent_item = parent.internalPointer() if parent.isValid() else self.root
        return parent_item.child_count()

    def columnCount(self, parent=QModelIndex()):
        return 1

    def data(self, index, role):
        if not index.isValid():
            return None
        if role in (Qt.DisplayRole, Qt.EditRole):
            return index.internalPointer().name
        return None

    def flags(self, index):
        if not index.isValid():
            return Qt.NoItemFlags
        return Qt.ItemIsEnabled | Qt.ItemIsSelectable


if __name__ == "__main__":
    import sys
    from PySide6.QtWidgets import QApplication, QTreeView

    app = QApplication(sys.argv)

    paths = [
        "src/main.cpp",
        "src/util/helpers.cpp",
        "src/util/helpers.hpp",
        "docs/readme.md",
        "assets/icons/logo.png",
    ]

    model = PathTreeModel(paths)
    view = QTreeView()
    view.setModel(model)
    view.setWindowTitle("Path Tree")
    view.resize(400, 300)
    view.show()

    sys.exit(app.exec())
