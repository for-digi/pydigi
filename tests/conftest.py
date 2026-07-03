"""Make the test-helper modules (framelib, test_reading) importable by name.

The tests deliberately have no package ``__init__``; this puts their directory
on ``sys.path`` so ``from framelib import ...`` works under any pytest layout.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
