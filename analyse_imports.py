# analyze_imports.py
import sys
import os

# Add your project to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

# Monkey-patch to track imports
import builtins
_original_import = builtins.__import__
imported_modules = set()

def tracking_import(name, *args, **kwargs):
    imported_modules.add(name.split('.')[0])  # Get top-level package
    return _original_import(name, *args, **kwargs)

builtins.__import__ = tracking_import

# Run your main module
try:
    import honeychrome.main
    # Or run your main function if you have one
    # honeychrome.main.main()
except Exception as e:
    print(f"Error during import: {e}")

# Restore original import
builtins.__import__ = _original_import

print("\n📦 Packages actually imported by your app:")
for module in sorted(imported_modules):
    print(f"  - {module}")

print(f"\nTotal: {len(imported_modules)} packages")