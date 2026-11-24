"""
EventPulse Services Package Shim
Points package search path to root services directory.
"""

import os

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_SERVICES_DIR = os.path.join(_PROJECT_ROOT, "services")

__path__ = [_SERVICES_DIR]
