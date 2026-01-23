# import sys
# import inspect
# import os
#
#
# class TraceImportFinder:
#     def find_spec(self, fullname, path, target=None):
#         # Frame 0 is find_spec, Frame 1 is the import system,
#         # Frame 2 is usually the actual file calling 'import'
#         stack = inspect.stack()
#
#         caller_frame = None
#         for frame in stack:
#             # We skip the internal importlib and this class to find the real source
#             if "importlib" not in frame.filename and frame.filename != __file__:
#                 caller_frame = frame
#                 break
#
#         if caller_frame:
#             origin = os.path.relpath(caller_frame.filename)
#             print(f"[META_PATH] '{fullname}' requested by {origin}:{caller_frame.lineno}")
#
#         # Return None so Python continues to the standard loaders
#         return None
#
#
# # Insert at the front of the path to ensure it intercepts everything
# sys.meta_path.insert(0, TraceImportFinder())
#

# import sys
# class ImportLogger:
#     def find_spec(self, fullname, path, target=None):
#         print(f"DEBUG: Loading module '{fullname}'")
#         return None  # Returning None tells Python to continue to the next finder
# # sys.meta_path.insert(0, ImportLogger())
#
# import sys
# import os
# import time
# import inspect
#
# # Get your project root to filter out external libraries
# PROJECT_ROOT = os.getcwd()
#
#
# class TimedLoader:
#     """Wraps a standard loader to measure execution time."""
#
#     def __init__(self, original_loader, module_name, caller_info):
#         self.original_loader = original_loader
#         self.module_name = module_name
#         self.caller_info = caller_info
#
#     def create_module(self, spec):
#         return self.original_loader.create_module(spec)
#
#     def exec_module(self, module):
#         start = time.perf_counter()
#         self.original_loader.exec_module(module)
#         end = time.perf_counter()
#
#         duration = (end - start) * 1000  # Convert to milliseconds
#         if duration > 100:
#             print(f"[IMPORT] {self.module_name:<25} | Time: {duration:>7.2f}ms | From: {self.caller_info}")
#
#
# class ProfileImportFinder:
#     def find_spec(self, fullname, path, target=None):
#         stack = inspect.stack()
#         caller_frame = None
#
#         # Look for the first caller that is inside your PROJECT_ROOT
#         # and not inside the importlib internal files.
#         for frame in stack:
#             f_path = frame.filename
#             if f_path.startswith(PROJECT_ROOT) and "importlib" not in f_path and f_path != __file__:
#                 caller_frame = frame
#                 break
#
#         if not caller_frame:
#             return None  # Ignore imports triggered by external libs/std lib
#
#         # Let the other finders find the actual spec
#         # We temporarily remove ourselves to avoid infinite recursion
#         meta_path_copy = sys.meta_path[:]
#         sys.meta_path.remove(self)
#         try:
#             import importlib.util
#             spec = importlib.util.find_spec(fullname, path)
#             if spec and spec.loader:
#                 origin = os.path.relpath(caller_frame.filename)
#                 caller_info = f"{origin}:{caller_frame.lineno}"
#
#                 # Wrap the loader to time it
#                 spec.loader = TimedLoader(spec.loader, fullname, caller_info)
#                 return spec
#         finally:
#             sys.meta_path[:] = meta_path_copy
#
#         return None
#
#
# # Install the profiler
# sys.meta_path.insert(0, ProfileImportFinder())


import sys
import os
import time
from importlib.abc import MetaPathFinder, Loader

# --- CONFIGURATION ---
PROJECT_ROOT = os.getcwd()
TRACER_FILE = __file__
MAX_DEPTH = 1


# ---------------------
class TimedLoader(Loader):
    def __init__(self, original_loader, fullname, frame_info, current_depth):
        self.original_loader = original_loader
        self.fullname = fullname
        self.frame_info = frame_info
        self.current_depth = current_depth

    # --- NEW: Delegate all unknown attributes to the original loader ---
    # This fixes the "Orphan Path" issue by providing access to .path, .get_filename, etc.
    def __getattr__(self, name):
        return getattr(self.original_loader, name)

    def create_module(self, spec):
        return self.original_loader.create_module(spec)

    def exec_module(self, module):
        global_state['active_depth'] += 1
        start = time.perf_counter()

        try:
            self.original_loader.exec_module(module)
        finally:
            end = time.perf_counter()
            global_state['active_depth'] -= 1

        if self.current_depth <= MAX_DEPTH:
            duration = (end - start) * 1000
            if duration > 5:
                filename, lineno = self.frame_info

                import linecache
                code_line = "<code unavailable>"
                if os.path.exists(filename):
                    code_line = linecache.getline(filename, lineno).strip()

                rel_path = os.path.relpath(filename) if os.path.exists(filename) else filename
                indent = "      " * (self.current_depth - 1)
                print(f"{indent}[D{self.current_depth}] {self.fullname:<40} | {duration:>8.2f}ms | {rel_path:<40}:{lineno:<4} | `{code_line}`")

class DepthFinder(MetaPathFinder):
    def find_spec(self, fullname, path, target=None):
        if getattr(self, '_searching', False):
            return None

        try:
            depth_count = 0
            curr_frame = sys._getframe(2)
            caller_frame = None

            while curr_frame:
                fname = curr_frame.f_code.co_filename
                # Only count frames inside your project
                if fname.startswith(PROJECT_ROOT) and "importlib" not in fname and fname != TRACER_FILE:
                    depth_count += 1
                    if not caller_frame:
                        caller_frame = curr_frame
                curr_frame = curr_frame.f_back

            if not caller_frame or depth_count > MAX_DEPTH:
                return None

            self._searching = True
            import importlib.util
            spec = importlib.util.find_spec(fullname, path)

            if spec and spec.loader and not isinstance(spec.loader, TimedLoader):
                spec.loader = TimedLoader(spec.loader, fullname, (caller_frame.f_code.co_filename, caller_frame.f_lineno), depth_count)
                return spec
        except (ValueError, KeyError):
            return None
        finally:
            self._searching = False
        return None


global_state = {'active_depth': 0}
sys.meta_path.insert(0, DepthFinder())