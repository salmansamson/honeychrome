from PySide6.QtCore import QSettings

def clear_settings_by_scope():
    """Clear settings based on organization and application name"""
    # Specify your organization and app name
    settings = QSettings("honeychrome")
    settings.clear()
    settings.sync()

clear_settings_by_scope()