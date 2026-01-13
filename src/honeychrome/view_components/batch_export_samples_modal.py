from PySide6.QtWidgets import (QApplication, QDialog, QVBoxLayout, QHBoxLayout, QRadioButton, QButtonGroup, QLineEdit,
                               QLabel, QPushButton, QDialogButtonBox, QCheckBox)
from PySide6.QtGui import QRegularExpressionValidator, Qt
from PySide6.QtCore import QRegularExpression
import sys

from controller_components.functions import get_all_subfolders_recursive


class BatchExportSamplesModal(QDialog):
    def __init__(self, parent=None, bus=None, path=None, experiment_dir=None):
        super().__init__(parent)
        self.bus = bus
        self.setWindowTitle("Batch Export Unmixed")

        self.folders = get_all_subfolders_recursive(path, experiment_dir)
        self.sample_sets = [str((experiment_dir / f).relative_to(path)) for f in self.folders]
        self.sample_sets[0] = '[All FCS files in experiment folder]'

        layout = QVBoxLayout(self)
        description = QLabel('''
        <h3>Select a subfolder to export all samples as FCS files (unmixed)</h3>
        <p>Note: all raw samples are already stored as FCS files within the raw data subfolder of the experiment.</p> 
        <p>This function takes all selected samples, applies the unmixing matrix, and saves them as new FCS files 
        (with spillover as the fine tuning matrix). The subfolders in which the raw data is organised are replicated in the unmixed data.</p>
        ''')
        description.setTextFormat(Qt.RichText)
        description.setWordWrap(True)
        layout.addWidget(description)

        # --- Radio Buttons ---
        self.radio_group = QButtonGroup(self)
        self.radio_folders = [QRadioButton(sample_set) for sample_set in self.sample_sets]
        for folder_btn in self.radio_folders:
            self.radio_group.addButton(folder_btn)

        radio_layout = QVBoxLayout()
        for folder_btn in self.radio_folders:
            radio_layout.addWidget(folder_btn)

        # Connect radio changes to enabling logic
        self.radio_group.buttonToggled.connect(self.update_button_state)
        layout.addLayout(radio_layout)

        self.subsample_checkbox = QCheckBox("Subsample before exporting")
        layout.addWidget(self.subsample_checkbox)

        # --- Buttons ---
        button_box = QDialogButtonBox()
        self.btn_cancel = button_box.addButton("Cancel", QDialogButtonBox.RejectRole)
        self.btn_submit = button_box.addButton("Proceed", QDialogButtonBox.AcceptRole)

        layout.addWidget(button_box)

        # Disable submit buttons initially
        self.btn_submit.setEnabled(False)

        # Connections
        self.btn_cancel.clicked.connect(self.reject)
        self.btn_submit.clicked.connect(self.submit)

    def update_button_state(self):
        """Enable submit buttons only if a radio is selected."""
        selected = self.radio_group.checkedButton() is not None
        self.btn_submit.setEnabled(selected)

    def get_subfolder(self):
        checked = self.radio_group.checkedButton().text()
        index = self.sample_sets.index(checked)
        folder = self.folders[index]

        return folder

    def submit(self):
        """Standard submit (dialog closes)."""
        folder = self.get_subfolder()
        subsample = self.subsample_checkbox.isChecked()
        print(f'BatchExportSamples: {folder}, subsample {subsample}')
        if self.bus is not None:
            self.bus.batchExportRequested.emit(str(folder), subsample)
        self.accept()



if __name__ == "__main__":
    app = QApplication(sys.argv)
    dialog = BatchExportSamplesModal(parent=None, bus=None, path='/home/ssr/spectral_cytometry/20240620 Spectral Symposium-poor cell unmixed/Raw', experiment_dir='/home/ssr/spectral_cytometry/20240620 Spectral Symposium-poor cell unmixed')

    if dialog.exec():
        print("Submitted")
    else:
        print("Cancelled")

    sys.exit(0)
