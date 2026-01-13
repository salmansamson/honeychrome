# model/file_model.py
import json
from pathlib import Path

class FileModel:
    def __init__(self):
        self.data = {}
        self.file_path = None

    def new(self):
        self.data = {}
        self.file_path = None

    def load(self, path: Path):
        with open(path, "r") as f:
            self.data = json.load(f)
        self.file_path = path

    def save(self, path: Path = None):
        if path is not None:
            self.file_path = path
        if self.file_path is None:
            raise ValueError("No file path set for saving")
        with open(self.file_path, "w") as f:
            json.dump(self.data, f, indent=2)