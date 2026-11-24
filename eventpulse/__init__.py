"""
EventPulse - Root Package Shim
Allows seamless imports via `eventpulse.services...` regardless of environment (Docker, CI, Local).
"""

import os
import sys

_PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from . import services  # noqa: F401
