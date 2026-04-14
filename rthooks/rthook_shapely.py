"""
PyInstaller runtime hook — add Shapely.libs to the DLL search path.

collect_dynamic_libs("shapely") places the GEOS DLLs under
_internal/Shapely.libs/ but Windows won't find them there unless we
explicitly register the directory before shapely is imported.
"""
import os
import sys

_shapely_libs = os.path.join(sys._MEIPASS, "Shapely.libs")
if os.path.isdir(_shapely_libs) and hasattr(os, "add_dll_directory"):
    os.add_dll_directory(_shapely_libs)
