"""Lane C's code on the import path, for the tests that run it in process.

``HARVESTNET_PLATFORM_SOURCE`` may name a pinned platform checkout. Unset, it is this repository's
root, which always carries ``harvestnet_platform``, so the cross-lane tests always run instead of
skipping. Import this module before importing ``harvestnet_platform``.
"""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = os.environ.get('HARVESTNET_PLATFORM_SOURCE') or str(ROOT)
if SOURCE not in sys.path:
    sys.path.insert(0, SOURCE)
