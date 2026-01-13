import sys

from PySide6.QtGui import Qt, QAction
from PySide6.QtWidgets import *


class GoodDockingPractice(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setup_ui()

    def setup_ui(self):
        # Always have a meaningful central widget
        self.text_edit = QTextEdit()
        self.text_edit.setPlainText("This is the main working area - always visible and focused.")
        self.setCentralWidget(self.text_edit)

        # Create useful, logical dock widgets
        self.create_tool_dock()
        self.create_properties_dock()
        self.create_console_dock()

        # Set reasonable default sizes
        self.resize(1200, 800)

        # Optional: Restore previous layout
        self.restore_default_layout()

    def create_tool_dock(self):
        """Tools dock - logical grouping"""
        dock = QDockWidget("Tools", self)
        widget = QWidget()
        layout = QVBoxLayout(widget)

        # Group related tools
        layout.addWidget(QLabel("Editing Tools:"))
        layout.addWidget(QPushButton("Select"))
        layout.addWidget(QPushButton("Move"))
        layout.addWidget(QPushButton("Scale"))

        layout.addStretch()
        dock.setWidget(widget)
        dock.setMinimumWidth(150)
        self.addDockWidget(Qt.LeftDockWidgetArea, dock)

    def create_properties_dock(self):
        """Properties dock - context-sensitive"""
        dock = QDockWidget("Properties", self)
        widget = QWidget()
        layout = QVBoxLayout(widget)

        layout.addWidget(QLabel("Current Selection:"))
        layout.addWidget(QLabel("No selection"))
        layout.addStretch()

        dock.setWidget(widget)
        dock.setMinimumWidth(200)
        self.addDockWidget(Qt.RightDockWidgetArea, dock)

    def create_console_dock(self):
        """Console dock - typically at bottom"""
        dock = QDockWidget("Console", self)
        console = QTextEdit()
        console.setMaximumHeight(150)
        console.setPlainText("Application messages...")
        dock.setWidget(console)
        self.addDockWidget(Qt.BottomDockWidgetArea, dock)

    def restore_default_layout(self):
        """Provide a way to reset to sane defaults"""
        reset_action = QAction("Reset Layout", self)
        reset_action.triggered.connect(self.reset_layout)
        self.toolbar = self.addToolBar("Layout")
        self.toolbar.addAction(reset_action)

    def reset_layout(self):
        """Reset to default layout"""
        # Implementation to reset dock positions
        pass


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = GoodDockingPractice()
    window.setWindowTitle("Good Docking Practices")
    window.show()
    sys.exit(app.exec())