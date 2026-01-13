import sys
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QPushButton, QWidget, QVBoxLayout,
    QDialog, QScrollArea, QFormLayout, QLineEdit, QCheckBox,
    QSpinBox, QDoubleSpinBox, QDialogButtonBox
)
from PySide6.QtCore import Qt, QSettings


class ConfigDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Configuration")
        self.resize(400, 300)

        self.settings = QSettings("MyCompany", "MyApp")

        main_layout = QVBoxLayout(self)

        # --- Scroll Area ---
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)

        container = QWidget()
        form = QFormLayout(container)
        form.setSpacing(10)

        # --- Settings Widgets ---
        self.name_edit = QLineEdit()
        form.addRow("User Name:", self.name_edit)

        self.enable_feature = QCheckBox("Enable Advanced Feature")
        form.addRow(self.enable_feature)

        self.max_items = QSpinBox()
        self.max_items.setRange(1, 1000)
        form.addRow("Max Items:", self.max_items)

        self.threshold = QDoubleSpinBox()
        self.threshold.setRange(0.0, 1.0)
        self.threshold.setSingleStep(0.05)
        form.addRow("Threshold:", self.threshold)

        scroll.setWidget(container)
        main_layout.addWidget(scroll)

        # Buttons
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.handle_accept)
        buttons.rejected.connect(self.reject)
        main_layout.addWidget(buttons, alignment=Qt.AlignRight)

        # Load settings on start
        self.load_settings()

    # ----------------------------
    # Settings Load / Save Methods
    # ----------------------------

    def load_settings(self):
        self.name_edit.setText(self.settings.value("user/name", ""))
        self.enable_feature.setChecked(self.settings.value("feature/enabled", False, type=bool))
        self.max_items.setValue(self.settings.value("ui/max_items", 10, type=int))
        self.threshold.setValue(self.settings.value("ui/threshold", 0.5, type=float))

    def save_settings(self):
        self.settings.setValue("user/name", self.name_edit.text())
        self.settings.setValue("feature/enabled", self.enable_feature.isChecked())
        self.settings.setValue("ui/max_items", self.max_items.value())
        self.settings.setValue("ui/threshold", self.threshold.value())

    def handle_accept(self):
        self.save_settings()
        self.accept()


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("PySide6 Config Dialog Example with QSettings")

        btn = QPushButton("Open Settings…")
        btn.clicked.connect(self.open_config)

        central = QWidget()
        layout = QVBoxLayout(central)
        layout.addWidget(btn)
        self.setCentralWidget(central)

    def open_config(self):
        dialog = ConfigDialog(self)
        dialog.exec()


app = QApplication(sys.argv)

# Optional: define organization/application for QSettings globally
QSettings.setDefaultFormat(QSettings.IniFormat)

window = MainWindow()
window.show()
sys.exit(app.exec())
