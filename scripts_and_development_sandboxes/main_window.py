# view/main_window.py
from PySide6.QtWidgets import QMainWindow, QFileDialog, QMessageBox
from PySide6.QtCore import Signal

class MainWindow(QMainWindow):
    newFileRequested = Signal()
    openFileRequested = Signal(str)
    saveFileRequested = Signal(str)
    calculateRequested = Signal()

    def __init__(self):
        super().__init__()
        self.setWindowTitle("MVC Qt Example")
        # build menus/buttons and connect to signals
        self._create_menus()

    def _create_menus(self):
        file_menu = self.menuBar().addMenu("&File")
        file_menu.addAction("New", self.newFileRequested.emit)
        file_menu.addAction("Open", self._open_dialog)
        file_menu.addAction("Save", self._save_dialog)

        tools_menu = self.menuBar().addMenu("&Tools")
        tools_menu.addAction("Calculate", self.calculateRequested.emit)

    def _open_dialog(self):
        path, _ = QFileDialog.getOpenFileName(self, "Open File", "", "JSON Files (*.json)")
        if path:
            self.openFileRequested.emit(path)

    def _save_dialog(self):
        path, _ = QFileDialog.getSaveFileName(self, "Save File", "", "JSON Files (*.json)")
        if path:
            self.saveFileRequested.emit(path)

    def update_from_model(self, data):
        # Update widgets based on data
        print("Updating UI with data:", data)

    def display_result(self, result):
        QMessageBox.information(self, "Result", f"Calculation result: {result}")

    def show_message(self, text):
        QMessageBox.information(self, "Info", text)
