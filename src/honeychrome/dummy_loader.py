import sys

class Mock(object):
    def __init__(self, *args, **kwargs):
        pass

    def __call__(self, *args, **kwargs):
        return Mock()

    def __getattr__(self, name):
        # Prevent infinite recursion on private/internal attributes
        if name.startswith('__'):
            raise AttributeError(name)
        return Mock()

# Define the "blocked" modules
for mod in ['bokeh', 'bokeh.plotting', 'bokeh.models', 'bokeh.layouts', 'narwhals']:
    sys.modules[mod] = Mock()