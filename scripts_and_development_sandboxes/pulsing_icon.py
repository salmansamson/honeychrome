from PySide6.QtWidgets import QApplication, QMainWindow, QToolBar
from PySide6.QtCore import QPropertyAnimation, QEasingCurve
from PySide6.QtWidgets import QGraphicsOpacityEffect
from PySide6.QtGui import QIcon, QAction

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        toolbar = QToolBar("Toolbar")
        self.addToolBar(toolbar)

        self.start_action = QAction(QIcon("player-record.png"), "Start Acquisition", self)
        toolbar.addAction(self.start_action)

        # get the QToolButton that represents the action
        btn = toolbar.widgetForAction(self.start_action)
        if btn is None:
            raise RuntimeError("widgetForAction returned None — make sure action was added to the toolbar")

        # apply an opacity effect and animate it
        effect = QGraphicsOpacityEffect(btn)
        btn.setGraphicsEffect(effect)

        anim = QPropertyAnimation(effect, b"opacity", self)
        anim.setDuration(900)
        anim.setStartValue(1.0)
        anim.setKeyValueAt(0.5, 0.3)  # fade mid-way
        anim.setEndValue(1.0)
        anim.setEasingCurve(QEasingCurve.InOutQuad)
        anim.setLoopCount(-1)
        anim.start()

if __name__ == "__main__":
    app = QApplication([])
    w = MainWindow()
    w.show()
    app.exec()
