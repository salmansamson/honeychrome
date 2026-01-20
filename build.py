# build.py in project root
import PyInstaller.__main__
import os
import sys

# Add src to Python path to ensure imports work
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

# PyInstaller.__main__.run([
#     'src/honeychrome/main.py',
#     '--name=honeychrome',
#     '--onefile',
#     '--clean',
#     '--distpath=./dist',
#     '--workpath=./build',
#     '--specpath=./',
#     '--add-data=src/honeychrome:src/honeychrome',  # If you have data files
#     '--hidden-import=some_module',  # Add any missing imports
# ])

PyInstaller.__main__.run([
    'src/honeychrome/main.py',
    '--name=honeychrome',
    '--onefile',
    '--additional-hooks-dir=hooks',  # Add hooks directory
    '--clean',
    '--distpath=./dist',
    '-y'
])