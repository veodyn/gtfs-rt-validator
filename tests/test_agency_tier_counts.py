"""The ratchet: how often each cited rule fires on a real agency, pinned.

`tools/tier_counts.py` runs modern mode over the recorded agency corpus and
writes `spec-tier-counts.json` and
`practice-tier-counts.json`; this module is what makes those files a check
rather than a note. It re-runs the generator and fails if any number moved.

**It pins exact numbers, not a band, and the clock is why that is possible.**
A band would be the honest choice for a run whose clock came from the wall,
because then a count that moved would only sometimes mean the code moved. It
does not: `tools/agencycorpus.py` stages every recorded message under a name
carrying its own `header.timestamp`, so the run is a pure function of bytes
whose SHA-256 the committed manifest pins. Nothing reads the wall clock, nothing
reads an mtime, and there is therefore no legitimate reason for a count to
change except a change to a rule. A band would hide exactly the movement this
exists to catch: P008 firing on one more percent of a real agency's trips is a
few occurrences, and a band wide enough to absorb the clock would absorb that
too.

**The counts are of the MBTA and of Valley Transit at the manifest's pin**, and
the recount below verifies the bytes against that manifest before comparing
anything, so a re-recorded corpus fails as "these are not those bytes" rather
than as a mysterious red diff in a rule nobody touched.

**Skips loudly.** `corpus/` is gitignored, so a fresh checkout cannot run the
recount at all. `-ra` in `addopts` prints the reason, which is the convention
`test_manifest_drift.py` set for the two other checks that need bytes git does
not carry. Everything that can be asserted without the corpus is asserted above
the recount rather than skipped with it.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import pytest

from gtfs_rt_validator.rules.registry import CITED_TIERS, Registry

ROOT = Path(__file__).resolve().parent.parent
FIXTURES = ROOT / "tests" / "fixtures" / "agencies"
TIERS = tuple(sorted(CITED_TIERS))

#: Everything the recount is allowed to differ on. Both are facts about when the
#: file was written rather than about what the run found: comparing the revision
#: would fail on every commit, which is the opposite of a ratchet.
NOT_COMPARED = ("generated_at", "code_revision")


def committed(tier: str) -> dict[str, Any]:
    return json.loads((FIXTURES / f"{tier}-tier-counts.json").read_text(encoding="utf-8"))


def tier_ids(tier: str) -> tuple[str, ...]:
    return tuple(sorted(rule.rule_id for rule in Registry.modern() if rule.tier == tier))


@pytest.fixture(scope="session")
def recount() -> dict[str, dict[str, Any]]:
    """Both tier files, regenerated, or a loud skip if the bytes are not here.

    Session scoped and one call for both tiers: the generator validates each
    agency once and splits the result, so a per-tier fixture would load an 18 MB
    static feed twice to answer the same question.
    """
    sys.path.insert(0, str(ROOT / "tools"))
    try:
        from agencycorpus import CorpusMissing
        from tier_counts import generate

        try:
            produced = generate()
        except CorpusMissing as absent:
            pytest.skip(f"the recorded agency corpus is not available: {absent}")
    finally:
        sys.path.pop(0)
    # Through JSON, so the comparison is between two loads of the same shape
    # rather than between a tuple and the list it serialises to.
    return json.loads(json.dumps(produced))


@pytest.mark.parametrize("tier", TIERS)
def test_every_registered_rule_of_the_tier_has_a_row(tier: str):
    """A rule that fires nowhere states its zero rather than going missing.

    The zeros are half the reading. A rule firing zero times where the feed
    plainly carries the shape it looks for is a finding, and a file that only
    listed what fired could not express it.
    """
    expected = tier_ids(tier)
    for agency in committed(tier)["agencies"]:
        assert tuple(agency["rules"]) == expected, (
            f"{tier}-tier-counts.json lists {len(agency['rules'])} rules for "
            f"{agency['static_mdb_id']} and the registry has {len(expected)}. A new rule needs "
            f"its count recorded: .venv/bin/python tools/tier_counts.py"
        )


@pytest.mark.parametrize("tier", TIERS)
def test_the_file_says_how_it_was_made(tier: str):
    """A generated file names its generator, or the next reader hand-edits it."""
    payload = committed(tier)
    assert payload["generated_by"] == "tools/tier_counts.py"
    assert "tools/tier_counts.py" in payload["do_not_edit"]
    assert payload["tier"] == tier
    assert payload["mode"] == "modern"


@pytest.mark.parametrize("tier", TIERS)
def test_the_clock_is_derived_from_the_bytes(tier: str):
    """The one property that makes an exact ratchet legitimate.

    If this ever reads `now`, the counts stop being reproducible and this whole
    module has to become a band. Asserted rather than trusted to a docstring.
    """
    assert committed(tier)["clock"]["source"] == "file_name"


@pytest.mark.parametrize("tier", TIERS)
def test_no_count_was_capped(tier: str):
    """`distinct_entities` is computed from retained occurrences only.

    The container caps retention at 100,000 per rule per message, far above
    anything here, and `dropped` records what capping cost. A nonzero would mean
    the distinct counts are a sample and the reading below them is weaker than
    it looks, so it is a failure rather than a footnote.
    """
    for agency in committed(tier)["agencies"]:
        capped = {
            rule_id: row["dropped"] for rule_id, row in agency["rules"].items() if row["dropped"]
        }
        assert not capped, f"{agency['static_mdb_id']} dropped occurrences: {capped}"


def test_the_two_tiers_are_recorded_in_the_same_shape():
    """So the two files read side by side, which is why they were written apart.

    Same agencies, same rounds, same clock, same entity counts: only the rule
    rows may differ, because only the tier does.
    """
    spec, practice = committed("spec"), committed("practice")
    assert spec["clock"] == practice["clock"]
    assert spec["corpus_recorded_at"] == practice["corpus_recorded_at"]
    for left, right in zip(spec["agencies"], practice["agencies"], strict=True):
        assert {key: value for key, value in left.items() if key != "rules"} == {
            key: value for key, value in right.items() if key != "rules"
        }


@pytest.mark.parametrize("tier", TIERS)
def test_recounting_reproduces_the_committed_counts(tier: str, recount: dict[str, Any]):
    """The ratchet. Every occurrence, message and entity count, exactly.

    A red here is not a flake and is never fixed by regenerating: it means a
    rule changed what it says about a real feed. Read the diff first, decide
    whether the new number is the better one, and only then re-run
    `.venv/bin/python tools/tier_counts.py`.

    Compared one rule at a time rather than one file at a time, because the
    whole-file assertion prints both agencies' every row and buries the one
    number that moved in four thousand characters of the ones that did not.
    """
    expected, produced = committed(tier), recount[tier]
    for key, value in expected.items():
        if key not in {*NOT_COMPARED, "agencies"}:
            assert produced[key] == value, f"{tier}-tier-counts.json {key} moved"
    for was, now in zip(expected["agencies"], produced["agencies"], strict=True):
        agency = was["static_mdb_id"]
        assert now["static_sha256"] == was["static_sha256"], f"{agency} is a different archive"
        for key in ("rounds", "messages_validated", "files_skipped", "entities", "system_errors"):
            assert now[key] == was[key], f"{agency} {key}: was {was[key]}, now {now[key]}"
        for rule_id, row in was["rules"].items():
            assert now["rules"][rule_id] == row, (
                f"{agency} {rule_id} moved over the recorded feed.\n"
                f"committed: {row}\nnow:       {now['rules'][rule_id]}\n"
                f"A rule changed what it says about a real agency. Decide whether the new "
                f"number is the better one before re-running tools/tier_counts.py."
            )
