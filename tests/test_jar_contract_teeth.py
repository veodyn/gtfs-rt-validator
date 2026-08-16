"""The output-contract checks, run over goldens broken on purpose.

`tests/test_jar_output_contract.py` runs `tests/jarcontract.py` over the
committed goldens and they pass. That says nothing about whether they would
notice if the goldens were wrong, and four of these checks used to be vacuous in
exactly that way: a count of four accepted any four prefixes, an empty
`prefixes` list made the clock check return green, and the formatting and
default-value checks looked for three good lines somewhere in a file rather than
at every line of it.

So each check is run here against a copy mutated to break the one thing it
claims to cover, and is required to reject it. Every mutation is written into
`tmp_path` and read back from there; `tests/fixtures/jar/` is generated from a
real jar run by `tools/gen_golden.py` and is never touched.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from jarcontract import check_defaults, check_every_line, check_keys, check_w008_clock, prefixes_for
from jarcorpus import CORPUS, FEED_TS, fingerprint, golden_bytes, parsed, record
from test_jar_output_contract import W003_PREFIXES

COMBINED = "04-combined-feed.pb"
NO_TIMESTAMPS = "01-no-timestamps.pb"


def broken(tmp_path: Path, blob: bytes) -> bytes:
    """A mutated golden, written into tmp_path and read back from disk."""
    path = tmp_path / "mutated.results.json"
    path.write_bytes(blob)
    return path.read_bytes()


def reserialised(tmp_path: Path, entries: list) -> list:
    """The same, for a mutation easier to express on the parsed form.

    The formatting is not the golden's any more, which is fine: the checks that
    read this take entries, and the ones that read bytes get `broken`.
    """
    return json.loads(broken(tmp_path, json.dumps(entries, indent=2).encode("utf-8")))


def test_the_committed_corpus_is_never_what_gets_mutated(tmp_path):
    """The guard on this module's method, asserted rather than promised."""
    before = fingerprint(CORPUS)
    broken(tmp_path, golden_bytes(COMBINED).replace(b"  ", b"   "))
    assert fingerprint(CORPUS) == before


# ── Every line, not three of them ────────────────────────────────────────────
# The check this replaces asserted three substrings were present and that `": "`
# was absent. Each mutation below leaves all four of those claims true, so the
# old check passed every one of them.


@pytest.mark.parametrize(
    ("original", "replacement"),
    [
        # One key indented by three spaces instead of four.
        (b'\n    "prefix" : ', b'\n     "prefix" : '),
        # One key moved a whole level out, to the indent an entry key sits at.
        (b'\n      "severity" : ', b'\n    "severity" : '),
        # Two spaces after the colon rather than one.
        (b'\n    "messageLogModel" : null', b'\n    "messageLogModel" :  null'),
        # A tab where Jackson wrote spaces.
        (b'\n  "occurrenceList" : ', b'\n\t"occurrenceList" : '),
        # A key upstream's beans do not have.
        (b'\n    "errorDetails" : ', b'\n    "errorNotes" : '),
        # Trailing whitespace, which no line of a Jackson file carries.
        (b'"occurrenceId" : 0,\n', b'"occurrenceId" : 0, \n'),
    ],
)
def test_a_line_that_is_not_jacksons_shape_is_rejected(tmp_path, original, replacement):
    blob = golden_bytes(COMBINED)
    assert original in blob, original
    mutated = broken(tmp_path, blob.replace(original, replacement, 1))
    with pytest.raises(AssertionError):
        check_every_line(mutated)


def test_the_unmutated_golden_still_passes_the_line_check(tmp_path):
    """The other half: an exhaustive check that rejects everything is no better."""
    check_every_line(broken(tmp_path, golden_bytes(COMBINED)))


# ── Every entry and every occurrence, not one of each ─────────────────────────
# Both mutations leave one null `messageId` and one zero `occurrenceId` in the
# file, which is all the old check asked for.


@pytest.mark.parametrize(
    ("original", "replacement"),
    [
        (b'"messageId" : null', b'"messageId" : 7'),
        (b'"occurrenceId" : 0', b'"occurrenceId" : 5'),
    ],
)
def test_one_wrong_default_among_many_right_ones_is_rejected(tmp_path, original, replacement):
    blob = golden_bytes(COMBINED)
    assert blob.count(original) > 1, original
    mutated = broken(tmp_path, blob.replace(original, replacement, 1))
    with pytest.raises(AssertionError):
        check_defaults(mutated, json.loads(mutated))


def test_a_default_wrong_only_in_the_bytes_is_rejected(tmp_path):
    """`-0` parses equal to zero and is not the byte Jackson wrote, so it is a diff."""
    mutated = broken(
        tmp_path, golden_bytes(COMBINED).replace(b'"occurrenceId" : 0', b'"occurrenceId" : -0', 1)
    )
    assert json.loads(mutated)[0]["occurrenceList"][0]["occurrenceId"] == 0
    with pytest.raises(AssertionError):
        check_defaults(mutated, json.loads(mutated))


# ── An entry always carries an occurrence ────────────────────────────────────


def test_an_entry_with_no_occurrences_is_rejected(tmp_path):
    """The loop over `occurrenceList` verified nothing when the list was empty."""
    entries = parsed(COMBINED)
    entries[0]["occurrenceList"] = []
    with pytest.raises(AssertionError):
        check_keys(reserialised(tmp_path, entries))


def test_a_reordered_bean_field_is_rejected(tmp_path):
    entries = parsed(COMBINED)
    rule = entries[0]["errorMessage"]["validationRule"]
    entries[0]["errorMessage"]["validationRule"] = {
        key: rule[key] for key in ["severity", "errorId", "title", "errorDescription"]
    } | {"occurrenceSuffix": rule["occurrenceSuffix"]}
    with pytest.raises(AssertionError):
        check_keys(reserialised(tmp_path, entries))


# ── W003's four prefixes, in order ───────────────────────────────────────────
# Both mutations keep the count at four, which is all the old assertion checked.


def w003(entries: list) -> list:
    return next(e for e in entries if e["errorMessage"]["validationRule"]["errorId"] == "W003")


def test_the_same_four_prefixes_reordered_are_rejected(tmp_path):
    """The order is Java `HashSet` iteration order, and reproducing it is the point."""
    entries = parsed(COMBINED)
    w003(entries)["occurrenceList"].reverse()
    assert prefixes_for(reserialised(tmp_path, entries), "W003") != W003_PREFIXES


def test_one_prefix_repeated_four_times_is_rejected(tmp_path):
    entries = parsed(COMBINED)
    occurrences = w003(entries)["occurrenceList"]
    w003(entries)["occurrenceList"] = [occurrences[0]] * 4
    mutated = reserialised(tmp_path, entries)
    assert len(prefixes_for(mutated, "W003")) == 4
    assert prefixes_for(mutated, "W003") != W003_PREFIXES


def test_a_wrong_prefix_string_is_rejected(tmp_path):
    entries = parsed(COMBINED)
    w003(entries)["occurrenceList"][2]["prefix"] = "vehicle_id vOnlyVP is in TripUpdates feed"
    assert prefixes_for(reserialised(tmp_path, entries), "W003") != W003_PREFIXES


# ── W008's clock, on a golden that reports it ────────────────────────────────


def elapsed(name: str) -> int:
    return record(name)["mtime"] - FEED_TS


def test_a_golden_that_lost_its_w008_entry_is_rejected(tmp_path):
    """Deleting the rule outright used to leave the clock check green."""
    entries = [
        e for e in parsed(COMBINED) if e["errorMessage"]["validationRule"]["errorId"] != "W008"
    ]
    with pytest.raises(AssertionError, match="reports W008"):
        check_w008_clock(reserialised(tmp_path, entries), elapsed(COMBINED), reported=True)


def test_a_clock_string_from_an_unstamped_mtime_is_rejected(tmp_path):
    """The failure a corpus regenerated without stamping mtimes would produce."""
    entries = parsed(COMBINED)
    w008 = next(e for e in entries if e["errorMessage"]["validationRule"]["errorId"] == "W008")
    w008["occurrenceList"][0]["prefix"] = "header.timestamp is 0 min 1 sec"
    with pytest.raises(AssertionError):
        check_w008_clock(reserialised(tmp_path, entries), elapsed(COMBINED), reported=True)


def test_a_w008_occurrence_in_a_golden_that_should_have_none_is_rejected(tmp_path):
    """The other direction: 01-no-timestamps.pb has no header timestamp to age."""
    borrowed = next(
        e for e in parsed(COMBINED) if e["errorMessage"]["validationRule"]["errorId"] == "W008"
    )
    entries = [*parsed(NO_TIMESTAMPS), borrowed]
    with pytest.raises(AssertionError):
        check_w008_clock(reserialised(tmp_path, entries), elapsed(NO_TIMESTAMPS), reported=False)
