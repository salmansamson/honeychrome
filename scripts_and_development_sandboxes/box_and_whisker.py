import sys
import numpy as np
import seaborn as sns
from PySide6.QtWidgets import QApplication, QMainWindow, QWidget, QVBoxLayout

# Matplotlib imports for embedding
from matplotlib.figure import Figure
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg


class SeabornPlotWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)

        # Create matplotlib figure + canvas
        self.figure = Figure(figsize=(6, 4))
        self.canvas = FigureCanvasQTAgg(self.figure)

        # Layout to hold the canvas
        layout = QVBoxLayout(self)
        layout.addWidget(self.canvas)

        self.draw_plot()

        # Export to PDF
        self.figure.savefig("my_figure.pdf", bbox_inches="tight")

        # Export to SVG (vector graphics)
        self.figure.savefig("my_figure.svg", bbox_inches="tight")

        # Export to PNG (raster image)
        self.figure.savefig("my_figure.png", dpi=300, bbox_inches="tight")

        print("Figure exported successfully!")

    def draw_plot(self):
        # Clean appearance for publication-like aesthetics
        sns.set_theme(style="whitegrid", context="talk")

        # Simulated dataset (replace with your own)
        np.random.seed(1)
        df = {
            "Group": np.repeat(["A", "B", "C"], 30),
            "Condition": np.tile(np.repeat(["Cond 1", "Cond 2"], 15), 3),
            "Value": np.concatenate([
                np.random.normal(10, 2, 15),
                np.random.normal(14, 3, 15),
                np.random.normal(12, 2, 15),
                np.random.normal(18, 3, 15),
                np.random.normal(9, 2, 15),
                np.random.normal(15, 4, 15),
            ])
        }

        ax = self.figure.add_subplot(111)

        sns.boxplot(
            data=df,
            x="Group",
            y="Value",
            hue="Condition",
            showfliers=False,
            width=0.6,
            palette="Set2",
            ax=ax,
        )

        # sns.barplot(
        #     data=df,
        #     x="Group",
        #     y="Value",
        #     hue="Condition",
        #     width=0.6,
        #     palette="Set2",
        #     ax=ax,
        # )

        sns.swarmplot(
            data=df,
            x="Group",
            y="Value",
            hue="Condition",
            dodge=True,
            color="k",
            alpha=0.55,
            size=6,
            ax=ax,
        )

        # Remove duplicate legends (swarmplot adds more)
        handles, labels = ax.get_legend_handles_labels()
        ax.legend(handles[:2], labels[:2], title="Condition")

        self.canvas.draw()


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Seaborn Boxplot in PySide6")
        self.resize(800, 600)

        plot_widget = SeabornPlotWidget(self)
        self.setCentralWidget(plot_widget)


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
