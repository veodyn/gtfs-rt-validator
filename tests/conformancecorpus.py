"""The committed tier 1 corpus, loaded once for the modules that assert about it.

`tests/fixtures/conformance/` holds four groups of crafted `.pb` inputs, the
`.results.json` files upstream's jar wrote for them, and the manifest tying the
three together. `tools/gen_golden.py --conformance` produces all of it from the
SHA in `upstream/pins.json`; nothing here is hand-edited.

A module of plain values rather than fixtures, matching `tests/jarcorpus.py`,
which does the same job for the eight output-contract feeds. The two corpora are
separate because they answer different questions: that one pins the writer's
bytes, this one pins that every rule was seen firing.
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CORPUS = ROOT / "tests" / "fixtures" / "conformance"
GTFS = ROOT / "tests" / "fixtures" / "gtfs"
MANIFEST = json.loads((CORPUS / "manifest.json").read_text(encoding="utf-8"))
GROUPS = MANIFEST["groups"]
RESULTS_SUFFIX = ".results.json"


def group(name: str) -> dict:
    return next(section for section in GROUPS if section["name"] == name)


def group_names() -> list[str]:
    return [section["name"] for section in GROUPS]


def directory(name: str) -> Path:
    return CORPUS / name


def archive(name: str) -> Path:
    """The static feed one group validates against."""
    return GTFS / group(name)["gtfs"]


def inputs(name: str) -> dict[str, bytes]:
    """A group's inputs in manifest order, which is the order mtimes are stamped in."""
    return {
        record["name"]: (directory(name) / record["name"]).read_bytes()
        for record in group(name)["inputs"]
    }


def goldens(name: str) -> dict[str, bytes | None]:
    """What the jar wrote for a group, `None` for an input it skipped.

    Keyed by input name and carrying the `None`s, so a comparison sees the
    absence of a file as a value rather than as a missing key.
    """
    found: dict[str, bytes | None] = {}
    for record in group(name)["inputs"]:
        results = record["results"]
        found[record["name"]] = (
            None if results is None else (directory(name) / results).read_bytes()
        )
    return found


def records() -> list[tuple[str, dict]]:
    """`(group name, input record)` for every input in the corpus."""
    return [(section["name"], record) for section in GROUPS for record in section["inputs"]]


def rule_ids() -> set[str]:
    """Every errorId the corpus's goldens carry."""
    return {rule for _, record in records() for rule in record.get("rules") or ()}


def occurrence_counts(name: str) -> dict[str, int]:
    """`{rule_id: how many occurrences}` across one group's goldens."""
    tally: dict[str, int] = {}
    for blob in goldens(name).values():
        if blob is None:
            continue
        for entry in json.loads(blob):
            rule_id = entry["errorMessage"]["validationRule"]["errorId"]
            tally[rule_id] = tally.get(rule_id, 0) + len(entry["occurrenceList"])
    return tally


def total_bytes() -> int:
    """Everything committed under the corpus directory, in bytes."""
    return sum(path.stat().st_size for path in CORPUS.rglob("*") if path.is_file())
