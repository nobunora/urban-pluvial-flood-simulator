import os
import sys
from pathlib import Path

_debug = os.environ.get("DEBUG")
if _debug is not None and not _debug.isdigit():
    os.environ.pop("DEBUG")

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
