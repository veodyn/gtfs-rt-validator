"""What the jar's `.results.json` looks like, byte for byte.

Every claim here was measured from a real run rather than transcribed from
upstream's README, whose sample cannot be trusted: it shows `"messageId" : 0`
for a boxed `Integer` nothing ever sets, which Jackson writes as `null`.

This is the shape `--compat` has to reproduce. It runs without a jar, because the
goldens are committed; `tests/test_jar_differential.py` re-derives them.

The checks themselves live in `tests/jarcontract.py`, because
`tests/test_jar_contract_teeth.py` runs the same functions over mutated copies
of these goldens and asserts they reject them. A check that has never rejected
anything is indistinguishable from one that cannot.
"""

from __future__ import annotations

import pytest

from jarcontract import (
    check_defaults,
    check_every_line,
    check_keys,
    check_w008_clock,
    prefixes_for,
)
from jarcorpus import FEED_TS, GOLDEN_NAMES, GOLDENS, RULES, golden_bytes, parsed, record

# W003's four occurrences in `04-combined-feed.pb`, read off the committed
# golden. Ordered by Java `HashSet` iteration rather than by anything in the
# feed, which is exactly why the order is asserted position by position: a count
# accepts the same four reordered, and reproducing that order is the work.
W003_PREFIXES = [
    "trip_id 1.1 is in TripUpdates but not in VehiclePositions feed",
    "vehicle_id vOnlyTU is in TripUpdates but not in VehiclePositions feed",
    "vehicle_id vOnlyVP is in VehiclePositions but not in TripUpdates feed",
    "trip_id 1.2 is in VehiclePositions but not in TripUpdates feed",
]


@pytest.fixture(params=GOLDEN_NAMES)
def golden(request) -> str:
    return request.param


def test_the_output_is_a_list_of_entries(golden):
    """Not an object with a `results` key, and never an empty file."""
    entries = parsed(golden)
    assert isinstance(entries, list)
    assert entries


def test_a_golden_opens_with_bracket_space_brace(golden):
    """Jackson's INDENT_OUTPUT puts a space between the two openers."""
    assert golden_bytes(golden).startswith(b"[ {\n")


def test_every_line_is_a_known_key_at_its_known_indent_or_punctuation(golden):
    """Two-space indent and a ` : ` separator, on every line rather than on three."""
    check_every_line(golden_bytes(golden))


def test_there_is_no_trailing_newline(golden):
    assert golden_bytes(golden).endswith(b"} ]")


def test_message_id_is_null_and_occurrence_id_is_zero_everywhere(golden):
    """Every entry and every occurrence, not one of each."""
    check_defaults(golden_bytes(golden), parsed(golden))


def test_the_keys_are_upstreams_bean_fields_in_upstreams_order(golden):
    check_keys(parsed(golden))


def test_the_prefix_and_the_suffix_are_never_joined(golden):
    """`RuleUtils.addOccurrence` joins them, into the debug log and nowhere else.

    `RuleUtils.java:40` at the pin is
    `log.debug(om.getPrefix() + " " + rule.getOccurrenceSuffix())`: one space
    always, even for W003, whose suffix is the empty string and whose join
    therefore ends in a trailing space. The JSON keeps the two halves apart, so
    no joined form appears in it.
    """
    text = golden_bytes(golden).decode("utf-8")
    for entry in parsed(golden):
        suffix = entry["errorMessage"]["validationRule"]["occurrenceSuffix"]
        for occurrence in entry["occurrenceList"]:
            assert occurrence["prefix"] + " " + suffix not in text


def test_the_one_rule_with_an_empty_suffix_still_writes_the_empty_string():
    """W003's suffix is the empty string, and its four occurrences are ordered."""
    entries = parsed("04-combined-feed.pb")
    w003 = next(e for e in entries if e["errorMessage"]["validationRule"]["errorId"] == "W003")
    assert w003["errorMessage"]["validationRule"]["occurrenceSuffix"] == ""
    assert b'"occurrenceSuffix" : ""' in golden_bytes("04-combined-feed.pb")
    assert prefixes_for(entries, "W003") == W003_PREFIXES


def test_w003_is_the_only_rule_in_the_manifest_with_an_empty_suffix():
    """The uniqueness claim, made against the artefact that carries every suffix.

    Reading W003's own suffix says nothing about the other sixty rules, and the
    manifest is where all of them are: `data/rules.json` is generated from the
    same commit the jar was built from, so a second empty suffix appearing
    upstream would land here first.
    """
    empty = {rule_id for rule_id, rule in RULES.items() if rule["occurrence_suffix"] == ""}
    assert empty == {"W003"}


def test_non_ascii_is_written_as_raw_utf8_rather_than_escaped():
    """A trip_id of `\\xff\\xfe` decodes to two U+FFFD, and Jackson emits them raw."""
    blob = golden_bytes("03-invalid-utf8.pb")
    assert b"\\u" not in blob
    assert b"trip_id \xef\xbf\xbd\xef\xbf\xbd" in blob


def test_the_stamped_mtime_is_the_clock_the_age_rules_measured_against(golden):
    """W008's prefix is the file's mtime minus the header timestamp, spelled out.

    The manifest decides whether the rule fired, so a golden that lost its W008
    entry fails here instead of passing on an empty list.
    """
    entry = record(golden)
    check_w008_clock(parsed(golden), entry["mtime"] - FEED_TS, "W008" in entry["rules"])


def test_every_rule_string_matches_the_committed_manifest_verbatim(golden):
    """The five strings compat emits are the manifest's, not paraphrases of them.

    This ties the goldens to what the shipped package reads at run time:
    `data/rules.json` is generated from the same commit the jar was built from.
    """
    for entry in parsed(golden):
        rule = entry["errorMessage"]["validationRule"]
        committed = RULES[rule["errorId"]]
        assert rule["severity"] == committed["severity"]
        assert rule["title"] == committed["title"]
        assert rule["errorDescription"] == committed["error_description"]
        assert rule["occurrenceSuffix"] == committed["occurrence_suffix"]


def test_the_rules_the_goldens_report_are_all_batch_reachable(golden):
    """A golden reporting an unreachable rule would mean the manifest's split is wrong."""
    ids = [entry["errorMessage"]["validationRule"]["errorId"] for entry in parsed(golden)]
    assert ids == record(golden)["rules"]
    for rule_id in ids:
        assert RULES[rule_id]["batch_reachable"], rule_id


def test_the_corpus_exercises_more_than_one_validator():
    """Ten rules across five goldens, from five of the nine registered validators.

    Not coverage, and not trying to be: the corpus exists to pin the writer's
    formatting and `BatchProcessor`'s file loop. Per-rule fixtures are a separate
    and much larger job. The set is asserted so that a rule quietly appearing or
    vanishing shows up as a corpus change rather than as a golden diff nobody
    reads.
    """
    reported = {rule_id for entry in GOLDENS for rule_id in entry["rules"]}
    assert reported == {
        "W001",
        "W002",
        "W003",
        "W008",
        "W009",
        "E002",
        "E003",
        "E017",
        "E028",
        "E041",
    }
    assert {RULES[rule_id]["emitters"][0] for rule_id in reported} == {
        "CrossFeedDescriptorValidator",
        "StopTimeUpdateValidator",
        "TimestampValidator",
        "TripDescriptorValidator",
        "VehicleValidator",
    }
