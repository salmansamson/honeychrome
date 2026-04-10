import umap
import hdbscan
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QTableWidgetItem
from line_profiler import profile

from PySide6 import QtWidgets, QtGui, QtCore
import numpy as np


class CopyableTableWidget(QtWidgets.QTableWidget):
    def __init__(self, list_of_dicts, headers):
        """
        list_of_dicts: list where each element is a dict containing the data for a row of the table
        headers: ordered list of columns (strings)
        """
        rows, columns = len(list_of_dicts), len(headers)
        super().__init__(rows, columns)

        self.setHorizontalHeaderLabels(headers)
        self.verticalHeader().setVisible(False)
        self.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self.setSelectionMode(QtWidgets.QAbstractItemView.ExtendedSelection)
        self.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        self.setSortingEnabled(False)  # Allow sorting by count or ID

        # 3. Populate Rows
        for i, row_data in enumerate(list_of_dicts):
            for j, column_name in enumerate(headers):
                value = row_data.get(column_name, "")
                item = QTableWidgetItem()

                # Check if the value is a Hex Color string
                if isinstance(value, str) and value.startswith("#") and len(value) == 7:
                    try:
                        # Set the background color
                        item.setBackground(QColor(value))
                        # Optionally, set the text to the hex code or leave it empty
                        item.setData(Qt.EditRole, value)
                    except Exception:
                        # Fallback if the string isn't a valid color
                        item.setData(Qt.EditRole, value)
                else:
                    item.setData(Qt.EditRole, value)

                self.setItem(i, j, item)

        self.setSortingEnabled(True)  # Allow sorting by count or ID
        self.resizeColumnsToContents()
        self.horizontalHeader().setSectionResizeMode(QtWidgets.QHeaderView.Stretch)

    def keyPressEvent(self, event):
        """Handles Ctrl+C to copy selected rows as TSV"""
        if event.matches(QtGui.QKeySequence.Copy):
            self.copy_to_clipboard()
        else:
            super().keyPressEvent(event)

    def copy_to_clipboard(self):
        selection = self.selectedRanges()
        if not selection:
            return

        output = []
        # Support multi-range selection
        for r_range in selection:
            for r in range(r_range.topRow(), r_range.bottomRow() + 1):
                row_data = [self.item(r, c).text() for c in range(self.columnCount())]
                output.append("\t".join(row_data))

        QtWidgets.QApplication.clipboard().setText("\n".join(output))

@profile
def main():
    import numpy as np

    # Create a dummy NumPy array
    # 3000 samples, 20 dimensions
    n_samples = 300
    n_features = 5
    data = np.random.rand(n_samples, n_features).astype(np.float32)

    # Creating some "clusters" so the plot isn't just a random blob
    data[:100] += 2
    data[100:200] -= 2

    # Initialize and fit UMAP
    # n_neighbors: controls local vs global structure (5 to 50 is typical)
    # min_dist: controls how tightly points are packed (0.1 is default)

    subsample = data[np.random.choice(np.arange(len(data)), 100)]
    reducer = umap.UMAP(n_neighbors=15, min_dist=0.1, transform_queue_size=1.0, n_components=2).fit(subsample)
    embedding = reducer.transform(subsample)

    # Cluster the UMAP output with HDBSCAN
    clusterer = hdbscan.HDBSCAN(min_cluster_size=10, prediction_data=True).fit(embedding)
    labels = clusterer.labels_

    from pyqtgraph.Qt import QtCore, QtWidgets
    import sys

    # 1. Setup the Application
    app = QtWidgets.QApplication(sys.argv)
    from matplotlib import pyplot as plt
    import colorcet as cc
    import numpy as np

    # 1. Get unique labels
    unique_labels = np.unique(labels).astype(int)

    # 2. Build the Glasbey mapping (Handling Noise as Gray)
    palette = cc.glasbey
    label_to_color = {}
    for i, unique_label in enumerate(unique_labels):
        l = int(unique_label)
        if l == -1:
            label_to_color[l] = "#7f7f7f"  # Standard Gray for noise
        else:
            # Use modulo to wrap around if there are > 256 clusters
            label_to_color[l] = palette[i % len(palette)]

    headers = ['Index', 'Colour', 'Count']
    table_data = []
    for i, unique_label in enumerate(unique_labels):
        l = int(unique_label)
        table_data.append({'Index':l, 'Colour':label_to_color[l], 'Count':int(np.sum(labels==l))})

    # 3. Initialize the table
    table = CopyableTableWidget(table_data, headers)
    table.show()

    app.exec()

    plt.figure(figsize=(10, 7))
    plot_colors = [label_to_color[l] for l in labels]
    plt.scatter(embedding[:, 0], embedding[:, 1], c=plot_colors, s=5)
    plt.colorbar(label='Cluster Label')
    plt.title('UMAP + HDBSCAN Clustering', fontsize=15)
    plt.show()

main()
