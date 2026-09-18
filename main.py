#!/usr/bin/env python3
"""Convenience launcher for Dust to Dominion.

The real bootstrap lives in ``dtd.main`` so it stays testable and spec-
tracked; this file only adds the ``src/`` layout to sys.path and calls it.
Run with: ``python main.py`` (from the repository root).
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from dtd.main import main  # noqa: E402

if __name__ == "__main__":
    main()
