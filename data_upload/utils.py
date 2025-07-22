import pathlib
import sys

IS_BUNDLED = getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS")

if IS_BUNDLED:
    BUNDLE_DIR = pathlib.Path(sys._MEIPASS)
else:
    BUNDLE_DIR = pathlib.Path(__file__).parent
