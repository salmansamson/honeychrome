# controller/app_controller.py
from file_model import FileModel

class AppController:
    def __init__(self, view):
        self.model = FileModel()
        self.view = view
        self._connect_signals()

    def _connect_signals(self):
        self.view.newFileRequested.connect(self.new_file)
        self.view.openFileRequested.connect(self.open_file)
        self.view.saveFileRequested.connect(self.save_file)
        self.view.calculateRequested.connect(self.do_calculation)

    def new_file(self):
        self.model.new()
        print("New file requested")
        self.view.show_message("New file created")

    def open_file(self, path):
        print(f"Open file requested {path}")
        self.model.load(path)
        self.view.update_from_model(self.model.data)

    def save_file(self, path=None):
        self.model.save(path)
        self.view.show_message("File saved")

    def do_calculation(self):
        result = sum(self.model.data.get("numbers", []))
        self.view.popup_message(result)
