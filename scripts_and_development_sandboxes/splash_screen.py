import sys
import os
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QPushButton,
    QFileDialog, QLabel, QListView, QMenu, QDialog, QDialogButtonBox,
    QVBoxLayout as QVLayout
)
from PyQt6.QtCore import Qt, QSettings, QStringListModel, QPoint

from settings import file_extension


class RecentFilesDialog(QDialog):
    def __init__(self, recent_files, on_file_chosen, parent=None):
        super().__init__(parent)
        self.setWindowTitle("All Recent Experiments")
        self.on_file_chosen = on_file_chosen

        layout = QVLayout()
        self.model = QStringListModel(recent_files)
        self.view = QListView()
        self.view.setModel(self.model)
        self.view.clicked.connect(self.handle_clicked)
        self.view.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.view.customContextMenuRequested.connect(self.show_context_menu)

        layout.addWidget(self.view)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self.setLayout(layout)

    def handle_clicked(self, index):
        path = self.model.data(index, Qt.ItemDataRole.DisplayRole)
        if path:
            self.on_file_chosen(path, new=False)
            self.accept()

    def show_context_menu(self, pos: QPoint):
        index = self.view.indexAt(pos)
        if not index.isValid():
            return
        path = self.model.data(index, Qt.ItemDataRole.DisplayRole)

        menu = QMenu(self)
        action_new_template = menu.addAction("New From Template")

        action = menu.exec(self.view.mapToGlobal(pos))
        if action == action_new_template:
            self.on_file_chosen(path, template=True)
            self.accept()


class SplashScreen(QWidget):
    def __init__(self, on_file_chosen):
        super().__init__()
        self.on_file_chosen = on_file_chosen
        self.settings = QSettings("honeychrome", "ExperimentSelector")

        layout = QVBoxLayout()

        layout.addWidget(QLabel("Select an option to start:"))

        btn_new = QPushButton("New Experiment")
        btn_new.clicked.connect(self.new_experiment)
        layout.addWidget(btn_new)

        btn_open = QPushButton("Open Experiment")
        btn_open.clicked.connect(self.open_experiment)
        layout.addWidget(btn_open)

        btn_template = QPushButton("New Experiment from Template")
        btn_template.clicked.connect(self.new_from_template)
        layout.addWidget(btn_template)

        # recent files
        self.recent_model = QStringListModel()
        full_recent_files = self.settings.value("recent_files", [])
        if full_recent_files:
            layout.addWidget(QLabel("Recent Experiments:"))
            self.display_path_list = full_recent_files[:3]
            display_list = [os.path.basename(path) for path in self.display_path_list]
            if len(full_recent_files) > 3:
                self.display_path_list.append("…More")
                display_list.append("…More")
            self.recent_model.setStringList(display_list)

            self.recent_view = QListView()
            self.recent_view.setModel(self.recent_model)
            self.recent_view.clicked.connect(self.handle_recent_clicked)
            self.recent_view.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
            self.recent_view.customContextMenuRequested.connect(self.show_context_menu)

            layout.addWidget(self.recent_view)

        self.setLayout(layout)

    def add_recent_file(self, path):
        recent = self.settings.value("recent_files", [])
        if path in recent:
            recent.remove(path)
        recent.insert(0, path)
        self.settings.setValue("recent_files", recent)  # store full history
        display_list = recent[:3]
        if len(recent) > 3:
            display_list.append("…More")
        self.recent_model.setStringList(display_list)

    def new_experiment(self):
        file, _ = QFileDialog.getSaveFileName(self, "Create New Experiment", "", f"Experiment File (*.{file_extension})")
        if file:
            self.add_recent_file(file)
            self.on_file_chosen(file, new=True)

    def open_experiment(self):
        file, _ = QFileDialog.getOpenFileName(self, "Open Experiment", "", f"Experiment File (*.{file_extension})")
        if file:
            self.add_recent_file(file)
            self.on_file_chosen(file, new=False)

    def new_from_template(self):
        file, _ = QFileDialog.getOpenFileName(self, "Select Template Experiment", "", f"Experiment File (*.{file_extension})")
        if file:
            self.add_recent_file(file + " (from template)")
            self.on_file_chosen(file, template=True)

    def handle_recent_clicked(self, index):
        #path = self.recent_model.data(index, Qt.ItemDataRole.DisplayRole)
        path = self.display_path_list[index.row()]
        if path == "…More":
            full_recent_files = self.settings.value("recent_files", [])
            dlg = RecentFilesDialog(full_recent_files, self.on_file_chosen, self)
            dlg.exec()
        elif path:
            self.on_file_chosen(path, new=False)

    def show_context_menu(self, pos: QPoint):
        index = self.recent_view.indexAt(pos)
        if not index.isValid():
            return
        path = self.recent_model.data(index, Qt.ItemDataRole.DisplayRole)
        if path == "…More":
            return  # no context menu for "…More"

        menu = QMenu(self)
        action_new_template = menu.addAction("New From Template")

        action = menu.exec(self.recent_view.mapToGlobal(pos))
        if action == action_new_template:
            self.on_file_chosen(path, template=True)


if __name__ == "__main__":
    from PySide6.QtWidgets import QApplication

    class ExperimentView(QApplication):
        def __init__(self, argv):
            super().__init__(argv)
            self.main_window = None
            self.splash = SplashScreen(self.load_main_window)
            self.splash.show()

        def load_main_window(self, experiment_file, new=False, template=False):
            self.splash.close()
            print([experiment_file, new, template])
            # self.main_window = MainWindow(experiment_file, experiment_model, new=new, template=template)
            # self.main_window.show()

    app = ExperimentView(sys.argv)
    sys.exit(app.exec())

    # def load_main_window(experiment_file, new=False, template=False):
    #     print([experiment_file, new, template])
    #
    # app = QApplication(sys.argv)
    #
    # splash = SplashScreen(load_main_window)
    # splash.show()
