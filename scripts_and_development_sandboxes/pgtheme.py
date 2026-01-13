import sys
import numpy as np
import pyqtgraph as pg
from PySide6 import QtWidgets, QtGui, QtCore

# Set pyqtgraph options first
pg.setConfigOptions(useOpenGL=True)

app = QtWidgets.QApplication(sys.argv)
app.setStyle("Fusion")

# Theme detection
palette = app.palette()
window_color = palette.color(QtGui.QPalette.ColorRole.Window)
brightness = (window_color.red() * 0.299 +
              window_color.green() * 0.587 +
              window_color.blue() * 0.114)

if brightness < 128:
    pg.setConfigOptions(background='#2b2b2b', foreground='#ffffff')
    theme_name = "Dark"
else:
    pg.setConfigOptions(background='#ffffff', foreground='#000000')
    theme_name = "Light"

# SIMPLER APPROACH: Use GraphicsLayoutWidget directly as main window
graph_widget = pg.GraphicsLayoutWidget()
graph_widget.setWindowTitle(f"PySide6 PyQtGraph - {theme_name} Theme")

# Add plots directly to the GraphicsLayoutWidget
plot1 = graph_widget.addPlot(title="Trigonometric Functions")
x = np.linspace(0, 4*np.pi, 200)
plot1.plot(x, np.sin(x), pen=pg.mkPen(color='r', width=2), name="sin(x)")
plot1.plot(x, np.cos(x), pen=pg.mkPen(color='g', width=2), name="cos(x)")
plot1.addLegend()

graph_widget.nextRow()
plot2 = graph_widget.addPlot(title="Scatter Data")
plot2.plot(np.random.normal(size=50), np.random.normal(size=50),
           pen=None, symbol='o', symbolSize=8, symbolBrush='b')

graph_widget.resize(1000, 800)
graph_widget.show()

print(f"Detected theme: {theme_name}")

sys.exit(app.exec())