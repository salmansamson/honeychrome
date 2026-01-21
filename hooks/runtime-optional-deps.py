# hooks/runtime-optional-deps.py
"""
Handle optional dependencies that might be imported by dependencies
but aren't actually needed at runtime.
"""
import sys
import warnings

# Suppress warnings about missing optional dependencies
warnings.filterwarnings('ignore', message='.*optional dependency.*')
warnings.filterwarnings('ignore', message='.*failed to import.*')

# Mock out heavy dependencies if they're not available
try:
    import bokeh
except ImportError:
    # Create a dummy module if bokeh is excluded but something tries to import it
    class DummyBokeh:
        pass


    sys.modules['bokeh'] = DummyBokeh()
    sys.modules['bokeh.plotting'] = DummyBokeh()
    sys.modules['bokeh.models'] = DummyBokeh()

# # Same for other heavy dependencies
# for module in ['matplotlib', 'sklearn', 'scipy.sparse', 'lxml']:
#     if module not in sys.modules:
#         # Create empty module to prevent ImportError
#         import types
#
#         sys.modules[module] = types.ModuleType(module)