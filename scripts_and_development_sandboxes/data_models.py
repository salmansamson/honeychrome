from datetime import datetime

# -------------------------
# Data Model
# -------------------------
class Sample:
    def __init__(self, name=None, num_points=0, date=None, file_path="", has_data=False, index=1):
        self.name = name if name else f"Sample{index}"
        self.num_points = num_points
        self.date = date if date else datetime.now()
        self.file_path = file_path
        self.has_data = has_data


class Experiment:
    """Container for experiment samples (data model separate from UI)."""
    def __init__(self):
        self.samples: list[Sample] = []

    def add_sample(self, sample: Sample):
        self.samples.append(sample)

    def remove_sample(self, index: int):
        if 0 <= index < len(self.samples):
            self.samples.pop(index)

    def rename_sample(self, index: int, new_name: str):
        if 0 <= index < len(self.samples):
            self.samples[index].name = new_name

    def get_sample(self, index: int):
        if 0 <= index < len(self.samples):
            return self.samples[index]
        return None
