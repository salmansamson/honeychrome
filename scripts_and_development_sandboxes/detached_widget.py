import sys
from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, QPushButton, QLabel, QDialog,
                               QGridLayout, QFrame)
from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QColor


class WidgetContainer(QFrame):
    """Container that holds the actual widget content"""

    def __init__(self, title="Widget", color="#e0e0e0"):
        super().__init__()
        self.title = title
        self.color = color
        self.original_parent = None
        self.original_position = None
        self.original_layout = None

        self.setFrameStyle(QFrame.Box | QFrame.Raised)
        self.setLineWidth(2)
        self.setMinimumSize(150, 100)

        # Create content layout
        layout = QVBoxLayout()

        self.title_label = QLabel(title)
        self.title_label.setAlignment(Qt.AlignCenter)
        self.title_label.setStyleSheet("font-weight: bold;")

        self.color_display = QLabel()
        self.color_display.setMinimumHeight(60)
        self.color_display.setStyleSheet(f"background-color: {color}; border-radius: 5px;")

        layout.addWidget(self.title_label)
        layout.addWidget(self.color_display)
        self.setLayout(layout)

        # Set style
        self.setStyleSheet("""
            WidgetContainer {
                background-color: white;
                border-radius: 5px;
            }
            WidgetContainer:hover {
                background-color: #f0f8ff;
                border: 2px solid #0078d4;
            }
        """)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Modal Widget Example - Working Version")
        self.setGeometry(100, 100, 800, 600)

        # Store references to widget containers and their positions
        self.widget_containers = []
        self.widget_positions = {}  # Maps widget to (row, col, rowspan, colspan)

        # Create central widget
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        # Create main layout
        main_layout = QVBoxLayout()
        central_widget.setLayout(main_layout)

        # Add title
        title = QLabel("Double-click any widget to move it to a modal window")
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet("font-size: 16px; font-weight: bold; padding: 10px;")
        main_layout.addWidget(title)

        # Create grid layout for widgets
        self.grid_layout = QGridLayout()
        self.grid_layout.setSpacing(10)

        # Create some sample widgets
        widgets_data = [("Widget 1", "#ffcccc"), ("Widget 2", "#ccffcc"), ("Widget 3", "#ccccff"),
            ("Widget 4", "#ffffcc"), ("Widget 5", "#ffccff"), ("Widget 6", "#ccffff"), ]

        # Add widgets to grid
        for i, (title, color) in enumerate(widgets_data):
            row = i // 3
            col = i % 3

            # Create container
            container = WidgetContainer(title, color)
            self.widget_containers.append(container)

            # Store position
            self.widget_positions[container] = (row, col, 1, 1)

            # Add to grid
            self.grid_layout.addWidget(container, row, col)

            # Install event filter for double-click
            container.installEventFilter(self)

        main_layout.addLayout(self.grid_layout)

        # Add instructions
        instructions = QLabel("Double-click any colored widget to open it in a modal window.\n"
                              "Close the modal window to restore it to its original position.")
        instructions.setAlignment(Qt.AlignCenter)
        instructions.setStyleSheet("color: #666666; padding: 10px; font-style: italic;")
        main_layout.addWidget(instructions)

        # Add stretch to push everything up
        main_layout.addStretch()

    def eventFilter(self, obj, event):
        """Handle double-click events on widgets"""
        if event.type() == event.Type.MouseButtonDblClick:
            if obj in self.widget_containers:
                self.open_widget_in_modal(obj)
                return True
        return super().eventFilter(obj, event)

    def open_widget_in_modal(self, widget_container):
        """Open widget in a modal dialog"""
        # Store original widget reference
        self.current_modal_widget = widget_container

        # Create a copy of the widget for the modal
        modal_widget = WidgetContainer(widget_container.title, widget_container.color)
        modal_widget.setMinimumSize(300, 200)

        # Create modal dialog
        dialog = QDialog(self)
        dialog.setWindowTitle(f"Modal: {widget_container.title}")
        dialog.setModal(True)
        dialog.setMinimumSize(400, 300)

        # Create layout for dialog
        layout = QVBoxLayout()
        layout.addWidget(self.current_modal_widget)

        # Add close button
        close_btn = QPushButton("Close and Restore")
        close_btn.clicked.connect(dialog.accept)
        layout.addWidget(close_btn)

        dialog.setLayout(layout)

        # Show dialog and wait for it to close
        dialog.exec()

        # Restore original widget when dialog closes

        row, col, _, _ = self.widget_positions[widget_container]


        self.grid_layout.addWidget(widget_container, row, col)


def main():
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()