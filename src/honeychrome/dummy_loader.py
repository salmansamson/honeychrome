import sys

class Mock(object):
    def __init__(self, *args, **kwargs):
        pass
    def __call__(self, *args, **kwargs):
        return Mock()
    @classmethod
    def __getattr__(cls, name):
        return Mock()

# Define the "blocked" modules
for mod in ['bokeh', 'bokeh.plotting', 'bokeh.models', 'bokeh.layouts', 'scipy.stats', 'scipy.interpolate', 'scipy.fft', 'narwhals']:
    sys.modules[mod] = Mock()