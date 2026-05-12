import json
import sys
import re
from datetime import datetime
from typing import List, Any, Dict
from PySide6 import QtCore
from PySide6.QtCore import Qt, QModelIndex, QTimer, QThread, Slot, QObject, QEvent, QSize, Signal
from PySide6.QtWidgets import (QApplication, QFrame, QVBoxLayout, QHBoxLayout, QTableView, QPushButton, QStyledItemDelegate, QComboBox, QLineEdit, QMessageBox, QHeaderView, QLabel, QWidget, QCheckBox)

from honeychrome.controller_components.functions import raw_gates_list
from honeychrome.controller_components.spectral_controller import SpectralAutoGenerator, ProfileUpdater, SpectralCleaner, spectral_library
from honeychrome.controller_components.spectral_functions import sanitise_control_in_place, _find_default_unstained
from honeychrome.view_components.icon_loader import icon
from honeychrome.settings import spectral_model_column_labels, heading_style, INTERNAL_NEGATIVE_SENTINEL
from honeychrome.controller_components.gml_functions_mod_from_flowkit import _rename_channel_in_gml

import logging
logger = logging.getLogger(__name__)

COLUMNS = list(spectral_model_column_labels.keys())
CONTROL_TYPES = ["Single Stained Spectral Control", "Single Stained Spectral Control from Library", "Channel Assignment"]
PARTICLE_TYPES = ["Beads", "Cells"]
NEGATIVE_TYPES = ["Internal Negative", "Unstained Negative"]



class ResizingTable(QTableView):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # No scrollbars
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        # multiselect
        self.setSelectionBehavior(QTableView.SelectRows)
        self.setSelectionMode(QTableView.ExtendedSelection)

        # fixed row height
        self.verticalHeader().setSectionResizeMode(QHeaderView.Fixed)
        self.setWordWrap(False)

        # no sorting, turn on row indices
        self.setSortingEnabled(False)
        self.verticalHeader().setVisible(True)


    def sizeHint(self):
        """
        Always compute the exact size needed for all rows and columns.
        """
        self.resizeRowsToContents()
        self.resizeColumnsToContents()

        width = self.verticalHeader().width() + self.horizontalHeader().length()
        height = self.horizontalHeader().height() + self.verticalHeader().length()

        # Add a small margin
        return QSize(width + 4, max([height + 4, 60]))

    def resizeToFit(self):
        self.resizeRowsToContents()

        total_height = 0

        # Add height of all rows
        for row in range(self.model().rowCount()):
            total_height += self.rowHeight(row)

        # Add horizontal header height
        total_height += self.horizontalHeader().height()

        # Add frame width (borders)
        total_height += 2 * self.frameWidth()

        # Apply the new height
        self.setMinimumHeight(total_height)
        # self.setMaximumHeight(total_height)

    # def wheelEvent(self, event):
    #     # We tell Qt we didn't handle this.
    #     # It will then look at the parent widget to handle it.
    #     event.ignore()


class _RecalcWorker(QObject):
    finished = Signal()

    def __init__(self, profile_updater, controls, search_results):
        super().__init__()
        self._profile_updater = profile_updater
        self._controls = controls
        self._search_results = search_results

    @Slot()
    def run(self):
        self._profile_updater.flush()
        for control in self._controls:
            self._profile_updater.generate(control, self._search_results)
        self.finished.emit()

class WheelBlocker(QObject):
    def eventFilter(self, obj, event):
        if event.type() == QEvent.Wheel:
            event.ignore()
            return True    # Block wheel event
        return super().eventFilter(obj, event)

class ListTableModel(QtCore.QAbstractTableModel):
    dataEditedSignal = QtCore.Signal(int, int) # changed to track cosmetic vs function changes
    dataDeletedSignal = QtCore.Signal(list)

    def __init__(self, data: List[Dict[str, Any]], fluorescence_channels_pnn, parent=None):
        super().__init__(parent)
        self._data = data
        self.fluorescence_channels_pnn = fluorescence_channels_pnn

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
            if key in ("use_cleaned", "af_remove"):
                return None   # checkbox widget handles display; suppress cell text
            return "" if val is None else str(val)
        return None

    _COLUMN_TOOLTIPS = {
        'universal_negative_name': (
            'The unstained sample used as the negative reference for this control.\n'
            'To add a sample here: right-click any sample in the Sample panel\n'
            'and choose "Mark as Unstained".'
        ),
    }

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if orientation == Qt.Horizontal:
            if role == Qt.DisplayRole:
                return spectral_model_column_labels[COLUMNS[section]]
            if role == Qt.ToolTipRole:
                return self._COLUMN_TOOLTIPS.get(COLUMNS[section])
        if role == Qt.DisplayRole:
            return section + 1
        return None

    def flags(self, index):
        if not index.isValid():
            return Qt.ItemIsEnabled
        colname = COLUMNS[index.column()]
        base = Qt.ItemIsSelectable | Qt.ItemIsEnabled
        if colname in ("label", "antigen"):
            base |= Qt.ItemIsEditable
        return base

    def setData(self, index, value, role=Qt.EditRole):
        if role != Qt.EditRole or not index.isValid():
            return False
        row, col = index.row(), index.column()
        key = COLUMNS[col]
        # if key == "gate_channel":
        #     try:
        #         value = int(value)
        #     except ValueError:
        #         return False
        self._data[row][key] = value
        self.dataChanged.emit(index, index, [Qt.DisplayRole, Qt.EditRole])
        # changed to return col so we can track cosmetic vs functional changes
        self.dataEditedSignal.emit(row, col)
        return True

    def insertRow(self, position, parent=QModelIndex()):
        self.beginInsertRows(QModelIndex(), position, position)
        new_row = {c: None for c in COLUMNS}

        # if entering channel assignment, give the next unused raw channel
        if position > 0:
            if self._data[-1]['control_type'] == 'Channel Assignment':
                new_row['control_type'] = 'Channel Assignment'
                unused_raw_channels = self.unused_raw_channels()
                new_row['gate_channel'] = unused_raw_channels[0] if self.unused_raw_channels() else None

        self._data.insert(position, new_row)
        self.endInsertRows()
        # self.dataEditedSignal.emit(position)
        return True

    def unused_raw_channels(self, exception=None):
        allowed_channels = set(self.fluorescence_channels_pnn) - ({row['gate_channel'] for row in self._data} - {exception})
        return [c for c in self.fluorescence_channels_pnn if c in allowed_channels]

    def removeRows(self, position, rows=1, parent=QModelIndex()):
        if rows <= 0:
            return False
        self.beginRemoveRows(QModelIndex(), position, position + rows - 1)
        labels = []
        for i in range(position, position + rows):
            labels.append(self._data[i]['label'])
        del self._data[position:position + rows]
        self.endRemoveRows()
        self.dataDeletedSignal.emit(labels)
        return True

    # this is the one that actually seems to be used
    def delete_rows_by_indices(self, indices: List[int]):
        if not indices:
            return
        to_drop = sorted(set(indices), reverse=True)
        self.beginResetModel()
        labels = []
        for i in to_drop:
            labels.append(self._data[i]['label'])
            del self._data[i]
        self.endResetModel()
        self.dataDeletedSignal.emit(labels)

class LabelDelegate(QStyledItemDelegate):
    def createEditor(self, parent, option, index):
        return QLineEdit(parent)

    def setEditorData(self, editor, index):
        val = index.model().data(index, Qt.EditRole)
        editor.setText(val)

    def setModelData(self, editor, model, index):
        text = editor.text()
        model.setData(index, text, Qt.EditRole)

class SpectralControlsEditor(QFrame):
    def __init__(self, bus, controller, parent=None):
        super().__init__(parent)

        # connect
        self.bus = bus
        self.controller = controller

        # initialise data
        self.fluorescence_channels_pnn = []
        self.update_fluorescence_channels_pnn()
        self.model = ListTableModel(self.controller.experiment.process['spectral_model'], self.fluorescence_channels_pnn)
        self.samples = self.controller.experiment.samples
        self.raw_gating = self.controller.raw_gating

        self.proxy = QtCore.QSortFilterProxyModel(self)
        self.proxy.setSourceModel(self.model)
        self.proxy.setFilterCaseSensitivity(Qt.CaseInsensitive)
        self.proxy.setFilterKeyColumn(-1)

        self.view = ResizingTable()
        self.view.setModel(self.proxy)
        self.bus.spectralModelUpdated.connect(self.view.resizeToFit)
        self.bus.spectralControlAdded.connect(self.view.resizeToFit) #extends the table as autogeneration runs... looks interesting but a bit wonky
        self.view.selectionModel().selectionChanged.connect(self._show_selected_profiles)

        # Different resize modes for different columns
        # Column 0: label
        # Column 1, 2, 3...: control_type particle_type gate_channel gate_label
        # Column 4: sample_name
        # Column 5: gate_label
        # Column 6: universal_negative_name
        # ssr review: we have a problem here with width. consider adding horizontal scrollbar
        header = self.view.horizontalHeader()
        header.setMinimumSectionSize(100)
        header.setStretchLastSection(True)
        header.setSectionResizeMode(0, QHeaderView.Interactive)   # label
        header.setSectionResizeMode(1, QHeaderView.Interactive)   # antigen
        header.setSectionResizeMode(2, QHeaderView.ResizeToContents)  # control_type
        header.setSectionResizeMode(3, QHeaderView.ResizeToContents)  # particle_type
        header.setSectionResizeMode(4, QHeaderView.ResizeToContents)  # gate_channel
        header.setSectionResizeMode(5, QHeaderView.ResizeToContents)  # sample_name
        header.setSectionResizeMode(6, QHeaderView.ResizeToContents)  # gate_label
        header.setSectionResizeMode(7, QHeaderView.Stretch)           # universal_negative_name
        header.setSectionResizeMode(8, QHeaderView.ResizeToContents)  # use_cleaned
        header.setSectionResizeMode(9, QHeaderView.ResizeToContents)  # af_remove

        self.label_delegate = LabelDelegate()
        self.view.setItemDelegateForColumn(COLUMNS.index("label"), self.label_delegate)
        self.antigen_delegate = LabelDelegate()
        self.view.setItemDelegateForColumn(COLUMNS.index("antigen"), self.antigen_delegate)

        self.model.dataDeletedSignal.connect(self._on_delete_controls)

        # Debounce rapid edits and guard against re-entrant generate calls
        self._pending_update_index = None
        self._update_timer = QTimer()
        self._update_timer.setSingleShot(True)
        self._update_timer.setInterval(300)
        self._update_timer.timeout.connect(self._do_update_control)
        self.model.dataEditedSignal.connect(self._on_update_control)

        self.filter_edit = QLineEdit()
        self.filter_edit.setPlaceholderText("Filter table...")
        self.filter_edit.textChanged.connect(self.proxy.setFilterFixedString)

        btn_top_layout = QHBoxLayout()
        self.auto_generate_button = QPushButton(icon('sparkles'), "Auto generate spectral controls")
        self.auto_generate_button.setToolTip('Loop through all single stained control samples (cells and beads, prioritising cells); \nautomatically each control with positive/negative gates in the relevant channel. \nAny previous controls will be cleared.')

        self.negatives_combo = QComboBox()
        self.negatives_combo.addItems(['Using unstained negative', 'Using internal negatives'])
        self.fluorescence_channel_filter_combo = QComboBox()
        self.fluorescence_channel_filter_combo.addItems(['Using area channels only', 'Using all fluorescence channels'])
        self.update_combos()
        self.bus.spectralModelUpdated.connect(self.update_combos)

        self.force_recalc_btn = QPushButton(icon('refresh'), "Recalculate")
        self.force_recalc_btn.setToolTip('Recalculate the unmixing matrix; reset spillover and unmixed plots and gates. \n(Useful if the control data has been replaced or control gates have moved under the same names.) \nDoes not change the spectral controls table.')

        self.clean_controls_btn = QPushButton(icon('sparkles'), "Clean Controls")
        self.clean_controls_btn.setToolTip(
            'Run the cleaning pipeline for all cell controls that have a Universal Negative assigned:\n'
            '  • Saturation exclusion\n'
            '  • Brightest-event selection\n'
            '  • Scatter matching\n'
            '  • AF removal (per-control, if "Remove AF" is ticked)\n'
            'Once complete, each control will have a "Use Cleaned" checkbox.\n'
            'Cleaned controls use RLM profile extraction by default.'
        )
        self.clean_controls_btn.clicked.connect(self._on_clean_controls)

        btn_top_layout.addWidget(self.auto_generate_button)
        btn_top_layout.addWidget(self.negatives_combo)
        btn_top_layout.addWidget(self.fluorescence_channel_filter_combo)
        btn_top_layout.addWidget(self.force_recalc_btn)
        btn_top_layout.addWidget(self.clean_controls_btn)
        btn_top_layout.addStretch()

        self.add_row_btn = QPushButton(icon('plus'), "Add Control")
        self.select_all_btn = QPushButton("Select All")
        self.select_none_btn = QPushButton("Select None")
        self.delete_btn = QPushButton("Delete Selected")

        self.auto_generate_button.clicked.connect(self.auto_generate)
        self.negatives_combo.currentTextChanged.connect(self.set_negative_type)
        self.fluorescence_channel_filter_combo.currentTextChanged.connect(self.set_fluorescence_channel_filter)
        self.force_recalc_btn.clicked.connect(self._on_force_recalc)
        self.add_row_btn.clicked.connect(self.add_row)
        self.select_all_btn.clicked.connect(self.view.selectAll)
        self.select_none_btn.clicked.connect(self.view.clearSelection)
        self.delete_btn.clicked.connect(self.delete_selected_rows)

        btn_layout = QHBoxLayout()
        btn_layout.addWidget(self.add_row_btn)
        btn_layout.addWidget(self.select_all_btn)
        btn_layout.addWidget(self.select_none_btn)
        btn_layout.addWidget(self.delete_btn)
        btn_layout.addStretch()

        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        title = QLabel("Spectral Model Editor")
        layout.addWidget(title)
        title.setStyleSheet(heading_style)
        layout.addWidget(QLabel("Note: editing this table resets unmixed cytometry (plots, gates and fine-tuning (spillover) matrix)"))
        layout.addLayout(btn_top_layout)
        layout.addWidget(self.filter_edit)
        layout.addWidget(self.view)
        layout.addLayout(btn_layout)
        self.setLayout(layout)

        # Build combobox widgets after layout setup
        self.refresh_comboboxes()
        self.thread = None
        self.spectral_auto_generator = None
        self.profile_updater = ProfileUpdater(self.controller, self.bus)
        self.spectral_library_search_results = None

    def update_fluorescence_channels_pnn(self):
        event_channels_pnn = self.controller.experiment.settings['raw']['event_channels_pnn']
        fluorescence_channel_ids = self.controller.filtered_raw_fluorescence_channel_ids
        self.fluorescence_channels_pnn.clear()
        self.fluorescence_channels_pnn.extend([event_channels_pnn[i] for i in fluorescence_channel_ids])

    def set_negative_type(self):
        if self.negatives_combo.currentText() == 'Using unstained negative':
            self.controller.experiment.process['negative_type'] = 'unstained'
            self.negatives_combo.setToolTip('Negative set to "Neg Unstained" gate on Unstained sample')
            # Pre-populate universal_negative_name for any control that has none set.
            # Beads get the sentinel unconditionally; cells get it only if no Unstained
            # sample exists to auto-assign.
            default_unstained = _find_default_unstained(self.samples['all_samples'])
            # Also check manually-tagged unstained samples as a fallback
            if not default_unstained:
                unstained_paths = self.samples.get('unstained_samples', [])
                if unstained_paths:
                    default_unstained = self.samples['all_samples'].get(unstained_paths[0])
            for control in self.model._data:
                if control.get('control_type') == 'Single Stained Spectral Control':
                    if not control.get('universal_negative_name'):
                        if control.get('particle_type') == 'Cells' and default_unstained:
                            control['universal_negative_name'] = default_unstained
                        else:
                            control['universal_negative_name'] = INTERNAL_NEGATIVE_SENTINEL
            self.model.layoutChanged.emit()
        else:
            self.controller.experiment.process['negative_type'] = 'internal'
            self.negatives_combo.setCurrentText('Using internal negatives')
            self.negatives_combo.setToolTip('Negative set to bottom percentile of each control sample')
        logger.info(f'SpectralModelEditor: set negative type to {self.controller.experiment.process['negative_type']}')
        self._update_universal_negative_column_visibility()
        # Defer recalculation until after the signal handler returns and the Qt
        # event loop is back in a clean state — calling _on_force_recalc() directly
        # here causes a hard crash via the busy cursor thread mechanism.
        # ssr review: are you sure this is necessary? the original intention was only to recalc if the recalc button pressed after changing this selection
        QTimer.singleShot(0, self._on_force_recalc)

    def set_fluorescence_channel_filter(self):
        if self.model.rowCount():
            reply = QMessageBox.question(self,
                                         f"Change to {self.fluorescence_channel_filter_combo.currentText()}",
                                         f"This will clear the spectral model. Are you sure you wish to continue?",
                                         QMessageBox.Yes | QMessageBox.No)
            if reply == QMessageBox.Yes:
                self.model.delete_rows_by_indices(list(range(len(self.model._data))))
            else:
                self.fluorescence_channel_filter_combo.blockSignals(True)
                self.update_combos()
                self.fluorescence_channel_filter_combo.blockSignals(False)
                return

        if self.fluorescence_channel_filter_combo.currentText() == 'Using all fluorescence channels':
            self.controller.experiment.process['fluorescence_channel_filter'] = 'all_fluorescence'
            self.fluorescence_channel_filter_combo.setToolTip('Including both area and height channels in spectral model')
        else:
            self.controller.experiment.process['fluorescence_channel_filter'] = 'area_only'
            self.fluorescence_channel_filter_combo.setToolTip('Ignoring height channels in spectral model')
        logger.info(f'SpectralModelEditor: set fluorescence channel filter to {self.controller.experiment.process['fluorescence_channel_filter']}')

        if self.bus:
            self.bus.spectralModelUpdated.emit()
            self.bus.showSelectedProfiles.emit(None)

    def update_combos(self):
        if self.controller.experiment.process['negative_type'] == 'unstained':
            self.negatives_combo.setCurrentText('Using unstained negative')
            self.negatives_combo.setToolTip('Negative set to "Neg Unstained" gate on Unstained sample')
        elif self.controller.experiment.process['negative_type'] == 'internal':
            self.negatives_combo.setCurrentText('Using internal negatives')
            self.negatives_combo.setToolTip('Negative set to bottom percentile of each control sample')

        if self.controller.experiment.process['fluorescence_channel_filter'] == 'area_only':
            self.fluorescence_channel_filter_combo.setCurrentText('Using area channels only')
            self.fluorescence_channel_filter_combo.setToolTip('Ignoring height channels in spectral model')
        elif self.controller.experiment.process['fluorescence_channel_filter'] == 'all_fluorescence':
            self.fluorescence_channel_filter_combo.setCurrentText('Using all fluorescence channels')
            self.fluorescence_channel_filter_combo.setToolTip('Including both area and height channels in spectral model')

        self._update_universal_negative_column_visibility()

    # ssr review: should use_cleaned and af_remove also be hidden if internal neg?
    def _update_universal_negative_column_visibility(self):
        """Hide the Universal Negative column when using internal negatives.
        The underlying data is preserved — hiding is purely visual."""
        col_idx = COLUMNS.index("universal_negative_name")
        using_unstained = self.controller.experiment.process.get('negative_type') == 'unstained'
        if using_unstained:
            self.view.horizontalHeader().showSection(col_idx)
        else:
            self.view.horizontalHeader().hideSection(col_idx)


    def refresh_comboboxes(self):
        for row in range(self.model.rowCount()):
            self._add_comboboxes_to_row(row)

    def _add_or_replace_combobox_if_enabled(self, idx, should_have_combobox, items):
        proxy_index = self.proxy.mapFromSource(idx)

        # remove existing index widget (if any)
        old_widget = self.view.indexWidget(proxy_index)
        if old_widget is not None:
            old_widget.deleteLater()
            self.view.setIndexWidget(proxy_index, None)

        # now safely create and add a new combobox (if needed)
        if should_have_combobox:
            cb = QComboBox()
            cb.installEventFilter(WheelBlocker(cb))
            cb.setFocusPolicy(Qt.FocusPolicy.ClickFocus)
            cb.addItems(items)
            self.view.setIndexWidget(proxy_index, cb)

            current_val = self.model.data(idx, Qt.EditRole)
            i = cb.findText(str(current_val))
            if i >= 0:
                cb.setCurrentIndex(i)

            cb.currentTextChanged.connect(lambda val, i=idx: self.model.setData(i, val))


    def _add_comboboxes_to_row(self, row):
        current_control_list = []
        unused_raw_channels = []
        if self.model._data[row]['control_type'] == 'Single Stained Spectral Control':
            enable_particle_types_cb = True
            enable_gate_channel_cb = False
            if self.model._data[row]['particle_type'] == 'Cells':
                current_control_list = [self.samples['all_samples'][sample_path] for sample_path in self.samples['single_stain_controls']]
                enable_sample_name_cb = True
                enable_gate_label_cb = True
            elif self.model._data[row]['particle_type'] == 'Beads':
                current_control_list = [self.samples['all_samples'][sample_path] for sample_path in self.samples['single_stain_controls']]
                enable_sample_name_cb = True
                enable_gate_label_cb = True
            else:
                enable_sample_name_cb = False
                enable_gate_label_cb = False

        elif self.model._data[row]['control_type'] == 'Channel Assignment':
            enable_particle_types_cb = False
            enable_gate_channel_cb = True
            enable_sample_name_cb = False
            enable_gate_label_cb = False
            unused_raw_channels = self.model.unused_raw_channels(self.model._data[row]['gate_channel'])

        elif self.model._data[row]['control_type'] == 'Single Stained Spectral Control from Library':
            enable_particle_types_cb = False
            enable_gate_channel_cb = False
            if self.model._data[row]['label']:
                enable_gate_label_cb = False
                search_results = spectral_library.search_for_label(self.model._data[row]['label'].strip())
                if search_results:
                    enable_sample_name_cb = True
                    current_control_list = ['[Spectral Library] '
                                            + search_results[index]['sample_name'] + ', '
                                            + ('Major Channel: ' + search_results[index]['gate_channel'] + ', ' if search_results[index]['gate_channel'] else '')
                                            + 'Experiment: ' + search_results[index]['experiment_root_directory'] + ', '
                                             + datetime.fromtimestamp(search_results[index]['timestamp']).strftime('%Y-%m-%d %H:%M:%S') + ' '
                                            for index in search_results
                                            if list(json.loads(search_results[index]['profile_dict']).keys()) == self.fluorescence_channels_pnn]

                    for index in search_results:
                        search_results[index]['current_control_list'] = current_control_list[index]

                    self.spectral_library_search_results = search_results # store search_results for profile generator
                else:
                    enable_sample_name_cb = False
            else:
                enable_particle_types_cb = False
                enable_gate_channel_cb = False
                enable_sample_name_cb = False
                enable_gate_label_cb = False

        else:
            enable_particle_types_cb = False
            enable_gate_channel_cb = False
            enable_sample_name_cb = False
            enable_gate_label_cb = False

        # Build list of available FCS file names for the universal negative combobox.
        # The sentinel option lets users explicitly opt back into the internal negative
        # for a specific control even when the global toggle is "Using unstained negative".
        ssc_paths = self.samples.get('single_stain_controls', [])
        manually_tagged = set(self.samples.get('unstained_samples', []))
        particle_type = self.model._data[row].get('particle_type', '')

        # Restrict to samples that are unstained (manually tagged or regex) and
        # match the particle type of this control (Cells or Beads)
        unstained_options = []
        for p in ssc_paths:
            if p not in self.samples['all_samples']:
                continue
            tube_name = self.samples['all_samples'][p]
            is_unstained = (
                p in manually_tagged
                or 'unstained' in tube_name.lower()
                or 'unstained' in p.lower()
            )
            if not is_unstained:
                continue
            # Match particle type: Beads tube for Beads control, non-Beads for Cells
            import re
            is_bead = bool(re.search(r'[Bb]eads', tube_name))
            if particle_type == 'Beads' and not is_bead:
                continue
            if particle_type == 'Cells' and is_bead:
                continue
            unstained_options.append(tube_name)

        universal_negative_options = [INTERNAL_NEGATIVE_SENTINEL] + unstained_options
        is_cell_single_stain = (
            self.model._data[row]['control_type'] == 'Single Stained Spectral Control'
            and self.model._data[row]['particle_type'] == 'Cells'
        )
        is_bead_single_stain = (
            self.model._data[row]['control_type'] == 'Single Stained Spectral Control'
            and self.model._data[row]['particle_type'] == 'Beads'
        )
        enable_universal_negative_cb = is_cell_single_stain or is_bead_single_stain

        for col_name in ["control_type", "particle_type", "gate_channel", "sample_name", "gate_label", "universal_negative_name"]:
            idx = self.model.index(row, COLUMNS.index(col_name))
            if col_name == "control_type":
                self._add_or_replace_combobox_if_enabled(idx, True, [""] + CONTROL_TYPES)
            elif col_name == "particle_type":
                self._add_or_replace_combobox_if_enabled(idx, enable_particle_types_cb, [""] + PARTICLE_TYPES)
            elif col_name == "gate_channel":
                self.update_fluorescence_channels_pnn()
                self._add_or_replace_combobox_if_enabled(idx, enable_gate_channel_cb, [""] + unused_raw_channels)
            elif col_name == "sample_name":
                self._add_or_replace_combobox_if_enabled(idx, enable_sample_name_cb, [""] + current_control_list)
            elif col_name == "gate_label":
                self._add_or_replace_combobox_if_enabled(idx, enable_gate_label_cb, [""] + raw_gates_list(self.raw_gating))
            elif col_name == "universal_negative_name":
                self._add_or_replace_combobox_if_enabled(idx, enable_universal_negative_cb, universal_negative_options)

        # "Use Cleaned" checkbox — visible only when cleaned data exist for this control
        label = self.model._data[row].get('label') or ''
        cleaned_events = self.controller.experiment.process.get('cleaned_events', {})
        cleaned_available = label in cleaned_events
        uc_col = COLUMNS.index("use_cleaned")
        uc_idx = self.model.index(row, uc_col)
        proxy_uc_idx = self.proxy.mapFromSource(uc_idx)

        old = self.view.indexWidget(proxy_uc_idx)
        if old is not None:
            old.deleteLater()
            self.view.setIndexWidget(proxy_uc_idx, None)

        if cleaned_available:
            cb = QCheckBox()
            cb.installEventFilter(WheelBlocker(cb))
            # Default to checked if use_cleaned is True or not yet set
            current_val = self.model._data[row].get('use_cleaned')
            cb.setChecked(current_val is not False)  # True or None → checked; False → unchecked
            cb.setToolTip('Use cleaned event pool for profile extraction.\nUncheck to revert to the standard gate-mean method for this control.')

            def _on_toggle(checked, idx=uc_idx, row=row):
                self.model._data[row]['use_cleaned'] = checked
                # Re-run generate() for this control immediately
                self.setEnabled(False)
                self.profile_updater.flush()
                control_valid = self.profile_updater.generate(
                    self.model._data[row], self.spectral_library_search_results
                )
                self.refresh_comboboxes()
                self.setEnabled(True)
                if control_valid:
                    self.bus.spectralModelUpdated.emit()

            cb.toggled.connect(_on_toggle)
            self.view.setIndexWidget(proxy_uc_idx, cb)

        # "Remove AF" checkbox — visible for all eligible cell controls that have a
        # universal negative assigned (af_remove controls what Clean Controls does,
        # so it must be settable before the user clicks Clean Controls, unlike
        # use_cleaned which is only meaningful after cleaning has run).
        af_remove_eligible = (
            is_cell_single_stain
            and bool(self.model._data[row].get('universal_negative_name'))
            and self.model._data[row].get('universal_negative_name') != INTERNAL_NEGATIVE_SENTINEL
        )
        af_col = COLUMNS.index("af_remove")
        af_idx = self.model.index(row, af_col)
        proxy_af_idx = self.proxy.mapFromSource(af_idx)

        old_af = self.view.indexWidget(proxy_af_idx)
        if old_af is not None:
            old_af.deleteLater()
            self.view.setIndexWidget(proxy_af_idx, None)

        if af_remove_eligible:
            af_cb = QCheckBox()
            af_cb.installEventFilter(WheelBlocker(af_cb))
            current_af = self.model._data[row].get('af_remove')
            af_cb.setChecked(bool(current_af))   # None / False → unchecked; True → checked
            af_cb.setToolTip(
                'Remove intrusive autofluorescence (AF) contamination from this control.\n'
                'Uses PCA on the matched unstained to identify the AF signature,\n'
                'fits an exclusion boundary in (AF channel, peak channel) space,\n'
                'and removes positive events above that boundary before RLM fitting.\n'
                'Re-run "Clean Controls" after changing this setting.'
            )

            def _on_af_toggle(checked, row=row):
                self.model._data[row]['af_remove'] = checked

            af_cb.toggled.connect(_on_af_toggle)
            self.view.setIndexWidget(proxy_af_idx, af_cb)
                

    def add_row(self):
        pos = self.model.rowCount()
        self.model.insertRow(pos)
        self.refresh_comboboxes()
        self.view.scrollToBottom()
        self.view.resizeToFit()

        # focus and start editing the new label cell
        label_index = self.proxy.mapFromSource(self.model.index(pos, COLUMNS.index("label")))
        self.view.setCurrentIndex(label_index)
        self.view.edit(label_index)

        # self._on_spectral_control_added()

    def delete_selected_rows(self):
        sel = self.view.selectionModel().selectedRows()
        if not sel:
            QMessageBox.information(self, "No selection", "No rows selected to delete.")
            return
        indices = sorted([self.proxy.mapToSource(s).row() for s in sel])
        reply = QMessageBox.question(self, "Confirm delete", f"Are you sure you want to delete {len(indices)} row(s)?", QMessageBox.Yes | QMessageBox.No)
        if reply == QMessageBox.Yes:
            self.model.delete_rows_by_indices(indices)
            self.refresh_comboboxes()
            self.bus.spectralModelUpdated.emit() #spectral model already scrubbed at this point - this will clear unmixing matrix
            self.bus.showSelectedProfiles.emit(None)

    def auto_generate(self):
        # if spectral model already exists, ask if user wants it cleared
        if self.model.rowCount():
            reply = QMessageBox.question(self, "Auto generate spectral model", f"This will overwrite the spectral model. Are you sure you wish to continue?", QMessageBox.Yes | QMessageBox.No)
            if reply == QMessageBox.Yes:
                self.model.delete_rows_by_indices(list(range(len(self.model._data))))
            else:
                return

        # then if the user has samples but no single stain controls, ask if channel assignment is desired
        if not self.controller.experiment.samples['single_stain_controls']:
            if self.controller.experiment.samples['all_samples']:
                reply = QMessageBox.question(self, "Do conventional cytometry?",
                                             "You have no spectral controls defined."
                                             "\nDo you wish to assign fluorophore names "
                                             "\nto all your raw FCS channels?"
                                             "\nYou can then edit the names.",
                                             QMessageBox.Yes | QMessageBox.No)
                if reply == QMessageBox.Yes:
                    self.auto_conventional()
                return

            # then if the user has no samples at all, just warn
            elif not self.controller.experiment.samples['all_samples'] and not self.controller.experiment.samples['single_stain_controls']:
                self.bus.warningMessage.emit('Can\'t autogenerate: your list of single stain controls is empty.'
                                             '\n\nPlease add your single stain controls or set the correct folder for '
                                             'single stain controls in experiment configuration. '
                                             '\n\nAlternatively, you can add controls from the spectral library (if previously added) '
                                             'or assign channels (for conventional cytometry).')
                return

        # if user gets through all above, run spectral auto generator
        self.setEnabled(False)
        self.thread = QThread()
        self.spectral_auto_generator = SpectralAutoGenerator(self.bus, self.controller)

        self.spectral_auto_generator.moveToThread(self.thread)
        self.bus.spectralControlAdded.connect(self._on_spectral_control_added_by_autogenerator)
        self.thread.started.connect(self.spectral_auto_generator.run)
        self.bus.spectralModelUpdated.connect(self.thread.quit)
        self.thread.finished.connect(self.refresh_table_and_enable)
        self.thread.start()

    def auto_conventional(self):
        # first make sure all channels selected
        self.fluorescence_channel_filter_combo.blockSignals(True)
        self.controller.experiment.process['fluorescence_channel_filter'] = 'all_fluorescence'
        self.update_combos()
        self.controller.filter_raw_fluorescence_channels()
        self.profile_updater.refresh()
        self.update_fluorescence_channels_pnn()
        self.fluorescence_channel_filter_combo.blockSignals(False)

        # generate profiles
        spectral_model = self.controller.experiment.process['spectral_model']
        for n, channel in enumerate(self.fluorescence_channels_pnn):
            control = {'label': channel, 'control_type': 'Channel Assignment', 'particle_type': '', 'gate_channel': channel, 'sample_name': '', 'sample_path': '', 'gate_label': ''}
            spectral_model.append(control)
            self.profile_updater.generate(control, self.spectral_library_search_results)  # pass in search results in case control is from library

        # refresh and update
        self.refresh_table_and_enable() #comboboxes
        self.model.layoutChanged.emit() #table view
        self.bus.spectralModelUpdated.emit() #unmixing matrix etc

    def _on_spectral_control_added_by_autogenerator(self):
        self.model.layoutChanged.emit()
        # control = self.model._data[-1]['label']
        # if control:
        #     if control in self.controller.experiment.process['profiles']:
        #         self.bus.showSelectedProfiles.emit([control])

    def refresh_table_and_enable(self):
        # self.model.layoutChanged.emit() # consider refreshing at this point... but it may cause crash
        self.refresh_comboboxes()
        self.setEnabled(True)
        QTimer.singleShot(300, lambda: self.bus.showSelectedProfiles.emit([]))

    def _show_selected_profiles(self):
        selected_rows = set()
        for index in self.view.selectionModel().selectedRows():
            selected_rows.add(index.row())
        selected_rows = sorted(selected_rows)
        profile_list = [self.model._data[row]['label'] for row in selected_rows if self.model._data[row]['label']]
        self.bus.showSelectedProfiles.emit(profile_list)

    @Slot(int)
    def _on_update_control(self, index, col):
        self._pending_update_index = index
        self._pending_update_col = col # track cosmetic vs functional changes
        self._update_timer.start()  # restarts timer on each rapid edit

    def _do_update_control(self):
        index = self._pending_update_index
        col = self._pending_update_col
        changed_col = COLUMNS[col]
        if index is None:
            return
        if changed_col in ('label', 'antigen'):
            control = self.model._data[index]

            if changed_col in ('label', 'antigen'):
                control = self.model._data[index]

                if changed_col == 'label':
                    attempted_label = control['label']
                    # Check for duplicate labels before mutating anything.
                    all_labels = [c['label'] for c in self.model._data if c['label']]
                    if len(all_labels) != len(set(all_labels)):
                        # Revert by restoring the old label from the profiles dict —
                        # the profiles key for this row hasn't been renamed yet so it
                        # still holds the pre-edit value.
                        old_label = next(
                            (k for k in self.profile_updater.profiles
                            if k not in [c['label'] for c in self.model._data]),
                            None
                        )
                        if old_label is not None:
                            control['label'] = old_label
                        self.model.dataChanged.emit(
                            self.model.index(index, col),
                            self.model.index(index, col),
                            [Qt.DisplayRole, Qt.EditRole]
                        )
                        self.bus.warningMessage.emit(
                            f'Label "{attempted_label}" is already in use. '
                            f'Each control must have a unique label.'
                        )
                        return
            
            # Rename the profiles dict key to match the new label.
            old_labels = [k for k in self.profile_updater.profiles if k not in [c['label'] for c in self.model._data]]
            new_labels = [c['label'] for c in self.model._data if c['label'] not in self.profile_updater.profiles]
            for old, new in zip(old_labels, new_labels):
                self.profile_updater.profiles[new] = self.profile_updater.profiles.pop(old)

            if changed_col == 'label' and old_labels and new_labels:
                # A label rename leaves four downstream structures stale.
                # Propagate atomically without recalculating the unmixing matrix.
                for old, new in zip(old_labels, new_labels):
                    self._propagate_label_rename(old, new)
                # Rebuild ephemeral gating/transform objects from the updated experiment
                # state and refresh the UI. Does not touch the unmixing matrix,
                # spillover, fine-tuning, or AF cache.
                self.controller.initialise_ephemeral_data(scope=['unmixed'])
                if self.bus:
                    self.bus.spectralProcessRefreshed.emit()

            self.bus.showSelectedProfiles.emit([control['label']])
            logger.info(f'SpectralModelEditor: cosmetic edit on row {index}, col "{changed_col}" — skipping regeneration')
            return
        self.setEnabled(False)  # block further interaction during generate
        control = self.model._data[index]
        unused_raw_channels = self.model.unused_raw_channels(control['gate_channel'])
        if control['control_type'] == 'Channel Assignment' and not control['gate_channel'] and unused_raw_channels:
            control['gate_channel'] = unused_raw_channels[0]
        sanitise_control_in_place(control)
        self.profile_updater.flush()
        control_valid = self.profile_updater.generate(control, self.spectral_library_search_results)
        self.refresh_comboboxes()
        self.setEnabled(True)  # re-enable after generate completes
        if control_valid:
            self.bus.showSelectedProfiles.emit([control['label']])
            if not label_only:
                self.bus.spectralModelUpdated.emit()
        logger.info(f'SpectralModelEditor: updated {"valid" if control_valid else "invalid"} control {control}')

    def _propagate_label_rename(self, old: str, new: str):
        """
        Rename a fluorescence channel label in all experiment structures that
        reference it by name, without touching the unmixing matrix or any
        computed numerical state.

        Structures updated:
          - experiment.settings['unmixed']['fluorescence_channels']
          - experiment.settings['unmixed']['event_channels_pnn']
          - experiment.cytometry['transforms']  (dict keyed by channel name)
          - experiment.cytometry['gating']      (GML string — replace as text)
        """
        exp = self.controller.experiment

        # 1. fluorescence_channels list
        fl = exp.settings['unmixed'].get('fluorescence_channels', [])
        exp.settings['unmixed']['fluorescence_channels'] = [
            new if ch == old else ch for ch in fl
        ]

        # 2. event_channels_pnn list
        pnn = exp.settings['unmixed'].get('event_channels_pnn', [])
        exp.settings['unmixed']['event_channels_pnn'] = [
            new if ch == old else ch for ch in pnn
        ]

        # 3. cytometry transforms dict (rename the key)
        transforms = exp.cytometry.get('transforms') or {}
        if old in transforms:
            transforms[new] = transforms.pop(old)

        # 4. GML gating string — parse as XML and rename only the fcs-dimension
        #    name attributes that match exactly, avoiding substring corruption
        #    (e.g. renaming "PE" must not touch "PE-Cy7", "PE-CF594", etc.)
        gating_gml = exp.cytometry.get('gating')
        if gating_gml:
            exp.cytometry['gating'] = _rename_channel_in_gml(gating_gml, old, new)

        # 5. cytometry plots list — channel_x and channel_y are stored by name
        for plot in exp.cytometry.get('plots') or []:
            if plot.get('channel_x') == old:
                plot['channel_x'] = new
            if plot.get('channel_y') == old:
                plot['channel_y'] = new

            # 6. Update the live ephemeral dicts immediately so any widget that
        #    re-renders before spectralProcessRefreshed is handled sees
        #    consistent channel names. initialise_ephemeral_data will
        #    overwrite these properly afterwards.
        for data_dict in (self.controller.data_for_cytometry_plots_process,
                          self.controller.data_for_cytometry_plots_unmixed):
            pnn = data_dict.get('pnn')
            if pnn:
                data_dict['pnn'] = [new if ch == old else ch for ch in pnn]
            for plot in data_dict.get('plots') or []:
                if plot.get('channel_x') == old:
                    plot['channel_x'] = new
                if plot.get('channel_y') == old:
                    plot['channel_y'] = new
            transformations = data_dict.get('transformations')
            if transformations and old in transformations:
                transformations[new] = transformations.pop(old)

        logger.info(f'SpectralModelEditor: propagated label rename "{old}" -> "{new}"')

    @Slot()
    def _on_force_recalc(self):
        self.setEnabled(False)
        self.profile_updater.flush()  # remove profiles that are not in the model
        for index, control in enumerate(self.model._data):
            control_valid = self.profile_updater.generate(control, self.spectral_library_search_results) # generate profile, pass in search results in case control is from library
            if not control_valid:
                break

        self.bus.spectralModelUpdated.emit()
        self.refresh_table_and_enable()
        logger.info(f'SpectralModelEditor: forced recalculation')

    @Slot()
    def _on_clean_controls(self):
        """Launch SpectralCleaner in a QThread. On completion, set use_cleaned=True
        for all successfully cleaned controls and trigger a full recalculate."""
        self.setEnabled(False)
        self.clean_controls_btn.setText("Cleaning…")

        self.cleaner_thread = QThread()
        self.spectral_cleaner = SpectralCleaner(self.bus, self.controller)
        self.spectral_cleaner.moveToThread(self.cleaner_thread)

        self.cleaner_thread.started.connect(self.spectral_cleaner.run)
        self.spectral_cleaner.cleaningFinished.connect(self.cleaner_thread.quit)
        self.cleaner_thread.finished.connect(self._on_clean_controls_finished)
        self.cleaner_thread.start()

    @Slot()
    def _on_clean_controls_finished(self):
        """After SpectralCleaner.run() completes: mark controls as use_cleaned=True,
        recalculate profiles, refresh UI."""
        cleaned_events = self.controller.experiment.process.get('cleaned_events', {})
        for control in self.model._data:
            label = control.get('label') or ''
            if label in cleaned_events:
                # Only set the default if not already explicitly set by the user
                if control.get('use_cleaned') is None:
                    control['use_cleaned'] = True

        self.clean_controls_btn.setText("Clean Controls")

        # Run profile regeneration in a background thread so the main thread
        # stays responsive. _on_force_recalc is not thread-safe (it touches Qt
        # widgets directly), so we do only the pure computation here and defer
        # the UI update to the main thread via a signal.
        self._recalc_thread = QThread()
        self._recalc_worker = _RecalcWorker(self.profile_updater, self.model._data, self.spectral_library_search_results)
        self._recalc_worker.moveToThread(self._recalc_thread)
        self._recalc_thread.started.connect(self._recalc_worker.run)
        self._recalc_worker.finished.connect(self._recalc_thread.quit)
        self._recalc_thread.finished.connect(self._on_recalc_finished)
        self._recalc_thread.start()

    @Slot()
    def _on_recalc_finished(self):
        self.bus.spectralModelUpdated.emit()
        self.refresh_table_and_enable()
        logger.info('SpectralControlsEditor: Clean Controls run complete.')


    @Slot(list)
    def _on_delete_controls(self, labels):
        for label in labels:
            self.profile_updater.pop_control(label)


if __name__ == "__main__":
    controls = [
        {'label': 'PE-Fire 810', 'control_type': 'Single Stained Spectral Control', 'particle_type': 'Cells', 'gate_channel': 'B6-A',
            'sample_name': 'PE-Fire 810 (Cells)',
            'sample_path': '/home/ssr/spectral_cytometry/20240620 Spectral Symposium-poor cell unmixed/Raw/Cell controls/Reference Group/G1 PE-Fire 810 (Cells)_Cell controls.fcs',
            'gate_label': 'Positive PE-Fire 810'},
        {'label': 'Spark', 'control_type': 'Single Stained Spectral Control', 'particle_type': 'Cells', 'gate_channel': 'B2-A',
            'sample_name': 'Spark (Beads)',
            'sample_path': '/home/ssr/spectral_cytometry/20240620 Spectral Symposium-poor cell unmixed/Raw/Bead controls/Reference Group/Spark (Beads)_Beads controls.fcs',
            'gate_label': 'Positive Spark'},
        {'label': 'FITC', 'control_type': 'Channel Assignment', 'particle_type': None, 'gate_channel': 'B1-A',
            'sample_name': None,
            'sample_path': None,
            'gate_label': None}
    ]

    samples = {'single_stain_controls': ['Raw/Cell controls/Reference Group/A1 Unstained (Cells)_Cell controls.fcs',
                                 'Raw/Cell controls/Reference Group/A10 BUV805 (Cells)_Cell controls.fcs',
                                 'Raw/Cell controls/Reference Group/A11 Super Bright 436 (Cells)_Cell controls.fcs',
                                 'Raw/Cell controls/Reference Group/A12 eFluor 450 (Cells)_Cell controls.fcs',
                                 'Raw/Cell controls/Reference Group/A2 Spark UV 387 (Cells)_Cell controls.fcs',
                                 'Raw/Cell controls/Reference Group/G7 APC-Fire 810 (Cells)_Cell controls.fcs']
    }

    gates = ['root', 'Cells', 'Singlets', 'Positive PE-Fire 810', 'Positive Spark']

    app = QApplication(sys.argv)

    from honeychrome.controller import Controller
    from pathlib import Path
    from event_bus import EventBus

    bus = EventBus()
    kc = Controller()
    kc.bus = bus
    # base_directory = Path.home() / 'spectral_cytometry'
    # experiment_name = base_directory / '20240620 Spectral Symposium-poor cell unmixed'
    # experiment_path = experiment_name.with_suffix('.kit')
    base_directory = Path.home() / 'Experiments'
    experiment_name = base_directory / 'Oleg K BD FACSAria III'
    experiment_path = experiment_name.with_suffix('.kit')
    kc.load_experiment(experiment_path) # note this loads first sample too and runs calculate all histograms and statistics

    frame = SpectralControlsEditor(bus, kc)
    frame.show()
    sys.exit(app.exec())

