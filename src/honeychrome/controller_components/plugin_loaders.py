import importlib.util
from pathlib import Path
import sys

from PySide6.QtCore import QSettings
from honeychrome.settings import experiments_folder

PLUGIN_DIR = Path.home() / experiments_folder / "plugins"
plugins_path = Path(PLUGIN_DIR)

settings = QSettings("honeychrome", "app_configuration")

def load_plugin_modules():
    """Import and execute plugin modules only — no Qt widget creation.
    Safe to call from a background thread."""
    loaded_modules = {}
    # Iterate over all *_tab.py files in the directory
    for file_path in plugins_path.glob("*_tab.py"):
        if settings.value(f"EnablePlugin_{file_path}", False, type=bool):
            # 1. Create a module name
            module_name = f"{plugins_path.name}.{file_path.stem}"
            # 2. Create a module spec from the file location
            spec = importlib.util.spec_from_file_location(module_name, file_path)
            if spec and spec.loader:
                # 3. Create a new module based on the spec
                module = importlib.util.module_from_spec(spec)
                # 4. Add to sys.modules so it behaves like a normal import
                sys.modules[module_name] = module
                # 5. Execute the module to actually load its code
                spec.loader.exec_module(module)
                print(f"Successfully loaded plugin module: {module_name}")
                loaded_modules[module_name] = module
    return loaded_modules


def instantiate_plugin_widgets(loaded_modules, bus, controller):
    """Create PluginWidget instances from pre-loaded modules.
    Must be called on the main (Qt) thread."""
    tab_plugins = {}
    for module_name, module in loaded_modules.items():
        # 6. initialise widget to be put in the tab
        widget = module.PluginWidget(bus=bus, controller=controller)
        print(f"Successfully instantiated plugin: {module_name}")
        tab_plugins[module_name] = {'module': module, 'widget': widget}
    return tab_plugins


def load_tabbed_plugins(bus, controller):
    """Original synchronous entry point — kept for compatibility."""
    loaded_modules = load_plugin_modules()
    return instantiate_plugin_widgets(loaded_modules, bus, controller)
