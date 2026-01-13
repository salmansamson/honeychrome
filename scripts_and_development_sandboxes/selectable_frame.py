from PySide6.QtWidgets import QApplication, QWidget, QGridLayout, QLabel, QFrame
from PySide6.QtCore import Qt


class SelectableFrame(QFrame):
    def __init__(self, text, parent=None):
        super().__init__(parent)
        self.label = QLabel(text, self)
        self.label.setAlignment(Qt.AlignCenter)
        self.setFixedSize(100, 100)

        self.setFrameShape(QFrame.NoFrame)
        self.setLineWidth(3)
        self.selected = False

    def mousePressEvent(self, event):
        if self.parent() and hasattr(self.parent(), "select_widget"):
            self.parent().select_widget(self)


class GridWidget(QWidget):
    def __init__(self):
        super().__init__()
        layout = QGridLayout(self)
        self.widgets = []

        for i in range(3):
            for j in range(3):
                frame = SelectableFrame(f"{i}, {j}", self)
                layout.addWidget(frame, i, j)
                self.widgets.append(frame)

        self.selected_widget = None

    def select_widget(self, widget):
        # Deselect previous
        if self.selected_widget:
            self.selected_widget.setFrameShape(QFrame.NoFrame)

        # Select new
        widget.setFrameShape(QFrame.Box)
        widget.setFrameShadow(QFrame.Plain)
        widget.setLineWidth(3)
        self.selected_widget = widget


if __name__ == "__main__":
    app = QApplication([])
    window = GridWidget()
    window.show()
    app.exec()
