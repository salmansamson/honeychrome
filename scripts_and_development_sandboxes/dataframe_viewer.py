"""
PySide6 program to display and edit a list-of-dicts data model named `spectral_controls`.

Features:
- Displays a list of dictionaries with keys:
    ['label', 'control type', 'tubename', 'path', 'particle type', 'peak channel', 'gate label']
- Only `label` column is editable (free text)
- Dropdowns for `control type`, `particle type`, and `peak channel` always visible
- Selecting a control type triggers an action (prints to console)
- Sorting and filtering enabled via QSortFilterProxyModel
- Row selection and bulk actions: Select All, Select None, Add Row, Delete Selected
- In-place editing (no export needed)
- Refreshes comboboxes properly when adding rows
- Triggers a general action whenever any table data changes

Run: python pyside6_spectral_controls.py
"""

from __future__ import annotations
import sys
from typing import List, Any, Dict
from PySide6 import QtCore, QtWidgets
from PySide6.QtCore import Qt, QModelIndex
from PySide6.QtWidgets import (QApplication, QMainWindow, QTableView, QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
                               QStyledItemDelegate, QComboBox, QLineEdit, QMessageBox, QFrame, )

COLUMNS = [
    "label",
    "control type",
    "tubename",
    "path",
    "particle type",
    "peak channel",
    "gate label",
]
CONTROL_TYPES = ["spectral control", "channel assignment"]
PARTICLE_TYPES = ["beads", "cells"]
PEAK_CHANNELS = list(range(1, 17))

class ListTableModel(QtCore.QAbstractTableModel):
    dataChangedSignal = QtCore.Signal()

    def __init__(self, data: List[Dict[str, Any]], parent=None):
        super().__init__(parent)
        self._data = data

    def rowCount(self, parent=QModelIndex()):
        return len(self._data)

    def columnCount(self, parent=QModelIndex()):
        return len(COLUMNS)

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid():
            return None
        row, col = index.row(), index.column()
        key = COLUMNS[col]
        val = self._data[row].get(key, None)
        if role in (Qt.DisplayRole, Qt.EditRole):
            return "" if val is None else str(val)
        return None

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if role != Qt.DisplayRole:
            return None
        if orientation == Qt.Horizontal:
            return COLUMNS[section]
        return section + 1

    def flags(self, index):
        if not index.isValid():
            return Qt.ItemIsEnabled
        colname = COLUMNS[index.column()]
        base = Qt.ItemIsSelectable | Qt.ItemIsEnabled
        if colname == "label":
            base |= Qt.ItemIsEditable
        return base

    def setData(self, index, value, role=Qt.EditRole):
        if role != Qt.EditRole or not index.isValid():
            return False
        row, col = index.row(), index.column()
        key = COLUMNS[col]
        if key == "peak channel":
            try:
                value = int(value)
            except ValueError:
                return False
        self._data[row][key] = value
        self.dataChanged.emit(index, index, [Qt.DisplayRole, Qt.EditRole])
        self.dataChangedSignal.emit()
        return True

    def insertRows(self, position, rows=1, parent=QModelIndex()):
        self.beginInsertRows(QModelIndex(), position, position + rows - 1)
        for _ in range(rows):
            empty = {c: None for c in COLUMNS}
            self._data.insert(position, empty)
        self.endInsertRows()
        return True

    def removeRows(self, position, rows=1, parent=QModelIndex()):
        if rows <= 0:
            return False
        self.beginRemoveRows(QModelIndex(), position, position + rows - 1)
        del self._data[position:position + rows]
        self.endRemoveRows()
        self.dataChangedSignal.emit()
        return True

    def delete_rows_by_indices(self, indices: List[int]):
        if not indices:
            return
        to_drop = sorted(set(indices), reverse=True)
        self.beginResetModel()
        for i in to_drop:
            del self._data[i]
        self.endResetModel()
        self.dataChangedSignal.emit()

class LabelDelegate(QStyledItemDelegate):
    def createEditor(self, parent, option, index):
        return QLineEdit(parent)

    def setEditorData(self, editor, index):
        val = index.model().data(index, Qt.EditRole)
        editor.setText(val)

    def setModelData(self, editor, model, index):
        text = editor.text()
        model.setData(index, text, Qt.EditRole)

class MainWindow(QFrame):
    def __init__(self, data: List[Dict[str, Any]]):
        super().__init__()
        self.model = ListTableModel(data)

        # Proxy for sorting/filtering
        self.proxy = QtCore.QSortFilterProxyModel(self)
        self.proxy.setSourceModel(self.model)
        self.proxy.setFilterCaseSensitivity(Qt.CaseInsensitive)
        self.proxy.setFilterKeyColumn(-1)

        self.view = QTableView()
        self.view.setModel(self.proxy)
        self.view.setSelectionBehavior(QTableView.SelectRows)
        self.view.setSelectionMode(QTableView.ExtendedSelection)
        self.view.horizontalHeader().setStretchLastSection(True)
        self.view.setSortingEnabled(False)

        self.label_delegate = LabelDelegate()
        self.view.setItemDelegateForColumn(COLUMNS.index("label"), self.label_delegate)

        self.model.dataChangedSignal.connect(self._on_any_edit)

        # Filter bar
        self.filter_edit = QLineEdit()
        self.filter_edit.setPlaceholderText("Filter table...")
        self.filter_edit.textChanged.connect(self.proxy.setFilterFixedString)

        # Buttons
        select_all_btn = QPushButton("Select All")
        select_none_btn = QPushButton("Select None")
        add_row_btn = QPushButton("Add Row")
        delete_btn = QPushButton("Delete Selected")

        select_all_btn.clicked.connect(self.view.selectAll)
        select_none_btn.clicked.connect(self.view.clearSelection)
        add_row_btn.clicked.connect(self.add_row)
        delete_btn.clicked.connect(self.delete_selected_rows)

        btn_layout = QHBoxLayout()
        btn_layout.addWidget(select_all_btn)
        btn_layout.addWidget(select_none_btn)
        btn_layout.addWidget(add_row_btn)
        btn_layout.addWidget(delete_btn)
        btn_layout.addStretch()

        layout = QVBoxLayout()
        layout.addWidget(self.filter_edit)
        layout.addWidget(self.view)
        layout.addLayout(btn_layout)
        self.setLayout(layout)

        # Build combobox widgets after layout setup
        self.refresh_comboboxes()

    def refresh_comboboxes(self):
        for row in range(self.model.rowCount()):
            self._add_comboboxes_to_row(row)

    def _add_comboboxes_to_row(self, row):
        # Control type
        idx_ctrl = self.model.index(row, COLUMNS.index("control type"))
        cb_ctrl = QComboBox()
        cb_ctrl.addItems(CONTROL_TYPES)
        current_val = self.model.data(idx_ctrl, Qt.EditRole)
        if current_val:
            idx = cb_ctrl.findText(str(current_val))
            if idx >= 0:
                cb_ctrl.setCurrentIndex(idx)
        cb_ctrl.currentTextChanged.connect(lambda val, r=row: self._on_control_type_changed(val, r))
        self.view.setIndexWidget(self.proxy.mapFromSource(idx_ctrl), cb_ctrl)

        # Particle type
        idx_part = self.model.index(row, COLUMNS.index("particle type"))
        cb_part = QComboBox()
        cb_part.addItems(PARTICLE_TYPES)
        current_val = self.model.data(idx_part, Qt.EditRole)
        if current_val:
            idx = cb_part.findText(str(current_val))
            if idx >= 0:
                cb_part.setCurrentIndex(idx)
        cb_part.currentTextChanged.connect(lambda val, r=row: self._set_model_value(idx_part, val))
        self.view.setIndexWidget(self.proxy.mapFromSource(idx_part), cb_part)

        # Peak channel
        idx_peak = self.model.index(row, COLUMNS.index("peak channel"))
        cb_peak = QComboBox()
        cb_peak.addItems([str(x) for x in PEAK_CHANNELS])
        current_val = self.model.data(idx_peak, Qt.EditRole)
        if current_val:
            idx = cb_peak.findText(str(current_val))
            if idx >= 0:
                cb_peak.setCurrentIndex(idx)
        cb_peak.currentTextChanged.connect(lambda val, r=row: self._set_model_value(idx_peak, val))
        self.view.setIndexWidget(self.proxy.mapFromSource(idx_peak), cb_peak)

    def _set_model_value(self, idx, val):
        self.model.setData(idx, val, Qt.EditRole)

    def add_row(self):
        pos = self.model.rowCount()
        self.model.insertRows(pos, 1)
        self.refresh_comboboxes()
        self.view.scrollToBottom()

    def delete_selected_rows(self):
        sel = self.view.selectionModel().selectedRows()
        if not sel:
            QMessageBox.information(self, "No selection", "No rows selected to delete.")
            return
        indices = sorted([self.proxy.mapToSource(s).row() for s in sel])
        reply = QMessageBox.question(self, "Confirm delete", f"Delete {len(indices)} row(s)?", QMessageBox.Yes | QMessageBox.No)
        if reply == QMessageBox.Yes:
            self.model.delete_rows_by_indices(indices)
            self.refresh_comboboxes()

    def _on_control_type_changed(self, value, row):
        idx = self.model.index(row, COLUMNS.index("control type"))
        self.model.setData(idx, value)
        if value == "spectral control":
            print(f"Row {row}: Spectral control selected - performing calibration...")
        elif value == "channel assignment":
            print(f"Row {row}: Channel assignment selected - updating mapping...")

    def _on_any_edit(self):
        print("Table edited: data changed.")

def make_example_data() -> List[Dict[str, Any]]:
    return [
        {"label": "Control A", "control type": "spectral control", "tubename": "Tube1", "path": "/data/tube1.fcs", "particle type": "cells", "peak channel": 3, "gate label": "Gate1"},
        {"label": "Control B", "control type": "channel assignment", "tubename": "Tube2", "path": "/data/tube2.fcs", "particle type": "beads", "peak channel": 7, "gate label": "Gate2"},
    ]

def launch_app(data):
    app = QApplication(sys.argv)
    win = MainWindow(data)
    win.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    if "spectral_controls" in globals() and isinstance(globals()["spectral_controls"], list):
        data_in = globals()["spectral_controls"]
    else:
        data_in = make_example_data()
        spectral_controls = data_in  # shared editable reference
    launch_app(data_in)
