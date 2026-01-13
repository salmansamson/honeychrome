from PySide6.QtWidgets import QApplication, QFileDialog, QMessageBox
from PySide6.QtCore import QDir
from pathlib import Path
import sys

from settings import experiments_folder, file_extension
base_directory = str(Path.home() / experiments_folder)

class NewFileDialog(QFileDialog):
    def __init__(self, parent=None):
        super().__init__(parent, "New Experiment Name", base_directory, "Experiment File (*.kit);;All Files (*)")
        self.setAcceptMode(QFileDialog.AcceptSave)
        self.setFileMode(QFileDialog.AnyFile)
        self.setOption(QFileDialog.DontConfirmOverwrite, True)  # we handle overwrite ourselves

    def accept(self):
        selected = self.selectedFiles()
        if not selected:
            return

        path = Path(selected[0]).expanduser()

        # Basic empty-string guard
        if not path.name.strip():
            QMessageBox.warning(self, "Invalid Name", "Filename cannot be empty.")
            return

        # Check for invalid characters (example for Windows + common restrictions)
        invalid_chars = set(r'\/:*?"<>|')
        if any(c in invalid_chars for c in path.name):
            QMessageBox.warning(self, "Invalid Name", f"Filename contains invalid characters: {invalid_chars}")
            return

        # Reject filenames that already exist
        if path.exists():
            QMessageBox.warning(self, "File Exists", f"The file '{path.name}' already exists.\nPlease choose another name.")
            return

        # If all checks pass, accept the dialog
        super().accept()


if __name__ == "__main__":
    app = QApplication(sys.argv)

    dlg = NewFileDialog()

    if dlg.exec():
        result_path = Path(dlg.selectedFiles()[0])
        print("Approved path:", result_path)

    sys.exit(0)
