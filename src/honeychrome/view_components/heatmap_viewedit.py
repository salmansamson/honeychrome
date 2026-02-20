import sys
import numpy as np

from PySide6.QtCore import Qt, QAbstractTableModel, QModelIndex, QObject, QEvent, Slot, QSize, QTimer, QItemSelectionModel, QSignalBlocker
from PySide6.QtWidgets import QApplication, QTableView, QStyledItemDelegate, QLineEdit, QFrame, QVBoxLayout, QLabel, QHeaderView, QStyle, QAbstractItemView
from PySide6.QtGui import QColor, QPen

import pyqtgraph as pg
import colorcet as cc

from honeychrome.settings import heading_style, wheel_speed

# ---------------------------
# Model
# ---------------------------
class HeatmapModel(QAbstractTableModel):
    def __init__(self, is_dark, heatmap_range):
        super().__init__()
        self._data = None
        self.horizontal_headers = None
        self.vertical_headers = None
        self.heatmap_range = heatmap_range

        if is_dark:
            heatmap_colormap_name = 'bkr'
        else:
            heatmap_colormap_name = 'coolwarm'

        colors = cc.palette[heatmap_colormap_name]  # Get the colormap from Colorcet
        self.cmap = pg.ColorMap(pos=np.linspace(0.0, 1.0, len(colors)), color=colors)  # Convert Colorcet colormap to PyQtGraph's format

    def value_to_cet_color(self, value):
        vmin, vmax = self.heatmap_range
        t = (value - vmin) / (vmax - vmin)
        r, g, b, _ = self.cmap.map(np.array([t]))[0]
        return QColor(int(r), int(g), int(b))

    def update_data(self, data, horizontal_headers, vertical_headers):
        self.beginResetModel()  # Notify view that model is about to be reset
        self._data = np.array(data)
        self.horizontal_headers = horizontal_headers
        self.vertical_headers = vertical_headers
        self.endResetModel()  # Notify view that model has been reset

    def rowCount(self, parent=None):
        if self._data is not None:
            return self._data.shape[0]
        else:
            return 0

    def columnCount(self, parent=None):
        if self._data is not None:
            return self._data.shape[1]
        else:
            return 0

    def data(self, index, role):
        if not index.isValid():
            return None

        value = self._data[index.row(), index.column()]

        if role == Qt.DisplayRole:
            return f"{value:.3f}"

        if role == Qt.EditRole:
            return value

        if role == Qt.BackgroundRole:
            return self.value_to_cet_color(value)

        return None

    def setData(self, index, value, role):
        if role == Qt.EditRole:
            try:
                v = float(value)
            except ValueError:
                return False

            self._data[index.row(), index.column()] = v
            self.dataChanged.emit(index, index, [Qt.DisplayRole, Qt.BackgroundRole])
            return True
        return False

    def flags(self, index):
        r, c = index.row(), index.column()

        if r == c:  # hide & disable
            return Qt.ItemIsEnabled

        return Qt.ItemIsSelectable | Qt.ItemIsEditable | Qt.ItemIsEnabled

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if orientation == Qt.Horizontal and role == Qt.ToolTipRole:
            return self.horizontal_headers[section]

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
    def __init__(self, parent=None, enable_editor=False, disable_diagonal=False):
        super().__init__(parent)
        self.enable_editor = enable_editor
        self.disable_diagonal = disable_diagonal

    def createEditor(self, parent, option, index):
        if not self.enable_editor:
            return super().createEditor(parent, option, index)

        editor = QLineEdit(parent)
        return editor

    def setEditorData(self, editor, index):
        if self.enable_editor:
            val = index.model().data(index, Qt.EditRole)
            # editor.setText(str(val))
            editor.setText(f"{val:.3f}")
            editor.selectAll()
        else:
            super().setEditorData(editor, index)

    def paint(self, painter, option, index):
        if self.disable_diagonal:
            r, c = index.row(), index.column()

            # Hide diagonal: paint background color of table with no text
            if r == c:
                painter.fillRect(option.rect, option.palette.window())  # blank area
                return  # skip default painting

        # 1. Clear the "Selected" state so the default renderer
        # doesn't paint the blue background fill.
        custom_option = option
        is_selected = option.state & QStyle.State_Selected
        if is_selected:
            custom_option.state &= ~QStyle.State_Selected

        # 2. Draw the standard cell content (text, etc.)
        super().paint(painter, custom_option, index)

        # 3. Manually draw the border if the cell is selected
        if is_selected:
            painter.save()

            # Setup the pen (color and thickness)
            pen = QPen(QColor("#3498db"), 2)  # Modern Blue
            painter.setPen(pen)

            # Adjust the rect slightly so the border isn't clipped
            rect = option.rect.adjusted(1, 1, -1, -1)
            painter.drawRect(rect)

            painter.restore()

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
                return super().eventFilter(obj, event)

            old = self.model.data(index, Qt.EditRole)
            if old is None:
                return super().eventFilter(obj, event)

            # ignore if not selected
            selection_model = self.view.selectionModel()
            if not selection_model.isSelected(index):
                return super().eventFilter(obj, event)

            step = wheel_speed if event.angleDelta().y() > 0 else -wheel_speed
            new_value = float(old) + step

            self.model.setData(index, new_value, Qt.EditRole)
            return True  # consume wheel event

        return False



class ResizingTable(QTableView):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # No scrollbars
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        # fixed row height
        # Equal column widths
        self.horizontalHeader().setDefaultSectionSize(60)
        self.verticalHeader().setDefaultSectionSize(60)
        self.setWordWrap(True)

        #single selection
        # 1. Allow only one item to be selected at a time
        self.setSelectionMode(QAbstractItemView.SingleSelection)
        # 2. Ensure selection happens at the cell level (not the whole row)
        self.setSelectionBehavior(QAbstractItemView.SelectItems)

    def setModel(self, model):
        super().setModel(model)
        # Connect to model's dataChanged signal
        if model:
            model.layoutChanged.connect(self._on_model_changed)
            model.modelReset.connect(self._on_model_changed)

    def _on_model_changed(self):
        self.updateGeometry()

    def sizeHint(self):
        if not self.model() or self.model().rowCount() == 0 or self.model().columnCount() == 0:
            return super().sizeHint()

        # Get header sizes
        horizontal_header = self.horizontalHeader()
        vertical_header = self.verticalHeader()

        # Calculate total width: vertical header + all columns + frame
        width = (vertical_header.width() if vertical_header.isVisible() else 0)
        width += horizontal_header.length()

        # Calculate total height: horizontal header + all rows + frame
        height = (horizontal_header.height() if horizontal_header.isVisible() else 0)
        height += vertical_header.length()

        # Add frame width (usually 1px per side)
        frame_width = self.frameWidth() * 2

        # Check if horizontal scrollbar is visible and add its height
        horizontal_scrollbar = self.horizontalScrollBar()
        if horizontal_scrollbar and horizontal_scrollbar.isVisible():
            height += horizontal_scrollbar.height()

        # Check if vertical scrollbar is visible and add its width
        vertical_scrollbar = self.verticalScrollBar()
        if vertical_scrollbar and vertical_scrollbar.isVisible():
            width += vertical_scrollbar.width()

        return QSize(width + frame_width, height + frame_width)

# -----------------------------------------------------
# Main Application
# -----------------------------------------------------

class HeatmapViewEditor(QFrame):
    def __init__(self, bus, controller, process_key, is_dark, parent=None):
        super().__init__(parent)

        # connect
        self.bus = bus
        self.controller = controller
        self.process_key = process_key
        self.matrix = None
        if self.bus:
            self.bus.showSelectedProfiles.connect(self.show_selected_rows)

        self._timer = QTimer(self)
        self._timer.setInterval(500)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._emit_now)

        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)

        self.view = ResizingTable()
        self.title = None
        delegate = None
        if process_key == 'similarity_matrix':
            self.title = QLabel('Similarity Matrix')
            delegate = HeatmapDelegate(disable_diagonal=True)
            heatmap_range = (-1,1)
        elif process_key == 'hotspot_matrix':
            self.title = QLabel('Hotspot Matrix')
            delegate = HeatmapDelegate(disable_diagonal=True)
            heatmap_range = (-10,10)
        elif process_key == 'unmixing_matrix':
            self.title = QLabel('Unmixing Matrix')
            delegate = HeatmapDelegate()
            heatmap_range = (-1,1)
        elif self.process_key == 'spillover':
            self.title = QLabel('Spillover (Fine Tuning) Matrix: double click to edit, or click to select then roll scroll wheel')
            delegate = HeatmapDelegate(enable_editor=True, disable_diagonal=True)
            heatmap_range = (-0.5,0.5)

        self.layout.addWidget(self.title)
        self.title.setStyleSheet(heading_style)
        self.model = HeatmapModel(is_dark, heatmap_range)
        self.view.setModel(self.model)
        self.view.setItemDelegate(delegate)

        # Wheel editor
        if process_key == 'spillover':
            self.wheel_handler = WheelEditor(self.view, self.model)
            self.view.viewport().installEventFilter(self.wheel_handler)
            self.model.dataChanged.connect(self._on_edit)
            self.view.selectionModel().currentChanged.connect(self.selected_cell_changed)
            if self.bus:
                self.bus.requestUpdateProcessHists.connect(self.refresh_heatmap)
                self.bus.spilloverSelectedCellChanged.connect(self.set_selected_cell)


        self.layout.addWidget(self.view)

        self.refresh_heatmap()

    @Slot(list)
    def show_selected_rows(self, selected_label_list):
        if self.model.vertical_headers:
            if selected_label_list:
                pass
            else:
                selected_label_list = self.model.vertical_headers

            for row, label in enumerate(self.model.vertical_headers):
                visible = label in selected_label_list
                self.view.setRowHidden(row, not visible)
            self.view.updateGeometry()

    def _emit_now(self):
        self.controller.reapply_fine_tuning()
        self.bus.requestUpdateProcessHists.emit()

    def _on_edit(self, index1, index2, role):
        if index1 == index2:
            r = index1.row()
            c = index1.column()
            self.matrix[r][c] = self.model._data[r][c]
            self._timer.start()

    def show_context_menu(self, event):
        # Empty method to completely disable context menu
        pass

    def refresh_heatmap(self):
        # insert key in case of backward compatibility problems
        if self.process_key not in self.controller.experiment.process:
            self.controller.experiment.process[self.process_key] = None

        self.matrix = self.controller.experiment.process[self.process_key]

        if self.matrix:
            if self.process_key == 'similarity_matrix' or self.process_key == 'hotspot_matrix':
                pnn = self.controller.experiment.settings['unmixed']['event_channels_pnn']
                fl_ids = self.controller.experiment.settings['unmixed']['fluorescence_channel_ids']
                fl_pnn = [pnn[n] for n in fl_ids]
                horizontal_headers = fl_pnn
                vertical_headers = fl_pnn
                self.model.update_data(self.matrix, horizontal_headers, vertical_headers)
                self.setVisible(True)
            elif self.process_key == 'unmixing_matrix':
                pnn = self.controller.experiment.settings['raw']['event_channels_pnn']
                fl_ids = self.controller.filtered_raw_fluorescence_channel_ids
                horizontal_headers = [pnn[n] for n in fl_ids]
                pnn = self.controller.experiment.settings['unmixed']['event_channels_pnn']
                fl_ids = self.controller.experiment.settings['unmixed']['fluorescence_channel_ids']
                vertical_headers = [pnn[n] for n in fl_ids]
                self.model.update_data(self.matrix, horizontal_headers, vertical_headers)
                self.setVisible(True)
            elif self.process_key == 'spillover':
                pnn = self.controller.experiment.settings['unmixed']['event_channels_pnn']
                fl_ids = self.controller.experiment.settings['unmixed']['fluorescence_channel_ids']
                fl_pnn = [pnn[n] for n in fl_ids]
                horizontal_headers = fl_pnn
                vertical_headers = fl_pnn

                # if there is a current selection, look it up and set it after the model is reset
                index = self.view.selectionModel().currentIndex()
                if index.isValid() and vertical_headers and horizontal_headers:
                    selected_row_chan = vertical_headers[index.row()]
                    selected_col_chan = horizontal_headers[index.column()]

                self.model.update_data(self.matrix, horizontal_headers, vertical_headers)
                self.setVisible(True)

                if index.isValid() and self.process_key == 'spillover':
                    QTimer.singleShot(0, lambda: self.set_selected_cell(selected_row_chan, selected_col_chan))

        else:
            self.setVisible(False)


    @Slot(QModelIndex, QModelIndex)
    def selected_cell_changed(self, current, previous):
        if current.isValid():
            row_chan = self.model.vertical_headers[current.row()]
            col_chan = self.model.horizontal_headers[current.column()]
            self.bus.spilloverSelectedCellChanged.emit(row_chan, col_chan)

    @Slot(str, str)
    def set_selected_cell(self, row_chan, col_chan):#
        if row_chan in self.model.vertical_headers and col_chan in self.model.horizontal_headers:
            self.view.selectionModel().setCurrentIndex(
                self.model.index(self.model.vertical_headers.index(row_chan),
                                 self.model.horizontal_headers.index(col_chan)
                                 ), QItemSelectionModel.ClearAndSelect)
        else:
            with QSignalBlocker(self.view.selectionModel()):
                self.view.selectionModel().clearSelection()
                self.view.selectionModel().clearCurrentIndex()  # Optional: also clears the focus anchor




if __name__ == '__main__':
    from PySide6.QtWidgets import QApplication
    import sys

    app = QApplication(sys.argv)

    from honeychrome.controller import Controller
    from pathlib import Path
    from event_bus import EventBus

    bus = EventBus()
    kc = Controller()
    base_directory = Path.home() / 'spectral_cytometry'
    experiment_name = base_directory / '20240620 Spectral Symposium-poor cell unmixed'
    experiment_path = experiment_name.with_suffix('.kit')
    kc.load_experiment(experiment_path) # note this loads first sample too and runs calculate all histograms and statistics

    frame = HeatmapViewEditor(bus, kc, 'similarity_matrix')
    # frame = HeatmapViewEditor(bus, kc, 'unmixing_matrix')
    # frame = HeatmapViewEditor(bus, kc, 'spillover')

    # Plot the profiles
    frame.refresh_heatmap()
    frame.show()

    frame.resize(950, 600)
    sys.exit(app.exec())

