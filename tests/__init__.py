import sys
from pathlib import Path

# The plugin modules are not a package; tests import them flat, so put
# src/ on the path the same way the script launch does.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
