#!/usr/bin/env python3
"""
Qt Icon Browser (searchable)
----------------------------
Auto-discovers all available themed icons (Freedesktop-compatible)
and shows them in a scrollable grid with their QIcon::fromTheme() names.

Includes a live search bar to filter icons by name.
"""

import os
import sys
from pathlib import Path
from PySide6.QtWidgets import (
    QApplication, QWidget, QLabel, QScrollArea, QVBoxLayout,
    QGridLayout, QLineEdit, QSizePolicy, QHBoxLayout
)
from PySide6.QtGui import QIcon
from PySide6.QtCore import QSize, Qt, QTimer


# --- Configuration ---
ICON_DIRS = [
    "/usr/share/icons",
    "/usr/local/share/icons",
    str(Path.home() / ".icons"),
]
ICON_EXTS = (".png", ".svg", ".xpm")


def collect_icon_names():
    """Collect unique icon base names from system icon directories."""
    names = set()
    for base in ICON_DIRS:
        if not os.path.isdir(base):
            continue
        for root, _, files in os.walk(base):
            for f in files:
                if f.endswith(ICON_EXTS):
                    names.add(os.path.splitext(f)[0])
    return sorted(names)


class IconGallery(QWidget):
    def __init__(self, icon_names):
        super().__init__()
        self.all_icon_names = icon_names
        self.setWindowTitle("Qt Icon Browser — Searchable Freedesktop Icon Gallery")
        self.resize(1000, 800)

        # --- Layouts ---
        main_layout = QVBoxLayout(self)
        search_layout = QHBoxLayout()
        self.search_box = QLineEdit()
        self.search_box.setPlaceholderText("🔍 Search icons by name...")
        self.search_box.textChanged.connect(self.schedule_filter)
        search_layout.addWidget(self.search_box)
        main_layout.addLayout(search_layout)

        # Scrollable area for icons
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.container = QWidget()
        self.scroll.setWidget(self.container)
        main_layout.addWidget(self.scroll)

        # Grid layout inside scroll area
        self.grid = QGridLayout(self.container)
        self.grid.setSpacing(12)

        # Timer for debounce on filtering
        self.filter_timer = QTimer()
        self.filter_timer.setSingleShot(True)
        self.filter_timer.timeout.connect(self.apply_filter)

        # Build initial grid
        self.populate_icons(self.all_icon_names)

    def schedule_filter(self):
        """Delay filtering slightly for smoother typing."""
        self.filter_timer.start(200)

    def apply_filter(self):
        query = self.search_box.text().strip().lower()
        if not query:
            filtered = self.all_icon_names
        else:
            filtered = [n for n in self.all_icon_names if query in n.lower()]
        self.populate_icons(filtered)

    def clear_grid(self):
        while self.grid.count():
            item = self.grid.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()

    def populate_icons(self, icon_names):
        """Populate grid with icons."""
        self.clear_grid()
        icon_size = QSize(48, 48)
        cols = 10

        for i, name in enumerate(icon_names):
            row, col = divmod(i, cols)
            icon = QIcon.fromTheme(name)

            label = QLabel()
            label.setAlignment(Qt.AlignCenter)
            label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

            if not icon.isNull():
                label.setPixmap(icon.pixmap(icon_size))
            else:
                label.setText("❌")

            text = QLabel(name)
            text.setAlignment(Qt.AlignCenter)
            text.setWordWrap(True)
            text.setStyleSheet("font-size: 12px; color: #fff;")

            cell = QWidget()
            vbox = QVBoxLayout(cell)
            vbox.setContentsMargins(4, 4, 4, 4)
            vbox.addWidget(label)
            vbox.addWidget(text)
            self.grid.addWidget(cell, row, col)


def main():
    app = QApplication(sys.argv)
    print("🔍 Scanning for available icon names...")
    names = collect_icon_names()
    print(f"✅ Found {len(names)} unique icon names.")
    if not names:
        print("⚠️ No icons found — check your icon theme paths or install a theme.")
        sys.exit(1)

    gallery = IconGallery(names)
    gallery.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
