"""The version this project reports for itself.

Kept in a module of its own so `pyproject.toml` and any report field cannot
drift; `tests/test_version.py` asserts they agree. The pinned upstream commit is
a separate fact and lives in `upstream/pins.json`.
"""

from __future__ import annotations

VERSION = "0.3.0"
