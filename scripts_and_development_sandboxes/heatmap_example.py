import sys
import numpy as np
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QRectF
import pyqtgraph as pg


# ---------------------------
# Generate data
# ---------------------------
data = np.array([
    [1, 4, 3],
    [2, 5, 7],
    [6, 8, 9]
], dtype=float)

rows, cols = data.shape

app = QApplication(sys.argv)

# ---------------------------
# Main window + graphics view
# ---------------------------
win = pg.GraphicsLayoutWidget()
win.setWindowTitle("Heatmap with Data Labels and Axis Labels")

plot = win.addPlot()
plot.setAspectLocked()

# Axis labels
plot.setLabel('left', 'Y Axis')
plot.setLabel('bottom', 'X Axis')

# ---------------------------
# Heatmap (ImageItem)
# ---------------------------
img = pg.ImageItem(data)
plot.addItem(img)

# Colormap
cmap = pg.colormap.get('viridis')
img.setLookupTable(cmap.getLookupTable())
img.setLevels([data.min(), data.max()])

# Correct scaling: each cell is 1×1
img.setRect(QRectF(0.0, 0.0, float(cols), float(rows)))

# Tick labels
plot.getAxis('left').setTicks([[(i, str(i)) for i in range(rows)]])
plot.getAxis('bottom').setTicks([[(i, str(i)) for i in range(cols)]])

# ---------------------------
# Add data labels on top
# ---------------------------
for y in range(rows):
    for x in range(cols):
        value = data[y, x]
        text = pg.TextItem(html=f"<span style='color:white;'>{value}</span>",
                           anchor=(0.5, 0.5))
        plot.addItem(text)
        text.setPos(x + 0.5, y + 0.5)  # center of the cell

win.show()
sys.exit(app.exec())
