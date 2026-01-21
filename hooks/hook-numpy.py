# hooks/hook-numpy.py for numpy >=1.25.0
from PyInstaller.utils.hooks import collect_all, collect_submodules, get_module_file_attribute
import numpy

# Collect all numpy files
datas, binaries, hiddenimports = collect_all('numpy')

# Get numpy version
numpy_version = numpy.__version__
print(f"Including numpy version {numpy_version}")

hiddenimports.extend([
    'numpy._core',
    'numpy._core._exceptions',
    'numpy._core._multiarray_umath',
    'numpy._core._pocketfft_umath',
])
