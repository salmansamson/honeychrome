# Honeychrome
Open Source GUI App for Cytometry Acquisition and Analysis. Now in beta.

<div>
  <img src="other/honeychrome screenshot animation.webp" alt="Animated Demo" width="800">
</div>

Our aim is to make Honeychrome so intuitive that you don't need instructions. But just in case, we have prepared this instructional video [Introduction to Honeychrome in 30 Minutes](https://youtu.be/PF78J3f5zsg).

## Mission statement

For too long, our field lacked a general purpose, 
free and open-source cytometry software package. 
We are plugging that gap to provide a software package that is useful for everybody: 
power cytometrists, biologists, students, innovators. 
The app is lightweight but provides all the features one expects: 

- acquire data (starting with Cytkit, perhaps with drivers for other instruments in the future)
- analyse data from any instrument's FCS files 
- provide both conventional compensation and spectral unmixing
- give simple statistical comparisons between samples, publication-quality graphs and exports
- provide intuitive usability with minimal instructions
- support the major operating systems (Windows, MacOS, Linux...)

Honeychrome is fully open source to provide a platform that innovators can exploit, 
for developing both new instrumentation and new methods in data analysis/visualisation.

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
2. Extract the honeychrome folder and put it somewhere appropriate for the single user or system
3. Change to the honeychrome folder and run ./install_linux.sh

#### MacOs
We intend to release a MacOS executable very soon; in the meantime, please follow the Python instructions below. 

#### Other systems
For all other systems, please follow the Python instructions below.

### For Python users: clone and run Python source
1. Clone or download the repository, navigate to the project folder. 
2. Install Python (or make sure you have already installed) version >= 3.12
3. Install a venv: python3 -m venv .venv
4. Upgrade pip: python3 -m pip install --upgrade pip
5. Install requirements: python3 -m pip install -r requirements.txt
6. Run the app: python3 src/honeychrome/main.py

## Contributions
We have many ideas for Honeychrome and welcome new ones. 
We also welcome anyone wishing to contribute to and improve the software!

We will shortly release documentation for programmers wishing to build on Honeychrome in
new open source cytometry projects. In the meantime, please contact us if you require assistance.

Honeychrome builds on several great open source Python packages:
- [FlowKit](https://github.com/whitews/flowkit) - for definition of gates, gating hierarchies, transforms, and FCS input/output
- [PySide6](https://pypi.org/project/PySide6/) - the GUI system, Qt for Python
- [pyqtgraph](https://www.pyqtgraph.org/) - extremely fast plotting and manipulation of plots in Qt
- Several others for processing of data, including numpy, scikit, sklearn
- Seaborn and Matplotlib for publication-quality graphics

## Roadmap
By January 2027, we hope to get to a stable release labeled v1.0.0, including the following:
- all bugs fixed
- documentation for users
- documentation for developers