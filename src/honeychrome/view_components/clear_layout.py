def clear_layout(layout):
    if layout is not None:
        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater() # Safely schedules the widget for deletion
            else:
                # If there's a nested layout, clear it recursively
                clear_layout(item.layout())