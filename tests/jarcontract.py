"""The jar's output contract as checks that run over every byte of a file.

Split out of `tests/test_jar_output_contract.py` so the same checks can be run
twice: once over the committed goldens, where they must pass, and once over a
deliberately broken copy in `tests/test_jar_contract_teeth.py`, where they must
fail. A check nothing has ever rejected is a check with no teeth, and this suite
had four of them.

Every constant here was measured from the committed goldens rather than
transcribed from upstream's README, whose sample cannot be trusted: it shows
`"messageId" : 0` for a boxed `Integer` nothing ever sets, which Jackson writes
as `null`.
"""

from __future__ import annotations

import re

# Upstream's output beans, field for field. `ErrorListHelperModel` holds a
# `MessageLogModel` and a `List<OccurrenceModel>`. There is no field holding
# prefix and occurrenceSuffix joined together, which is the README's other trap.
ENTRY_KEYS = ["errorMessage", "occurrenceList"]
MESSAGE_KEYS = ["messageId", "gtfsRtFeedIterationModel", "validationRule", "errorDetails"]
RULE_KEYS = ["errorId", "severity", "title", "errorDescription", "occurrenceSuffix"]
OCCURRENCE_KEYS = ["occurrenceId", "messageLogModel", "prefix"]

# Every key Jackson writes, at the one indent it is ever written at. Two spaces
# per level, so an entry key sits at 2, a message or occurrence key at 4 and a
# rule key at 6. Asserting the depth per key rather than "the indent is even"
# is what makes a line moved one level in or out a failure.
KEY_INDENT = {
    **dict.fromkeys(ENTRY_KEYS, 2),
    **dict.fromkeys(MESSAGE_KEYS, 4),
    **dict.fromkeys(RULE_KEYS, 6),
    **dict.fromkeys(OCCURRENCE_KEYS, 4),
}

# The only lines in a results file that carry no key. Jackson's
# `DefaultPrettyPrinter` opens an object on the line of the key that holds it
# and closes it on a line of its own, so these seven shapes cover every
# structural line in every golden.
PUNCTUATION_LINES = frozenset(
    {
        "[ {",
        "}, {",
        "} ]",
        "  },",
        "  }, {",
        "  } ]",
        "    },",
    }
)

# A key line, anchored at the start so a colon inside a value can never look
# like one. Jackson's default separator is ` : `, not `: `, and the lookahead
# rejects a second space after it. One wrong space is a byte-level diff on every
# line of every result file compat writes.
KEY_LINE = re.compile(r'^(?P<indent> *)"(?P<key>[A-Za-z]+)" : (?=[^ ])')


def check_every_line(blob: bytes) -> None:
    """Every line of a results file is a known key at its known indent, or punctuation.

    Exhaustive on purpose. The check this replaces asserted that three correctly
    formatted lines existed somewhere in the file, which mixed indentation and a
    wrong separator on any other line both passed.
    """
    for number, line in enumerate(blob.decode("utf-8").split("\n"), start=1):
        where = f"line {number}: {line!r}"
        assert "\t" not in line, where
        assert line == line.rstrip(" \r"), where
        match = KEY_LINE.match(line)
        if match is None:
            assert line in PUNCTUATION_LINES, where
            continue
        key = match.group("key")
        assert key in KEY_INDENT, where
        assert len(match.group("indent")) == KEY_INDENT[key], where


def check_defaults(blob: bytes, entries: list) -> None:
    """`messageId` is null and `occurrenceId` is zero in every entry, not in one.

    `messageId` is a boxed `Integer` nothing sets; `occurrenceId` an unboxed
    `int`. The byte counts are the second half of the check: they catch a value
    that parses to the right thing while being spelled differently.
    """
    occurrences = 0
    for entry in entries:
        assert entry["errorMessage"]["messageId"] is None, entry["errorMessage"]
        for occurrence in entry["occurrenceList"]:
            occurrences += 1
            assert occurrence["occurrenceId"] == 0, occurrence
            assert not isinstance(occurrence["occurrenceId"], bool), occurrence
    assert blob.count(b'"messageId" : null') == len(entries)
    assert blob.count(b'"occurrenceId" : 0') == occurrences
    # The README's sample, restated so the trap stays named next to the check.
    assert b'"messageId" : 0' not in blob


def check_keys(entries: list) -> None:
    """The bean fields in upstream's order, and never an empty `occurrenceList`.

    An entry with no occurrences would make the per-occurrence loop vacuous, so
    the emptiness is asserted rather than tolerated: every entry in every golden
    carries at least one occurrence, because an entry exists only because an
    occurrence was appended to it.
    """
    for entry in entries:
        assert list(entry) == ENTRY_KEYS
        assert list(entry["errorMessage"]) == MESSAGE_KEYS
        assert list(entry["errorMessage"]["validationRule"]) == RULE_KEYS
        assert entry["occurrenceList"], entry["errorMessage"]["validationRule"]["errorId"]
        for occurrence in entry["occurrenceList"]:
            assert list(occurrence) == OCCURRENCE_KEYS


def prefixes_for(entries: list, rule_id: str) -> list[str]:
    """Every occurrence prefix a rule reported, in file order."""
    return [
        occurrence["prefix"]
        for entry in entries
        if entry["errorMessage"]["validationRule"]["errorId"] == rule_id
        for occurrence in entry["occurrenceList"]
    ]


def check_w008_clock(entries: list, elapsed: int, reported: bool) -> None:
    """W008's prefix is the file's mtime minus the header timestamp, spelled out.

    This is the check that catches a corpus regenerated without stamping mtimes:
    the input bytes would be identical and only this string would move. It is
    also the check that used to return green on an empty list, which made
    deleting W008 from a golden invisible, so `reported` comes from the manifest
    and an empty list is a failure wherever the manifest says the rule fired.
    """
    prefixes = prefixes_for(entries, "W008")
    if not reported:
        assert prefixes == [], prefixes
        return
    assert prefixes, "the manifest says this golden reports W008, and no occurrence carries it"
    assert prefixes == [f"header.timestamp is {elapsed // 60} min {elapsed % 60} sec"]
