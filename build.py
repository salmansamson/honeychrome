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

    fcs_path = os.path.join(project_root, 'src', 'honeychrome', 'controller_components', 'data')
    fcs_path_destination = os.path.join('honeychrome', 'controller_components', 'data')
    assets.append((fcs_path, fcs_path_destination))

    assets_path = os.path.join('src', 'honeychrome', 'view_components', 'assets')
    assets_path_destination = os.path.join('honeychrome', 'view_components', 'assets')
    assets.append((assets_path, assets_path_destination))

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
            f'--icon={icon_path}'
            ]

    # 2. Add --strip ONLY if not on Windows
    if platform.system() != "Windows":
        args.append('--strip')

    # Add project files
    for source, dest in get_project_files():
        args.append(f'--add-data={source}:{dest}')

    # Add hooks directory
    args.append('--additional-hooks-dir=hooks')
    args.append('--runtime-hook=hooks/runtime-optional-deps.py')

    # Essential hidden imports
    essential_hidden = ['numpy._core._exceptions', 'numpy._core._multiarray_umath', 'numpy.fft._pocketfft_internal', ]

    for imp in essential_hidden:
        args.append(f'--hidden-import={imp}')

    # Exclude heavy packages
    # heavy_packages = ['IPython', 'jedi', 'parso', 'bokeh', 'sklearn', 'matplotlib', 'pyqtgraph', 'scipy.sparse', 'scipy.optimize', 'scipy.special', 'scipy.linalg', 'scipy.stats', 'lxml', 'jinja2', 'docx', 'pytest', 'pandas.plotting', 'tkinter', '_tkinter', 'PIL', 'pyarrow', 'urllib3', 'certifi', ]
    heavy_packages = ['IPython', 'jedi', 'parso', 'pytest', 'tkinter', '_tkinter', 'urllib3', 'certifi',
                      'bokeh', 'bokeh.plotting', 'bokeh.models', 'bokeh.layouts', 'scipy.stats', 'scipy.interpolate', 'scipy.fft', 'narwhals']

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