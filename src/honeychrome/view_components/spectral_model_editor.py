import json
import sys
from datetime import datetime
from typing import List, Any, Dict
from PySide6 import QtCore
from PySide6.QtCore import Qt, QModelIndex, QTimer, QThread, Slot, QObject, QEvent, QSize
from PySide6.QtWidgets import (QApplication, QFrame, QVBoxLayout, QHBoxLayout, QTableView, QPushButton, QStyledItemDelegate, QComboBox, QLineEdit, QMessageBox, QHeaderView, QLabel, QWidget)

from honeychrome.controller_components.functions import raw_gates_list
from honeychrome.controller_components.spectral_controller import SpectralAutoGenerator, ProfileUpdater, spectral_library
from honeychrome.controller_components.spectral_functions import sanitise_control_in_place
from honeychrome.view_components.icon_loader import icon
from honeychrome.settings import spectral_model_column_labels, heading_style

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


class WheelBlocker(QObject):
    def eventFilter(self, obj, event):
        if event.type() == QEvent.Wheel:
            return True    # Block wheel event
        return super().eventFilter(obj, event)

class ListTableModel(QtCore.QAbstractTableModel):
    dataEditedSignal = QtCore.Signal(int)
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
            return "" if val is None else str(val)
        return None

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if role != Qt.DisplayRole:
            return None
        if orientation == Qt.Horizontal:
            return spectral_model_column_labels[COLUMNS[section]]
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
        # if key == "gate_channel":
        #     try:
        #         value = int(value)
        #     except ValueError:
        #         return False
        self._data[row][key] = value
        self.dataChanged.emit(index, index, [Qt.DisplayRole, Qt.EditRole])
        self.dataEditedSignal.emit(row)
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
        header = self.view.horizontalHeader()
        header.setStretchLastSection(False)
        header.setSectionResizeMode(0, QHeaderView.Interactive)
        header.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(4, QHeaderView.Stretch)
        header.setSectionResizeMode(5, QHeaderView.ResizeToContents)
        self.view.setColumnWidth(0, 400)

        self.label_delegate = LabelDelegate()
        self.view.setItemDelegateForColumn(COLUMNS.index("label"), self.label_delegate)

        self.model.dataEditedSignal.connect(self._on_update_control)
        self.model.dataDeletedSignal.connect(self._on_delete_controls)

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

        btn_top_layout.addWidget(self.auto_generate_button)
        btn_top_layout.addWidget(self.negatives_combo)
        btn_top_layout.addWidget(self.fluorescence_channel_filter_combo)
        btn_top_layout.addWidget(self.force_recalc_btn)
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
        else:
            self.controller.experiment.process['negative_type'] = 'internal'
            self.negatives_combo.setCurrentText('Using internal negatives')
            self.negatives_combo.setToolTip('Negative set to bottom percentile of each control sample')
        logger.info(f'SpectralModelEditor: set negative type to {self.controller.experiment.process['negative_type']}')

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

        for col_name in ["control_type", "particle_type", "gate_channel", "sample_name", "gate_label"]:
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
    def _on_update_control(self, index):
        # sanitise data and regenerate profile if control is valid
        control = self.model._data[index]
        unused_raw_channels = self.model.unused_raw_channels(control['gate_channel'])
        if control['control_type'] == 'Channel Assignment' and not control['gate_channel'] and unused_raw_channels:
            control['gate_channel'] = unused_raw_channels[0]
        sanitise_control_in_place(control)
        self.profile_updater.flush() # remove profiles that are not in the model
        control_valid = self.profile_updater.generate(control, self.spectral_library_search_results) # generate profile, pass in search results in case control is from library
        self.refresh_comboboxes()
        if control_valid:
            self.bus.showSelectedProfiles.emit([control['label']])
            self.bus.spectralModelUpdated.emit()
        logger.info(f'SpectralModelEditor: updated {'valid' if control_valid else 'invalid'} control {control}')

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

