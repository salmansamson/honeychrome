import numpy as np

from PySide6.QtCore import Qt, QAbstractTableModel, QModelIndex, QObject, QEvent, Slot, QSize, QTimer, QSettings
from PySide6.QtWidgets import QTableView, QStyledItemDelegate, QFrame, QVBoxLayout, QLabel, QApplication, QComboBox, QHBoxLayout
from PySide6.QtGui import QColor, QPalette, QImage, QPixmap

import colorcet as cc

import settings
from controller_components.functions import define_process_plots
from view_components.busy_cursor import with_busy_cursor

# ---------------------------
# Model
# ---------------------------
class HeatmapGridModel(QAbstractTableModel):
    def __init__(self, controller, is_dark):
        super().__init__()
        self._data = []
        self.horizontal_headers = []
        self.vertical_headers = []
        self.controller = controller

        self._pixmap_cache = {}
        self._pixmap_size = QSize(settings.tile_size_nxn_grid_retrieved, settings.tile_size_nxn_grid_retrieved)

        self.colormap = self.get_colorcet_colormap(settings.colourmap_name_retrieved)

        if is_dark:
            background_colour = QColor(0,0,0,255)
        else:
            background_colour = QColor(255,255,255,255)
        self.colormap[0] = background_colour

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


    def update_data(self, data, horizontal_headers, vertical_headers):
        self.beginResetModel()  # Notify view that model is about to be reset
        self._data = data
        self._pixmap_cache = {}
        self.horizontal_headers = horizontal_headers
        self.vertical_headers = vertical_headers
        self.endResetModel()  # Notify view that model has been reset

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
            r = index.row()
            c = index.column()


            return ("Spillover:\n"
                    f"{self.vertical_headers[r]} --- {self.horizontal_headers[c]}: {self.controller.experiment.process['spillover'][r][c]:0.3f}\n"
                    f"{self.horizontal_headers[c]} --- {self.vertical_headers[r]}: {self.controller.experiment.process['spillover'][c][r]:0.3f}\n"
                    )

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
        data_max = np.max(data)

        if data_max > 0:
            normalized = np.flipud(data / data_max)
        else:
            normalized = np.full_like(data, 0.5)

        indices = (normalized * (len(self.colormap) - 1)).astype(np.int32)
        indices = np.clip(indices, 0, len(self.colormap) - 1)

        # Create color lookup table
        color_table = np.array([[c.red(), c.green(), c.blue(), c.alpha()] for c in self.colormap], dtype=np.uint8)

        # Vectorized lookup
        rgb_array = color_table[indices]

        # Convert to ARGB32 format expected by QImage
        argb_array = (rgb_array[:, :, 3].astype(np.uint32) << 24) | (rgb_array[:, :, 0].astype(np.uint32) << 16) | (
                    rgb_array[:, :, 1].astype(np.uint32) << 8) | (rgb_array[:, :, 2].astype(np.uint32))

        scaled_image = QImage(argb_array.data, width, height, QImage.Format_ARGB32).scaled(self._pixmap_size, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        # Create QImage from memory
        return QPixmap.fromImage(scaled_image)

    def setData(self, index, value, role):
        if role == Qt.EditRole:
            try:
                v = float(value)
            except ValueError:
                return False

            self._data[index.row(), index.column()] = v
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
    def __init__(self, parent=None):
        super().__init__(parent)

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
    def __init__(self, view, controller, bus):
        super().__init__()
        self.view = view
        self.controller = controller
        self.bus = bus

        self._timer = QTimer(self)
        self._timer.setInterval(500)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._emit_now)

    def _emit_now(self):
        self.bus.spilloverChanged.emit()

    def eventFilter(self, obj, event):
        if event.type() == QEvent.Wheel:
            pos = event.position().toPoint()
            index = self.view.indexAt(pos)

            if not index.isValid():
                return False

            r = index.row()
            c = index.column()
            # ignore diagonal cells
            if r == c:
                return True

            old = self.controller.experiment.process['spillover'][r][c]
            step = 0.01 if event.angleDelta().y() > 0 else -0.01
            new_value = float(old) + step
            self.controller.experiment.process['spillover'][r][c] = new_value
            self.controller.reapply_fine_tuning()
            self._timer.start()

            return True  # consume wheel event

        return False



class ResizingTable(QTableView):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # No scrollbars
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        # fixed row height
        # Equal column widths
        self.horizontalHeader().setDefaultSectionSize(settings.tile_size_nxn_grid_retrieved)
        self.verticalHeader().setDefaultSectionSize(settings.tile_size_nxn_grid_retrieved)
        self.setWordWrap(True)

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

class NxNGrid(QFrame):
    def __init__(self, bus, controller, is_dark=False, parent=None):
        super().__init__(parent)

        # connect
        self.bus = bus
        self.controller = controller
        self.heatmaps = None
        self.bus.showSelectedProfiles.connect(self.show_selected_rows)

        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)

        self.view = ResizingTable()
        self.title = QLabel('NxN Plots: roll scroll wheel for fine tuning (row to column), hover to inspect (row to column, column to row)')
        delegate = HeatmapDelegate()

        self.layout.addWidget(self.title)
        self.title.setStyleSheet(settings.heading_style)
        source_gate_combo_layout = QHBoxLayout()
        self.source_gate_combo = QComboBox(self)
        self.source_gate_combo.currentTextChanged.connect(self.change_process_source_gate)
        self.source_gate_combo.addItem("Select Gate:")  # placeholder for "no selection"
        source_gate_combo_layout.addWidget(self.source_gate_combo)
        source_gate_combo_layout.addStretch()
        self.layout.addLayout(source_gate_combo_layout)

        self.model = HeatmapGridModel(self.controller, is_dark)
        self.view.setModel(self.model)
        self.view.setItemDelegate(delegate)

        # Wheel editor
        self.wheel_handler = WheelEditor(self.view, self.controller, self.bus)
        self.view.viewport().installEventFilter(self.wheel_handler)

        self.layout.addWidget(self.view)

        self.refresh_heatmaps()
        self.refresh_source_combo('unmixed') # populate the source combo with all unmixed gates

        if self.bus is not None:
            self.bus.histsStatsRecalculated.connect(self.refresh_heatmaps)
            self.bus.spilloverChanged.connect(self.refresh_heatmaps)
            self.bus.changedGatingHierarchy.connect(self.refresh_source_combo)
            self.bus.spectralProcessRefreshed.connect(self.refresh_source_combo)

    @Slot(list)
    def show_selected_rows(self, selected_label_list):
        if self.model.vertical_headers:
            if selected_label_list:
                pass
            else:
                selected_label_list = self.vertical_headers

            for row, label in enumerate(self.vertical_headers):
                visible = label in selected_label_list
                self.view.setRowHidden(row, not visible)
            self.view.updateGeometry()

    def show_context_menu(self, event):
        # Empty method to completely disable context menu
        pass

    @Slot(str, str)
    def refresh_source_combo(self, mode='unmixed', gate=None): #gate not used, just for connecting signal
        if mode == 'unmixed':
            if self.controller.data_for_cytometry_plots_process['gating'] and self.controller.data_for_cytometry_plots_process['plots']:
                gate_names = ['root'] + [g[0] for g in self.controller.data_for_cytometry_plots_process['gating'].get_gate_ids()]
                current_source_combo_items = [self.source_gate_combo.itemText(i) for i in range(self.source_gate_combo.count())]
                if set(current_source_combo_items) != set(gate_names):
                    self.source_gate_combo.clear()
                    self.source_gate_combo.addItems(gate_names)
                    index = self.source_gate_combo.findText(self.controller.data_for_cytometry_plots_process['plots'][0]['source_gate'])
                    if index >= 0:
                        self.source_gate_combo.setCurrentIndex(index)

    @Slot(str)
    def change_process_source_gate(self, source_gate):
        if self.controller.experiment.settings['unmixed']['fluorescence_channels']:
            process_plots = define_process_plots(self.controller.experiment.settings['unmixed']['fluorescence_channels'], source_gate=source_gate)
            self.controller.data_for_cytometry_plots_process.update({'plots': process_plots})
            if self.controller.current_mode == 'process':
                if source_gate:
                    self.controller.initialise_data_for_cytometry_plots()

    @Slot(str)
    def refresh_heatmaps(self, mode='process'):
        if mode == 'process':
            pnn = self.controller.experiment.settings['unmixed']['event_channels_pnn']
            if pnn is not None:
                self.setVisible(True)
                fl_ids = self.controller.experiment.settings['unmixed']['fluorescence_channel_ids']
                fl_pnn = [pnn[n] for n in fl_ids]
                self.horizontal_headers = fl_pnn
                self.vertical_headers = fl_pnn

                plots = self.controller.data_for_cytometry_plots_process['plots']
                if plots:
                    histograms = self.controller.data_for_cytometry_plots_process['histograms']
                    if not histograms:
                        histograms += [np.zeros((settings.tile_size_nxn_grid_retrieved,settings.tile_size_nxn_grid_retrieved)) for plot in plots]

                    self.heatmaps = []
                    for x in fl_pnn:
                        row = []
                        for y in fl_pnn:
                            if x != y:
                                index = [plots.index(plot) for plot in plots if plot['type'] == 'hist2d' and plot['channel_x'] == x and plot['channel_y'] == y][0]
                                row.append(histograms[index])
                            else:
                                row.append(None)
                        self.heatmaps.append(row)

                    # self.view.setModel(self.model)
                    self.model.update_data(self.heatmaps, self.horizontal_headers, self.vertical_headers)
            else:
                self.setVisible(False)



if __name__ == '__main__':
    import sys

    app = QApplication(sys.argv)

    from controller import Controller
    from pathlib import Path
    from event_bus import EventBus

    bus = EventBus()
    kc = Controller()
    base_directory = Path.home() / 'spectral_cytometry'
    experiment_name = base_directory / '20240620 Spectral Symposium-poor cell unmixed'
    experiment_path = experiment_name.with_suffix('.kit')
    kc.load_experiment(experiment_path)
    kc.set_mode('Spectral Process')
    kc.load_sample(kc.experiment.samples['single_stain_controls'][0])

    frame = NxNGrid(bus, kc)

    # Plot the profiles
    frame.refresh_heatmaps()
    frame.show()

    sys.exit(app.exec())

