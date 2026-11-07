#!/usr/bin/env python3
"""Validate media-catalog JSON collections and playlists.

Part of https://github.com/rmnavz/media-catalog (CC0 1.0).
"""

from __future__ import annotations

import sys
from pathlib import Path

TOOLS_DIR = Path(__file__).resolve().parent
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

from catalog_validate.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
