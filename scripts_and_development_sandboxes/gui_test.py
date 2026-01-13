
import sys
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QLabel, QMenu, QDialog, QDialogButtonBox,
    QHBoxLayout, QSplitter, QTabWidget,
    QToolBar, QStatusBar, QTreeView, QInputDialog
)
from PyQt6.QtCore import Qt, QPoint
from PyQt6.QtGui import QIcon, QAction, QStandardItemModel, QStandardItem
import os
from scripts_and_development_sandboxes.data_models import Sample, Experiment
from scripts_and_development_sandboxes.splash_screen import SplashScreen

class SampleListModel(QStandardItemModel):
    """Qt Item Model reflecting ExperimentModel samples."""
    def __init__(self, experiment_model: Experiment, parent=None):
        super().__init__(parent)
        self.experiment_model = experiment_model
        self.icon_with_data = None
        self.icon_blank = None
        self.refresh()

    def ensure_icons(self):
        if self.icon_with_data is None:
            self.icon_with_data = QIcon("green_dot.png")  # replace with valid resource
        if self.icon_blank is None:
            self.icon_blank = QIcon("transparent_dot.png")  # replace with valid resource

    def refresh(self):
        self.clear()
        self.setColumnCount(4)
        self.setHorizontalHeaderLabels(["Index", "Sample Name", "Points", "Date"])
        self.ensure_icons()

        for i, sample in enumerate(self.experiment_model.samples, start=1):
            icon = self.icon_with_data if sample.has_data else self.icon_blank
            item_icon = QStandardItem()
            item_icon.setIcon(icon)

            item_name = QStandardItem(sample.name if sample.name else f"Sample{i}")
            item_name.setEditable(True)
            item_points = QStandardItem(str(sample.num_points))
            item_date = QStandardItem(sample.date.strftime("%Y-%m-%d"))

            self.appendRow([item_icon, item_name, item_points, item_date])


class SamplePropertiesDialog(QDialog):
    def __init__(self, sample: Sample, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Sample Properties")
        layout = QVBoxLayout()
        layout.addWidget(QLabel(f"Name: {sample.name}"))
        layout.addWidget(QLabel(f"Points: {sample.num_points}"))
        layout.addWidget(QLabel(f"Date: {sample.date}"))
        layout.addWidget(QLabel(f"Path: {sample.file_path}"))

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok)
        buttons.accepted.connect(self.accept)
        layout.addWidget(buttons)
        self.setLayout(layout)


class MainWindow(QMainWindow):
    def __init__(self, experiment_file, experiment_model: Experiment, new=False, template=False):
        super().__init__()
        self.setWindowTitle(f"{os.path.basename(experiment_file)} - Honeychrome by CytKit")
        self.experiment_model = experiment_model

        # --- Menu Bar ---
        menubar = self.menuBar()
        file_menu = menubar.addMenu("File")
        edit_menu = menubar.addMenu("Edit")
        view_menu = menubar.addMenu("View")
        help_menu = menubar.addMenu("Help")

        # Example file menu actions
        action_open = QAction(QIcon.fromTheme("document-open"), "Open", self)
        action_save = QAction(QIcon.fromTheme("document-save"), "Save", self)
        file_menu.addAction(action_open)
        file_menu.addAction(action_save)

        # --- Tool Bar ---
        toolbar = QToolBar("Main Toolbar")
        toolbar.setMovable(False)
        toolbar.addAction(action_open)
        toolbar.addAction(action_save)
        self.addToolBar(toolbar)

        # --- Central Widget Layout ---
        central_widget = QWidget()
        main_layout = QHBoxLayout()

        splitter = QSplitter(Qt.Orientation.Horizontal)

        # # Left panel (samples list)
        # self.samples_list = QListWidget()
        # self.samples_list.addItems(["Sample 1", "Sample 2", "Sample 3"])
        # splitter.addWidget(self.samples_list)

        # Left: sample list (QTreeView with multiple columns)
        self.sample_view = QTreeView()
        self.sample_model = SampleListModel(self.experiment_model)
        self.sample_view.setModel(self.sample_model)
        self.sample_view.setRootIsDecorated(False)
        self.sample_view.setAlternatingRowColors(True)
        self.sample_view.setEditTriggers(QTreeView.EditTrigger.DoubleClicked)
        self.sample_view.setSelectionBehavior(QTreeView.SelectionBehavior.SelectRows)
        self.sample_view.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.sample_view.clicked.connect(self.sample_clicked)
        self.sample_view.doubleClicked.connect(self.sample_double_clicked)
        self.sample_view.customContextMenuRequested.connect(self.sample_context_menu)
        self.sample_view.header().setStretchLastSection(True)


        splitter.addWidget(self.sample_view)


        # Right panel (tab widget)
        self.tabs = QTabWidget()
        self.tabs.addTab(QLabel("Overview content here"), "Overview")
        self.tabs.addTab(QLabel("Analysis content here"), "Analysis")
        self.tabs.addTab(QLabel("Results content here"), "Results")
        splitter.addWidget(self.tabs)

        splitter.setSizes([250, 500])
        main_layout.addWidget(splitter)
        central_widget.setLayout(main_layout)
        self.setCentralWidget(central_widget)

        # --- Status Bar ---
        status = QStatusBar()
        status.showMessage("Ready")
        self.setStatusBar(status)


    # --- Slots ---
    def sample_clicked(self, index):
        row = index.row()
        sample = self.experiment_model.get_sample(row)
        if sample:
            content = (
                f"Sample: {sample.name}\n"
                f"Points: {sample.num_points}\n"
                f"Date: {sample.date}\n"
                f"Path: {sample.file_path}"
            )
            self.overview_tab.setText(content)

    def sample_double_clicked(self, index):
        self.sample_view.edit(index)

    def sample_context_menu(self, pos: QPoint):
        index = self.sample_view.indexAt(pos)
        if not index.isValid():
            return
        row = index.row()
        sample = self.experiment_model.get_sample(row)

        menu = QMenu(self)
        action_delete = menu.addAction("Delete")
        action_rename = menu.addAction("Rename")
        action_properties = menu.addAction("Properties")

        action = menu.exec(self.sample_view.mapToGlobal(pos))
        if action == action_delete:
            self.experiment_model.remove_sample(row)
            self.sample_model.refresh()
        elif action == action_rename:
            new_name, ok = QInputDialog.getText(self, "Rename Sample", "New name:", text=sample.name)
            if ok and new_name:
                self.experiment_model.rename_sample(row, new_name)
                self.sample_model.refresh()
        elif action == action_properties:
            dlg = SamplePropertiesDialog(sample, self)
            dlg.exec()


class ExperimentSelector(QApplication):
    def __init__(self, argv):
        super().__init__(argv)
        self.main_window = None
        self.splash = SplashScreen(self.load_main_window)
        self.splash.show()

    def load_main_window(self, experiment_file, new=False, template=False):
        self.splash.close()
        experiment_model = Experiment() #SSR temporary... create or read here
        self.main_window = MainWindow(experiment_file, experiment_model, new=new, template=template)
        self.main_window.show()

if __name__ == "__main__":
    app = ExperimentSelector(sys.argv)
    sys.exit(app.exec())

