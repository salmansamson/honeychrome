# Honeychrome
Open Source GUI App for Cytometry Acquisition and Analysis

Now in beta.

For too long, our field has lacked a general purpose, free and open-source cytometry software package. We intend to plug that gap and provide a software package that is useful for everybody: power cytometrists, biologists, students, innovators. The app should be lightweight but provide all the functions one expects: 

- acquire data (starting with Cytkit, perhaps with drivers for other instruments in the future)
- import FCS files from any instrument
- provide both conventional compensation and spectral unmixing
- give simple statistical comparisons between samples, publication quality graphs and exports
- be highly intuitive to use
- support the major operating systems (Windows, macOS, Linux)

It should also be fully open source, and provide a platform that innovators can exploit, for developing both instrumentation and data analysis and visualisation techniques. (We intend to release a programmers guide too, so that people can build on the app easily.)

See the blog https://cytkit.com/blog/

## Installation
1. Clone or download the repository, navigate to the project folder. 
2. Install Python (or make sure you already have it installed), version >= 3.12
4. python3 -m pip install --upgrade pip
4. Recommended: install a venv
3. Run on the command line: pip install -e
4. Run honeychrome
