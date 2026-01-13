# main.py
import sys
from PySide6.QtWidgets import QApplication
from main_window import MainWindow
from app_controller import AppController

def main():
    app = QApplication(sys.argv)
    view = MainWindow()
    controller = AppController(view)
    view.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()

