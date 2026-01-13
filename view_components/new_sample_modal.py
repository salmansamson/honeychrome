from PySide6.QtWidgets import (QApplication, QDialog, QVBoxLayout, QHBoxLayout, QRadioButton, QButtonGroup, QLineEdit,
                               QLabel, QPushButton, QDialogButtonBox, QCheckBox)
from PySide6.QtGui import QRegularExpressionValidator
from PySide6.QtCore import QRegularExpression
import sys

from controller_components.functions import get_all_subfolders_recursive


class NewSampleModal(QDialog):
    def __init__(self, parent=None, bus=None, path=None, experiment_dir=None):
        super().__init__(parent, modal=True)
        self.bus = bus
        self.setWindowTitle("New Sample")

        self.folders = get_all_subfolders_recursive(path, experiment_dir)

        layout = QVBoxLayout(self)

        # --- Radio Buttons ---
        self.radio_group = QButtonGroup(self)
        self.radio_single_stain_control = QRadioButton("Single Stain Controls")
        self.radio_single_stain_control.setToolTip("Sample name should be of form: \n\"Label (Cells)\"\nor \"Label (Beads)\"")
        self.radio_folders = [QRadioButton(str(folder)) for folder in self.folders]

        # Add to group but leave none selected
        self.radio_group.addButton(self.radio_single_stain_control)
        for folder_btn in self.radio_folders:
            self.radio_group.addButton(folder_btn)

        radio_layout = QVBoxLayout()
        radio_layout.addWidget(QLabel('Add new sample to:'))
        radio_layout.addWidget(self.radio_single_stain_control)
        radio_layout.addWidget(QLabel('Or choose sample folder:'))
        for folder_btn in self.radio_folders:
            radio_layout.addWidget(folder_btn)

        # Connect radio changes to enabling logic
        self.radio_group.buttonToggled.connect(self.update_button_state)

        # --- Filename validator ---
        # Accept filename-safe characters: letters, numbers, underscore, hyphen, dot
        filename_regex = QRegularExpression(r"[A-Za-z0-9._\- ]+")
        self.filename_validator = QRegularExpressionValidator(filename_regex)

        layout.addWidget(QLabel("Sample Name:"))
        self.input_field = QLineEdit()
        self.input_field.setPlaceholderText("Enter filename...")
        self.input_field.setValidator(self.filename_validator)
        layout.addWidget(self.input_field)

        layout.addLayout(radio_layout)

        self.batch_entry = QCheckBox("Stay open to enter multiple files")
        layout.addWidget(self.batch_entry)

        # --- Buttons ---
        button_box = QDialogButtonBox()
        self.btn_cancel = button_box.addButton("Cancel", QDialogButtonBox.RejectRole)
        self.btn_submit = button_box.addButton("Submit", QDialogButtonBox.AcceptRole)

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

    def get_sample_type(self):
        """Return the selected radio button's text or None."""
        checked = self.radio_group.checkedButton()
        sample_type = ''
        if checked:
            if checked.text() == 'Single Stain Controls':
                sample_type = 'single_stain_controls'
            elif checked.text():
                sample_type = checked.text()

        return sample_type

    def submit(self):
        """Standard submit (dialog closes)."""
        if self._validate_input():
            if self.bus is not None:
                self.bus.newSampleRequested.emit(self.input_field.text(), self.get_sample_type())

        if not self.batch_entry.isChecked():
            self.accept()
        else:
            self.input_field.clear()

    def _validate_input(self):
        text = self.input_field.text()
        if not text:
            self.input_field.setPlaceholderText("Name required.")
            return False
        if self.filename_validator.validate(text, 0)[0] != QRegularExpressionValidator.Acceptable:
            self.input_field.clear()
            self.input_field.setPlaceholderText("Invalid filename characters.")
            return False
        return True


if __name__ == "__main__":
    app = QApplication(sys.argv)
    dialog = NewSampleModal(parent=None, bus=None, path='/home/ssr/spectral_cytometry/20240620 Spectral Symposium-poor cell unmixed/Raw', experiment_dir='/home/ssr/spectral_cytometry/20240620 Spectral Symposium-poor cell unmixed')

    if dialog.exec():
        print("Submitted:", dialog.input_field.text(), dialog.get_sample_type())
    else:
        print("Cancelled")

    sys.exit(0)
