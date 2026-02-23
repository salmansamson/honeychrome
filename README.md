# <img src="src/honeychrome/view_components/assets/cytkit_web_logo.png> Honeychrome
Open Source GUI App for Cytometry Acquisition and Analysis. Now in beta.

<div>
  <img src="other/honeychrome screenshot animation.webp" alt="Animated Demo" width="800">
</div>

Our aim is to make Honeychrome so intuitive that you don't need instructions. But just in case, we have prepared this instructional video [Introduction to Honeychrome in 30 Minutes](https://youtu.be/RQ4-RQkDCm4).

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

### For non-programmers: download and run executable
A set of compressed binary packages are available in the releases section.
> **Note:** Since Honeychrome is very new, you may get warnings on Windows/Mac that the application is unrecognised. If so, please post the warning on the Github issues page, or contact Samson (go to [cytkit.com](https://cytkit.com)). You can normally click through any warnings; starting the app should function normally after that.

#### Windows
1. Download [Honeychrome for Windows x64](https://github.com/salmansamson/honeychrome/releases/download/v0.6.1-beta/Honeychrome-v0.6.1-windows-x64.exe)
2. Double click to run the installer

#### Linux
1. Download [Honeychrome for Linux x64](https://github.com/salmansamson/honeychrome/releases/download/v0.6.1-beta/honeychrome-v0.6.1-linux-x64.tar.gz)
2. Extract the honeychrome folder and put it somewhere appropriate for the single user or system
3. Change to the honeychrome folder and run ./install_linux.sh

#### MacOs
1. Download [Honeychrome for MacOS](https://github.com/salmansamson/honeychrome/releases/download/v0.6.1-beta/honeychrome-v0.6.1-macos.dmg)
2. Open the disk image and drag honeychrome.app to your Applications folder.
3. Double click the app in your Applications folder to run 

#### Other systems
For all other systems, please follow the Python instructions below.

### For programmers: clone and run Python source
Follow these steps to clone the repository and run the application from source:

1.  **Clone the repository:**
    ```bash
    git clone https://github.com/salmansamson/honeychrome.git
    cd honeychrome
    ```

2.  **Create a virtual environment:**
    *Requires Python 3.12 or higher.*
    ```bash
    python3 -m venv .venv
    ```

3.  **Activate the virtual environment:**
    * **Linux/macOS:** `source .venv/bin/activate`
    * **Windows:** `.venv\Scripts\activate`

4.  **Upgrade pip and install dependencies:**
    ```bash
    pip install --upgrade pip
    pip install -r requirements.txt
    ```

5.  **Install the package in editable mode:**
    *This ensures all internal modules are correctly mapped to your path.*
    ```bash
    pip install -e .
    ```

6.  **Run the application:**
    ```bash
    python3 -m honeychrome.main
    ```

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

Samson Rogers has been the main developer so far. Thanks to support and advice from many people 
including Oliver Burton, C. Vant, Lotte Carr, Scott Tasker, Philip Jones, Robyn Pritchard.

## Roadmap
By January 2027, we hope to get to a stable release labeled v1.0.0, including the following:
- all bugs fixed
- documentation for users
- documentation for developers
