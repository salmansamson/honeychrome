from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout,
    QLineEdit, QLabel, QRadioButton,
    QPushButton, QButtonGroup
)
from PySide6.QtCore import Signal


class NewSampleDialog(QDialog):
    """
    Dialog to enter a sample name and choose a sample type.
    Emits newSampleRequested(name: str, type: str) when submitted.
    """
    newSampleRequested = Signal(str, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Create New Sample")
        self.setModal(True)
        self.resize(500,150)

        layout = QVBoxLayout(self)

        # --- Name input ---
        name_layout = QHBoxLayout()
        name_layout.addWidget(QLabel("Name:"))
        self.name_edit = QLineEdit()
        name_layout.addWidget(self.name_edit)
        layout.addLayout(name_layout)

        # --- Radio buttons for type selection ---
        button_layout = QHBoxLayout()

        self.type_group = QButtonGroup(self)
        self.single_stain_control_btn = QRadioButton("Single Stain Control")
        self.raw_sample_btn = QRadioButton("Raw Sample")


        # Add to layout and group
        for btn in [self.single_stain_control_btn, self.raw_sample_btn]:
            button_layout.addWidget(btn)
            self.type_group.addButton(btn)

        layout.addLayout(button_layout)


        # Default selection
        self.single_stain_control_btn.setChecked(True)

        # --- Submit / Cancel buttons ---
        button_layout = QHBoxLayout()
        self.submit_btn = QPushButton("Submit")
        self.cancel_btn = QPushButton("Cancel")
        button_layout.addWidget(self.submit_btn)
        button_layout.addWidget(self.cancel_btn)
        layout.addLayout(button_layout)

        # --- Connections ---
        self.submit_btn.clicked.connect(self._on_submit)
        self.cancel_btn.clicked.connect(self.reject)

    def _on_submit(self):
        name = self.name_edit.text().strip()
        if not name:
            return  # In real use, show a QMessageBox warning instead

        if self.single_stain_control_btn.isChecked():
            sample_type = "Single Stain Control"
        else:
            sample_type = "Raw Sample"

        self.newSampleRequested.emit(name, sample_type)
        self.accept()  # close dialog with success


if __name__ == "__main__":
    from PySide6.QtWidgets import QApplication
    import sys

    app = QApplication(sys.argv)
    dlg = NewSampleDialog()
    dlg.newSampleRequested.connect(lambda n, t: print(f"New sample: {n} ({t})"))
    dlg.exec()
