"""The committed jar corpus, loaded once for the modules that assert about it.

`tests/fixtures/jar/` holds eight crafted `.pb` inputs, the five
`.results.json` files upstream's jar wrote for them, and the manifest tying the
two together. `tools/gen_golden.py` produces all of it from the SHA in
`upstream/pins.json`; nothing here is hand-edited.

A module of plain values rather than fixtures, matching `gtfsfixtures.py`: three
test modules read the same bytes and none of them needs setup or teardown.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CORPUS = ROOT / "tests" / "fixtures" / "jar"
MANIFEST = json.loads((CORPUS / "manifest.json").read_text(encoding="utf-8"))
INPUTS = MANIFEST["inputs"]
GOLDENS = [record for record in INPUTS if record["results"]]
GOLDEN_NAMES = [record["name"] for record in GOLDENS]

# The rule strings the shipped package reads at run time, generated from the
# same commit the jar was built from. The goldens agreeing with these is the
# evidence that both are at the pin.
RULES = json.loads(
    (ROOT / "src" / "gtfs_rt_validator" / "data" / "rules.json").read_text(encoding="utf-8")
)["rules"]

# The header timestamp every crafted feed carries, from tools/goldenfeeds.py.
# Restated rather than imported because one module asserting about the corpus
# should not need `tools/` on sys.path to do arithmetic with it.
FEED_TS = 1_500_000_000


def record(name: str) -> dict:
    return next(entry for entry in INPUTS if entry["name"] == name)


def input_bytes(name: str) -> bytes:
    return (CORPUS / name).read_bytes()


def golden_bytes(name: str) -> bytes:
    return (CORPUS / record(name)["results"]).read_bytes()


def parsed(name: str) -> list:
    return json.loads(golden_bytes(name))


def digest(blob: bytes) -> str:
    return hashlib.sha256(blob).hexdigest()


def fingerprint(directory: Path) -> dict[str, str]:
    """Name to content digest for every file in a directory."""
    return {path.name: digest(path.read_bytes()) for path in sorted(directory.iterdir())}


def import_tool(name: str):
    """Import a module from `tools/`, which is not a package and not installed.

    The same two lines `tests/test_schema_2015.py` and
    `tests/test_manifest_drift.py` already use, in one place.
    """
    sys.path.insert(0, str(ROOT / "tools"))
    try:
        return __import__(name)
    finally:
        sys.path.pop(0)
