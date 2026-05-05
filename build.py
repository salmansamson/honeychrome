# build_optimized.py
import PyInstaller.__main__
import os
import shutil
import sys
import platform

def clean():
    """Clean build directories"""
    for folder in ['dist', 'build']:
        if os.path.exists(folder):
            print(f"Cleaning {folder}...")
            shutil.rmtree(folder)


def get_project_files():
    """Get only essential project files"""
    project_root = os.path.dirname(os.path.abspath(__file__))
    assets = []

    fcs_path = os.path.join(project_root, 'src', 'honeychrome', 'instrument_driver_components', 'data')
    fcs_path_destination = os.path.join('honeychrome', 'instrument_driver_components', 'data')
    assets.append((fcs_path, fcs_path_destination))

    assets_path = os.path.join('src', 'honeychrome', 'view_components', 'assets')
    assets_path_destination = os.path.join('honeychrome', 'view_components', 'assets')
    assets.append((assets_path, assets_path_destination))

    templates_path = os.path.join('src', 'honeychrome', 'plugin_templates')
    templates_dest = os.path.join('honeychrome', 'plugin_templates')
    assets.append((templates_path, templates_dest))

    return assets

def main():
    clean()
    icon_path = os.path.join('src', 'honeychrome', 'view_components', 'assets', 'cytkit_web_logo.ico')

    args = ['src/honeychrome/main.py',
            '--name=honeychrome',
            '--noconsole',
            '--clean',
            '--noconfirm',
            '--onedir',
            '--copy-metadata=pandas',
            '--copy-metadata=matplotlib',
            f'--icon={icon_path}'
            ]

    # Make the honeychrome package importable by external plugin scripts
    args.append('--hidden-import=honeychrome')
    args.append('--hidden-import=honeychrome.settings')
    args.append('--hidden-import=honeychrome.plugin_loaders')
    args.append('--runtime-hook=hooks/runtime-patch-syspath.py')

    # Add project files
    sep = os.pathsep
    for source, dest in get_project_files():
        args.append(f'--add-data={source}{sep}{dest}')

    # Add hooks directory
    args.append('--additional-hooks-dir=hooks')
    args.append('--runtime-hook=hooks/runtime-optional-deps.py')

    # Essential hidden imports
    essential_hidden = ['numpy._core._exceptions',
                        'numpy._core._multiarray_umath',
                        'numpy.fft._pocketfft_internal',
                        'pytz',
                        'scipy.special.cython_special',
                        ]

    for imp in essential_hidden:
        args.append(f'--hidden-import={imp}')

    # Exclude heavy packages
    # heavy_packages = ['IPython', 'jedi', 'parso', 'bokeh', 'sklearn', 'matplotlib', 'pyqtgraph', 'scipy.sparse', 'scipy.optimize', 'scipy.special', 'scipy.linalg', 'scipy.stats', 'lxml', 'jinja2', 'docx', 'pytest', 'pandas.plotting', 'tkinter', '_tkinter', 'PIL', 'pyarrow', 'urllib3', 'certifi', ]
    heavy_packages = ['IPython', 'jedi', 'parso', 'pytest', 'tkinter', '_tkinter', 'bokeh', 'bokeh.plotting', 'bokeh.models', 'bokeh.layouts', 'narwhals']

    for pkg in heavy_packages:
        args.append(f'--exclude-module={pkg}')

    PyInstaller.__main__.run(args)

    # Show size
    exe_path = os.path.join('dist', 'honeychrome')
    if os.path.exists(exe_path):
        size = os.path.getsize(exe_path) / (1024 * 1024)  # MB
        print(f"Build complete! Executable size: {size:.2f} MB")


if __name__ == "__main__":
    main()