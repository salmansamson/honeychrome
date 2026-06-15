# build_optimized.py
import PyInstaller.__main__
import os
import shutil
import subprocess
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

    label_data_path = os.path.join(project_root, 'src', 'honeychrome', 'data')
    label_data_destination = os.path.join('honeychrome', 'data')
    assets.append((label_data_path, label_data_destination))

    # C kernel extension (compiled before this script runs)
    kernel_dir = os.path.join(
        project_root, 'src', 'honeychrome', 'controller_components'
    )
    kernel_dest = os.path.join('honeychrome', 'controller_components')
    for fname in os.listdir(kernel_dir):
        if fname.startswith('_af_kernel') and fname.split('.')[-1] in ('so', 'pyd', 'dylib'):
            assets.append((os.path.join(kernel_dir, fname), kernel_dest))

    # macOS: bundle libomp.dylib explicitly — Homebrew path is non-standard
    # and PyInstaller will not find it via normal shared-library scanning.
    # On Windows/Linux the OpenMP runtime (vcomp.dll / libgomp.so) is found
    # automatically and needs no explicit entry here.
    if platform.system() == 'Darwin':
        try:
            libomp_prefix = subprocess.check_output(
                ['brew', '--prefix', 'libomp'], stderr=subprocess.DEVNULL
            ).decode().strip()
            libomp_path = os.path.join(libomp_prefix, 'lib', 'libomp.dylib')
            if os.path.exists(libomp_path):
                # Place alongside the kernel extension so @loader_path resolves it
                assets.append((libomp_path, kernel_dest))
        except (subprocess.CalledProcessError, FileNotFoundError):
            print('WARNING: libomp not found via brew — OpenMP will not be '
                  'available in the built app; falling back to NumPy path.')

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

    if platform.system() == "Darwin":
        args.append('--windowed')

    # Make the honeychrome package importable by external plugin scripts
    args.append('--hidden-import=honeychrome')
    args.append('--hidden-import=honeychrome.settings')
    args.append('--hidden-import=honeychrome.plugin_loaders')
    args.append('--hidden-import=honeychrome.controller_components.af_kernel_wrapper')
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