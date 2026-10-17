import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
for p in (ROOT,):
    if p not in sys.path:
        sys.path.insert(0, p)
