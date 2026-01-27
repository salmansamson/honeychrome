# Honeychrome
Open Source GUI App for Cytometry Acquisition and Analysis. Now in beta.

## About

For too long, our field lacked a general purpose, 
free and open-source cytometry software package. 
We are plugging that gap to provide a software package that is useful for everybody: 
power cytometrists, biologists, students, innovators. 
The app is lightweight but provides all the features one expects: 

- acquire data (starting with Cytkit, perhaps with drivers for other instruments in the future)
- import FCS files from any instrument
- provide both conventional compensation and spectral unmixing
- give simple statistical comparisons between samples, publication quality graphs and exports
- use intuitively with minimal instructions
- support the major operating systems (Windows, macOS, Linux)

It should also be fully open source, and provide a platform that innovators can exploit, 
for developing both instrumentation and data analysis and visualisation techniques.

See the blog https://cytkit.com/blog/

## Installation
You have the following options, depending on whether you want to use the Python source 
code or just download an executable. For most users, it is sufficient to download
an executable for your platform (Windows/Linux/MacOS).

### For non-technical users: download and run executable
A set of compressed binary packages are available in the releases section.
#### Windows
1. Download [Honeychrome for Windows x64](https://github.com/salmansamson/honeychrome/releases/download/v0.6.0-beta/Honeychrome-v0.6.0-windows-x64.exe)
2. Double click to run the installer

#### Linux
1. Download [Honeychrome for Linux x64](https://github.com/salmansamson/honeychrome/releases/download/v0.6.0-beta/honeychrome-v0.6.0-linux-x64.tar.gz)
2. Extract the honeychrome folder and put it somewhere appropriate
3. Change to the honeychrome folder and run ./install_linux.sh

#### Other systems
We intend to release a MacOS executable very soon. For all other systems, please follow the Python instructions below.

### For Python users: clone and run Python source
1. Clone or download the repository, navigate to the project folder. 
2. Install Python (or make sure you have already installed) version >= 3.12
3. Install a venv: python3 -m venv .venv
4. Upgrade pip: python3 -m pip install --upgrade pip
5. Install requirements: python3 -m pip install -r requirements.txt
6. Run the app: python3 src/honeychrome/main.py

## For programmers
We aim to release documentation for programmers wishing to build on Honeychrome in
new open source cytometry projects. Please contact us if you require assistance.
Honeychrome builds on several excellent open source Python packages:
- [FlowKit](https://github.com/whitews/flowkit) - for definition of gates, gating hierarchies, transforms, and FCS input/output
- [PySide6](https://pypi.org/project/PySide6/) - the GUI system, Qt for Python
- [pyqtgraph](https://www.pyqtgraph.org/) - extremely fast plotting and manipulation of plots in Qt
- Several others for processing of data, including numpy, scikit, sklearn
- Seaborn and Matplotlib for publication-quality graphics