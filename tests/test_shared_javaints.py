"""Java's signed narrowing of protobuf's unsigned integer types.

Java has no unsigned integer type, so protobuf-java 2.6.1 maps `uint32` to
`int` and `uint64` to `long`. A value past the signed maximum comes back
negative from the getter, and that negative is what a rule sees: not only what
it prints, but what it compares, sorts and matches on.

**The earlier reading of this was wrong and is retracted here.** A first pass
described the narrowing as a rendering detail and asserted that a rule's
comparisons should keep the true unsigned value. That is not what upstream does.
`StopTimeUpdateValidator` fills `List<Integer> rtStopSequenceList` from
`getStopSequence()` (`:111`, `:114`) and asks
`Ordering.natural().isStrictlyOrdered` of it (`:184`), so a feed sending 1 then
4294967295 is `[1, -1]` there and gets an E002 that an unsigned comparison never
fires. `tests/test_unsigned_prefixes.py` pins that against a jar run.

The decoder keeps the wire value, which is what the wire says and what modern
mode wants. The narrowing belongs at the rule layer, which is where `int32` and
`int64` are applied.

Split from `test_shared_javafmt.py`, which the 300-line hook stopped at 342.
The seam is real: everything here is about integer width and sign, and nothing
here touches the floating-point printing that file exists for.

Every expectation below was run through JDK 17.0.19 rather than reasoned.
"""

from __future__ import annotations

import pytest

from gtfs_rt_validator.proto.decode import decode
from gtfs_rt_validator.proto.schema_2015 import SCHEMA
from gtfs_rt_validator.rules._shared.javafmt import int32, int32_str, int64, int64_str
from unsignedfeeds import FEEDS, U32

#: Measured: `System.out.println("" + (int) v)` for each.
U32_ORACLE = [
    (0, "0"),
    (1, "1"),
    (2147483647, "2147483647"),
    (2147483648, "-2147483648"),
    (4294967294, "-2"),
    (4294967295, "-1"),
]

#: Measured: `Long.parseUnsignedLong(...)` printed as a long.
U64_ORACLE = [
    (0, "0"),
    (1, "1"),
    (9223372036854775807, "9223372036854775807"),
    (9223372036854775808, "-9223372036854775808"),
    (18446744073709551615, "-1"),
]


@pytest.mark.parametrize(("value", "expected"), U32_ORACLE)
def test_int32_str_matches_javas_signed_int(value: int, expected: str) -> None:
    assert int32_str(value) == expected


@pytest.mark.parametrize(("value", "expected"), U64_ORACLE)
def test_int64_str_matches_javas_signed_long(value: int, expected: str) -> None:
    assert int64_str(value) == expected


@pytest.mark.parametrize(("value", "expected"), U32_ORACLE)
def test_int32_is_the_number_behind_that_string(value: int, expected: str) -> None:
    """The narrowing and its rendering cannot disagree: one is `str` of the other."""
    assert int32(value) == int(expected)
    assert str(int32(value)) == int32_str(value)


@pytest.mark.parametrize(("value", "expected"), U64_ORACLE)
def test_int64_is_the_number_behind_that_string(value: int, expected: str) -> None:
    assert int64(value) == int(expected)
    assert str(int64(value)) == int64_str(value)


@pytest.mark.parametrize("value", [v for v, _ in U32_ORACLE])
def test_int32_is_idempotent(value: int) -> None:
    """A caller does not have to track which side of the boundary a value is on."""
    assert int32(int32(value)) == int32(value)


@pytest.mark.parametrize("value", [v for v, _ in U64_ORACLE])
def test_int64_is_idempotent(value: int) -> None:
    assert int64(int64(value)) == int64(value)


def test_int64_wraps_the_way_long_arithmetic_does() -> None:
    """`_shared/walk_timestamp` narrows a difference, not only its operands.

    Java's `long interval = headerTimestamp - previousTimestamp` wraps at 64
    bits. Python's subtraction widens without bound, so the difference of the
    two extremes is 2^64-1 here and -1 there.
    """
    assert int64(int64(2**63 - 1) - int64(2**63)) == -1


def test_the_decoder_keeps_the_wire_value_and_the_rule_layer_narrows_it() -> None:
    """Where the boundary is, asserted at the boundary.

    `Msg.get` answers what the wire says, because that is correct for the wire
    and correct for modern mode. Compat's rules read the same field through
    `int32`, which is what protobuf-java's getter would have handed them, and
    they then compare and print that.
    """
    message = decode(FEEDS["01-seq-e051.pb"], SCHEMA)
    update = message.get("entity")[0].get("trip_update").get("stop_time_update")[0]
    assert update.get("stop_sequence") == U32
    assert int32(update.get("stop_sequence")) == -1


def test_the_signed_ordering_upstream_uses_is_not_the_unsigned_one() -> None:
    """The retraction, as an assertion rather than a paragraph.

    `Ordering.natural().isStrictlyOrdered([1, -1])` is false and a comparison on
    the wire values would call the same pair sorted. `02-seq-e037.pb` carries
    exactly this pair and the jar's E002 for it is pinned in `unsignedpins`.
    """
    sequences = [1, U32]
    assert sequences[0] < sequences[1]
    narrowed = [int32(value) for value in sequences]
    assert narrowed == [1, -1]
    assert not narrowed[0] < narrowed[1]
