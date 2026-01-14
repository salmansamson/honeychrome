from PySide6.QtWidgets import (QApplication, QDialog, QVBoxLayout, QHBoxLayout, QRadioButton, QButtonGroup, QLineEdit,
                               QLabel, QPushButton, QDialogButtonBox, QCheckBox)
from PySide6.QtGui import QRegularExpressionValidator, QDesktopServices
from PySide6.QtCore import QRegularExpression, Qt, QUrl, QThread
import sys

from honeychrome.controller_components.functions import get_all_subfolders_recursive
from honeychrome.controller_components.import_fcs_controller import ImportFCSController
from honeychrome.view_components.icon_loader import icon


class ImportFCSFilesWidget(QDialog):
    def __init__(self, parent, bus=None, controller=None, failed_to_load_sample_warning=False):
        super().__init__(parent=parent, modal=True)
        self.bus = bus
        self.controller = controller
        self.setWindowTitle("Import FCS Files")

        self.thread = None
        self.import_fcs_controller = None

        layout = QVBoxLayout(self)

        if failed_to_load_sample_warning:
            self.setGeometry(200, 200, 450, 200)
            label = QLabel('''
            <p><b>Failed to load sample: sample channels (names and ranges) do not match the experiment configuration.</b></p>
            <p>Does this sample belong with the others? If so, update the experiment configuration below. If not, delete this sample.</p>
            ''')
            label.setTextFormat(Qt.RichText)
            label.setWordWrap(True)

            layout.addWidget(label)
            layout.addStretch()

        else:
            self.setGeometry(200, 200, 500, 500)
            part_one_label = QLabel('''
            <h3>1. Copy or Move FCS Files</h3>
            <p>First, copy or move FCS files into the experiment's <tt>Raw</tt> folder using your file browser.</p>
            <p>Tip: you can organise your FCS files into further subfolders.</p>
            ''')
            part_one_label.setTextFormat(Qt.RichText)
            part_one_label.setWordWrap(True)

            part_one_button = QPushButton(icon('folder-search'), "Open Raw Subfolder")
            part_one_button.clicked.connect(self.open_samples_folder)
            part_one_button_layout = QHBoxLayout()

            part_two_label = QLabel('''
            <h3>2. Update Experiment Configuration</h3>
            <p>Second, update the experiment configuration to match your FCS files (setting channel names and ranges, and checking for consistency between the FCS files). 
            Note that all plots, transforms, gating and spectral process in the experiment will be reset.</p>
            ''')
            part_two_label.setTextFormat(Qt.RichText)
            part_two_label.setWordWrap(True)

            layout.addWidget(part_one_label)
            layout.addStretch()
            layout.addLayout(part_one_button_layout)
            part_one_button_layout.addStretch()
            part_one_button_layout.addWidget(part_one_button)
            part_one_button_layout.addStretch()
            layout.addStretch()
            layout.addWidget(part_two_label)
            layout.addStretch()

        # --- Buttons ---
        button_box = QDialogButtonBox()
        self.btn_cancel = button_box.addButton("Cancel", QDialogButtonBox.RejectRole)
        self.btn_submit = button_box.addButton("Update Experiment Configuration", QDialogButtonBox.AcceptRole)

        layout.addWidget(button_box)

        # Connections
        self.btn_cancel.clicked.connect(self.reject)
        self.btn_submit.clicked.connect(self.submit)

    def submit(self):
        self.thread = QThread()
        self.import_fcs_controller = ImportFCSController(self.controller.experiment, bus=self.bus)
        self.import_fcs_controller.moveToThread(self.thread)
        self.thread.started.connect(self.import_fcs_controller.reconfigure_experiment_from_fcs_files)
        self.import_fcs_controller.finished.connect(self.thread.quit)
        self.thread.finished.connect(self._on_thread_finished)
        self.thread.start()

    def _on_thread_finished(self):
        self.accept()


    def open_samples_folder(self):
        QDesktopServices.openUrl(QUrl.fromLocalFile(self.controller.experiment_dir / self.controller.experiment.settings['raw']['raw_samples_subdirectory']))


if __name__ == "__main__":
    app = QApplication(sys.argv)


    from honeychrome.controller import Controller
    from pathlib import Path
    from event_bus import EventBus

    bus = EventBus()
    kc = Controller()
    kc.bus = bus
    base_directory = Path.home() / 'spectral_cytometry'
    experiment_name = base_directory / '20240620 Spectral Symposium-poor cell unmixed'
    experiment_path = experiment_name.with_suffix('.kit')
    kc.load_experiment(experiment_path) # note this loads first sample too and runs calculate all histograms and statistics

    dialog = ImportFCSFilesWidget(bus, kc)
    dialog.exec()
    sys.exit(0)
