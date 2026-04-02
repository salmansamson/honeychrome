import importlib.util
from pathlib import Path
import sys

current_file = Path(__file__).resolve()
PROJECT_ROOT = current_file.parent.parent.parent.parent
PLUGIN_DIR = PROJECT_ROOT / "plugins"

def load_tabbed_plugins(bus, controller):
    plugins_path = Path(PLUGIN_DIR)

    tab_plugins = {}

    # Iterate over all *_tab.py files in the directory
    for file_path in plugins_path.glob("*_tab.py"):

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

            if module.plugin_enabled:
                # 6. initialise widget to be put in the tab
                widget = module.PluginWidget(bus=bus, controller=controller)

                print(f"Successfully loaded plugin: {module_name}")
                tab_plugins[module_name] = {'module':module, 'widget':widget}

    return tab_plugins
