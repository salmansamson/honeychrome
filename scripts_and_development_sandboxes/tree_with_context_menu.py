import sys
from PySide6.QtWidgets import (QApplication, QMainWindow, QTreeView, QMenu, QMessageBox, QInputDialog, QLineEdit,
                               QStyledItemDelegate, QStyle)
from PySide6.QtCore import QAbstractItemModel, QModelIndex, Qt, QEvent
from PySide6.QtGui import QAction


class EditableTreeModel(QAbstractItemModel):
    def __init__(self):
        super().__init__()
        # Data: (name, size, type, is_folder)
        self._data = [("Documents", "2.3 GB", "Folder", True), ("Pictures", "1.5 GB", "Folder", True),
            ("report.pdf", "2.4 MB", "PDF File", False), ("photo.jpg", "4.2 MB", "Image File", False),
            ("script.py", "15 KB", "Python File", False), ]

    def index(self, row, column, parent=QModelIndex()):
        if not self.hasIndex(row, column, parent) or parent.isValid():
            return QModelIndex()
        return self.createIndex(row, column, row)

    def parent(self, index):
        return QModelIndex()

    def rowCount(self, parent=QModelIndex()):
        return len(self._data) if not parent.isValid() else 0

    def columnCount(self, parent=QModelIndex()):
        return 4  # Hidden type column

    def data(self, index, role=Qt.ItemDataRole):
        if not index.isValid():
            return None

        row = index.row()
        col = index.column()
        name, size, file_type, is_folder = self._data[row]

        if role == Qt.DisplayRole:
            if col == 0:
                return name
            elif col == 1:
                return size
            elif col == 2:
                return file_type

        elif role == Qt.EditRole:
            if col == 0: return name  # Return data for editing

        elif role == Qt.UserRole:
            return self._data[row]  # Return all data

        return None

    def setData(self, index, value, role=Qt.EditRole):
        if not index.isValid() or role != Qt.EditRole:
            return False

        row = index.row()
        col = index.column()

        if col == 0:  # Only allow editing the name column
            # Update the data
            old_data = self._data[row]
            self._data[row] = (value, old_data[1], old_data[2], old_data[3])

            # Emit dataChanged signal to update the view
            self.dataChanged.emit(index, index, [Qt.DisplayRole, Qt.EditRole])
            return True

        return False

    def flags(self, index):
        if not index.isValid():
            return Qt.NoItemFlags

        flags = super().flags(index)

        # Make only the first column editable
        if index.column() == 0:
            flags |= Qt.ItemIsEditable

        return flags

    def headerData(self, section, orientation, role=Qt.ItemDataRole):
        if orientation == Qt.Horizontal and role == Qt.DisplayRole:
            headers = ["Name", "Size", "Type"]
            if section < len(headers):
                return headers[section]
        return None


class TreeViewWithRename(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("TreeView with Double-Click Rename")
        self.resize(600, 400)

        self.model = EditableTreeModel()
        self.tree_view = QTreeView()
        self.tree_view.setModel(self.model)

        # Hide the type column (column 3)
        self.tree_view.setColumnHidden(3, True)

        # Enable editing on double-click
        self.tree_view.setEditTriggers(QTreeView.DoubleClicked | QTreeView.SelectedClicked)

        # Enable context menu
        self.tree_view.setContextMenuPolicy(Qt.CustomContextMenu)
        self.tree_view.customContextMenuRequested.connect(self.show_context_menu)

        # Set column widths
        self.tree_view.setColumnWidth(0, 200)
        self.tree_view.setColumnWidth(1, 100)
        self.tree_view.setColumnWidth(2, 150)

        self.setCentralWidget(self.tree_view)

    def show_context_menu(self, position):
        index = self.tree_view.indexAt(position)
        menu = QMenu(self)

        if index.isValid():
            item_data = self.model.data(index.siblingAtColumn(0), Qt.UserRole)
            if item_data:
                name, size, file_type, is_folder = item_data

                # Add rename action to context menu
                rename_action = QAction(f"Rename '{name}'", self)
                rename_action.triggered.connect(lambda: self.start_rename(index))
                menu.addAction(rename_action)

                menu.addSeparator()

                if is_folder:
                    open_action = QAction(f"Open '{name}'", self)
                    open_action.triggered.connect(lambda: self.open_item(index))
                    menu.addAction(open_action)
                else:
                    open_action = QAction(f"Open '{name}'", self)
                    open_action.triggered.connect(lambda: self.open_item(index))
                    menu.addAction(open_action)

                delete_action = QAction(f"Delete '{name}'", self)
                delete_action.triggered.connect(lambda: self.delete_item(index))
                menu.addAction(delete_action)
        else:
            new_folder_action = QAction("New Folder", self)
            new_folder_action.triggered.connect(self.new_folder)
            menu.addAction(new_folder_action)

            refresh_action = QAction("Refresh", self)
            refresh_action.triggered.connect(self.refresh_view)
            menu.addAction(refresh_action)

        menu.exec(self.tree_view.viewport().mapToGlobal(position))

    def start_rename(self, index):
        """Start editing the item (rename)"""
        # Ensure we're editing the name column (column 0)
        name_index = index.siblingAtColumn(0)
        self.tree_view.edit(name_index)

    def open_item(self, index):
        name = self.get_item_name(index)
        QMessageBox.information(self, "Open", f"Opening: {name}")

    def delete_item(self, index):
        name = self.get_item_name(index)
        reply = QMessageBox.question(self, "Delete", f"Delete '{name}'?", QMessageBox.Yes | QMessageBox.No)
        if reply == QMessageBox.Yes:
            QMessageBox.information(self, "Deleted", f"Deleted: {name}")

    def new_folder(self):
        QMessageBox.information(self, "New Folder", "Creating new folder")

    def refresh_view(self):
        QMessageBox.information(self, "Refresh", "Refreshing view")

    def get_item_name(self, index):
        return self.model.data(index.siblingAtColumn(0), Qt.DisplayRole)


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = TreeViewWithRename()
    window.show()
    sys.exit(app.exec())