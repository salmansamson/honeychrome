import sys
from PySide6.QtWidgets import *
from PySide6.QtCore import Qt


class ScrollableGridExample(QWidget):
    def __init__(self):
        super().__init__()
        self.init_ui()

    def init_ui(self):
        main_layout = QVBoxLayout(self)

        # Create scroll area
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)

        # Create content widget with grid layout
        content_widget = QWidget()
        grid_layout = QGridLayout(content_widget)

        # Add multiple widgets in grid pattern
        row, col = 0, 0
        for i in range(50):
            label = QLabel(f"Item {i + 1}")
            label.setAlignment(Qt.AlignCenter)
            label.setStyleSheet("""
                QLabel {
                    background-color: #e0e0e0;
                    border: 1px solid #ccc;
                    padding: 10px;
                    margin: 2px;
                    border-radius: 5px;
                }
            """)
            label.setMinimumSize(100, 60)

            # Add to grid (3 columns)
            grid_layout.addWidget(label, row, col)

            # Update row and column
            col += 1
            if col >= 3:  # 3 columns
                col = 0
                row += 1

        # Set the content widget to scroll area
        scroll_area.setWidget(content_widget)

        main_layout.addWidget(QLabel("Scrollable Grid Layout:"))
        main_layout.addWidget(scroll_area)

        self.setWindowTitle("Scrollable Grid Layout Example")
        self.resize(400, 300)


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = ScrollableGridExample()
    window.show()
    sys.exit(app.exec())