"""Jackson's `DefaultPrettyPrinter`, asserted against the layout it produced.

Two kinds of assertion, and both are needed. The unit cases below pin the
printer's rules one at a time, including the two containers no results file
happens to carry. The rest read the committed goldens, which are real jar output,
and assert the layout directly off their bytes: that is the contract this module
reproduces, stated where it came from rather than paraphrased.

`tests/test_compat_writer.py` is where the two meet, byte-comparing this
project's whole output against those same files.
"""

from __future__ import annotations

import pytest

from gtfs_rt_validator.report import jackson
from jarcorpus import GOLDEN_NAMES, golden_bytes


def test_an_object_is_a_newline_and_two_spaces_per_level():
    assert jackson.dumps({"a": 1, "b": {"c": None}}) == (
        '{\n  "a" : 1,\n  "b" : {\n    "c" : null\n  }\n}'
    )


def test_an_array_is_inline_and_does_not_raise_the_indent():
    """`FixedSpaceIndenter.isInline()` is true, so `writeStartArray` never
    increments the nesting level and an object inside an array is indented as
    though the array were not there."""
    assert jackson.dumps({"a": [{"b": 1}, {"b": 2}]}) == (
        '{\n  "a" : [ {\n    "b" : 1\n  }, {\n    "b" : 2\n  } ]\n}'
    )


def test_an_empty_container_is_its_brackets_around_one_space():
    """`writeEndObject` writes a single space in place of the indentation when
    nothing was written, and the array indenter writes one either way."""
    assert jackson.dumps([]) == "[ ]"
    assert jackson.dumps({}) == "{ }"
    assert jackson.dumps({"a": [], "b": {}}) == '{\n  "a" : [ ],\n  "b" : { }\n}'


def test_the_key_separator_carries_a_space_on_both_sides():
    """A writer that used `json.dumps`'s default `": "` would differ on every
    line of every file."""
    assert jackson.KEY_SEPARATOR == " : "
    assert jackson.dumps({"a": 1}).endswith('"a" : 1\n}')


def test_non_ascii_is_raw_and_the_escape_set_is_jacksons():
    """Jackson escapes the quote, the backslash and the control characters, and
    writes everything else as itself."""
    assert jackson.dumps("héllo ✓") == '"héllo ✓"'
    assert jackson.dumps('a"b\\c') == '"a\\"b\\\\c"'
    assert jackson.dumps("a\nb\tc\x00d") == '"a\\nb\\tc\\u0000d"'


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("\x01", '"\\u0001"'),
        ("\x1f", '"\\u001F"'),
        ("\x0b", '"\\u000B"'),
        ("\x1b", '"\\u001B"'),
    ],
)
def test_a_unicode_escape_uses_jacksons_upper_case_hex(value, expected):
    """**Measured against the pinned jar's own Jackson on JDK 17.**

    Jackson writes the four hex digits in upper case; `json.dumps` writes them in
    lower. U+0001 agrees only because its escape has no letter in it, which is
    exactly why the older assertion above, pinning U+0000, could not see the
    difference. One character per hex digit class is pinned here so it cannot be
    masked again.

    Reachable rather than theoretical: a `trip_id` is bytes on the wire, so a
    producer can put U+001F in one and W002 renders it into an occurrence prefix.
    """
    assert jackson.dumps(value) == expected


@pytest.mark.parametrize("value", ["/", "\u2028", "\u2029", "\x7f", "\u00ad"])
def test_the_characters_jackson_leaves_raw_stay_raw(value):
    """The other half of the same measurement, and the reason not to escape more.

    Jackson emits all five of these unescaped. A writer that reached for
    `ensure_ascii=True`, or that escaped U+2028 and U+2029 the way some JavaScript
    encoders do, would differ from the jar on every one.
    """
    assert jackson.dumps(value) == f'"{value}"'


@pytest.mark.parametrize("value", [1.5, True, b"bytes", ("a",)])
def test_a_value_the_printer_was_not_measured_for_is_refused(value):
    """A results file carries strings, ints and nulls. Rendering a float the way
    Java's `Double.toString` would is a separate measured problem, and guessing
    at one inside the printer is how a byte comparison goes quietly wrong."""
    with pytest.raises(TypeError):
        jackson.dumps(value)


@pytest.mark.parametrize("name", GOLDEN_NAMES)
def test_the_goldens_carry_the_layout_this_printer_reproduces(name):
    """The contract, read off the jar's own output rather than restated."""
    blob = golden_bytes(name)
    assert blob.startswith(b"[ {\n")
    assert blob.endswith(b" ]")
    assert not blob.endswith(b"\n")
    assert b'"errorMessage" : {' in blob
    assert b'"errorMessage": {' not in blob
    assert b"\\u" not in blob


def test_the_goldens_separate_entries_on_one_line():
    """`}, {` rather than a newline between them, which needs a file carrying
    more than one entry."""
    assert b"\n}, {\n" in golden_bytes("01-no-timestamps.pb")


def test_a_golden_ends_inside_two_containers_at_the_right_indents():
    """The last occurrence closes its object at one level, its array inline, then
    the entry object at nothing and the outer array inline again."""
    assert golden_bytes("01-no-timestamps.pb").endswith(b'"prefix" : "trip_id 1.1"\n  } ]\n} ]')


def test_the_goldens_write_non_ascii_as_raw_utf8():
    """Two invalid bytes became two U+FFFD in the decoder, and the four
    occurrences naming that trip_id carry eight of them into the file."""
    assert golden_bytes("03-invalid-utf8.pb").count(b"\xef\xbf\xbd") == 8
