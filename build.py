# build_optimized.py
import PyInstaller.__main__
import os
import shutil
import sys


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

    fcs_path = os.path.join(project_root, 'src', 'honeychrome', 'controller_components', 'example_for_dummy_acquisition.fcs')
    if os.path.exists(fcs_path):
        assets.append((fcs_path, 'honeychrome/controller_components'))

    assets_path = os.path.join(project_root, 'src', 'honeychrome', 'view_components', 'assets')
    if os.path.exists(assets_path):
        for root, dirs, files in os.walk(assets_path):
            for file in files:
                source = os.path.join(root, file)
                # Calculate relative path
                rel_dir = os.path.relpath(root, assets_path)
                if rel_dir == ".":
                    dest_dir = "assets"
                else:
                    dest_dir = os.path.join("assets", rel_dir)
                assets.append((source, dest_dir))

    return assets


def main():
    clean()

    args = ['src/honeychrome/main.py',
            '--name=honeychrome',
            '--onefile',
            '--console',
            '--strip',  # Remove debug symbols
            '--clean',
            '--noconfirm', ]

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
    heavy_packages = ['IPython', 'jedi', 'parso', 'pytest', 'tkinter', '_tkinter', 'urllib3', 'certifi', ]

    for pkg in heavy_packages:
        args.append(f'--exclude-module={pkg}')

    # Use UPX if available
    try:
        import subprocess
        subprocess.run(['which', 'upx'], capture_output=True, check=True)
        args.append('--upx-dir=/usr/bin')
    except:
        print("UPX not found, skipping compression")

    print(f"Building with {len(args)} arguments...")
    print("This will be much faster than before!")

    PyInstaller.__main__.run(args)

    # Show size
    exe_path = os.path.join('dist', 'honeychrome')
    if os.path.exists(exe_path):
        size = os.path.getsize(exe_path) / (1024 * 1024)  # MB
        print(f"\n✅ Build complete! Executable size: {size:.2f} MB")


if __name__ == "__main__":
    main()