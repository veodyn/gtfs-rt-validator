"""Decoder semantics, each one a claim about what protobuf-java 2.6.1 does.

Byte literals rather than our own encoder on purpose: a test that round-trips
through `encode` passes when both halves share a mistake.
`tools/diff_decoder_against_bindings.py` is the comparison against the real
bindings, which is a different question.
"""

import pytest

from gtfs_rt_validator.proto.decode import decode
from gtfs_rt_validator.proto.descriptor import FieldDesc, MessageDesc, Schema
from gtfs_rt_validator.proto.errors import DecodeError


def schema() -> Schema:
    return Schema(
        messages={
            "Root": MessageDesc(
                "Root",
                (
                    FieldDesc(1, "name", "string", "optional"),
                    FieldDesc(2, "count", "int32", "optional"),
                    FieldDesc(3, "kind", "enum", "optional", "Root.Kind", default=0),
                    FieldDesc(4, "child", "message", "optional", "Child"),
                    FieldDesc(5, "items", "message", "repeated", "Child"),
                    FieldDesc(6, "tag", "string", "required"),
                ),
            ),
            "Child": MessageDesc(
                "Child",
                (
                    FieldDesc(1, "a", "int32", "optional"),
                    FieldDesc(2, "b", "int32", "optional"),
                ),
            ),
        },
        enums={"Root.Kind": {"ZERO": 0, "ONE": 1}},
    )


def tagged(number: int, wire_type: int) -> bytes:
    """A tag is a varint, not a byte. Field 99 encodes to 792, which needs two."""
    tag = (number << 3) | wire_type
    out = bytearray()
    while True:
        byte = tag & 0x7F
        tag >>= 7
        if tag:
            out.append(byte | 0x80)
        else:
            out.append(byte)
            return bytes(out)


REQUIRED_TAG = tagged(6, 2) + b"\x01x"  # tag="x", so messages below are valid


def test_a_present_scalar_reads_back():
    msg = decode(tagged(1, 2) + b"\x03abc" + REQUIRED_TAG, schema(), "Root")
    assert msg.has("name")
    assert msg.get("name") == "abc"


def test_an_absent_field_is_absent_and_returns_none():
    msg = decode(REQUIRED_TAG, schema(), "Root")
    assert not msg.has("name")
    assert msg.get("name") is None


def test_an_absent_field_with_a_declared_default_returns_that_default():
    """proto2's `getX()` returns the default while `hasX()` stays false, and
    rules read both. `TripDescriptor.schedule_relationship [default = SCHEDULED]`
    is the case this exists for."""
    msg = decode(REQUIRED_TAG, schema(), "Root")
    assert not msg.has("kind")
    assert msg.get("kind") == 0


def test_a_repeated_scalar_occurrence_of_a_singular_field_takes_the_last():
    msg = decode(tagged(2, 0) + b"\x01" + tagged(2, 0) + b"\x02" + REQUIRED_TAG, schema(), "Root")
    assert msg.get("count") == 2


def test_a_repeated_occurrence_of_a_singular_message_merges_rather_than_replaces():
    """The one place protobuf does not take the last value. Two partial `child`
    submessages combine, so a feed splitting a message across occurrences reads
    the same here as in Java."""
    first = tagged(4, 2) + b"\x02" + tagged(1, 0) + b"\x07"
    second = tagged(4, 2) + b"\x02" + tagged(2, 0) + b"\x09"
    msg = decode(first + second + REQUIRED_TAG, schema(), "Root")
    assert msg.get("child").get("a") == 7
    assert msg.get("child").get("b") == 9


def test_a_repeated_field_collects_every_occurrence_in_order():
    one = tagged(5, 2) + b"\x02" + tagged(1, 0) + b"\x01"
    two = tagged(5, 2) + b"\x02" + tagged(1, 0) + b"\x02"
    msg = decode(one + two + REQUIRED_TAG, schema(), "Root")
    assert [item.get("a") for item in msg.get("items")] == [1, 2]


def test_a_repeated_field_with_no_occurrences_is_an_empty_list():
    assert decode(REQUIRED_TAG, schema(), "Root").get("items") == []


def test_an_unknown_field_number_is_retained_rather_than_dropped():
    msg = decode(tagged(99, 0) + b"\x05" + REQUIRED_TAG, schema(), "Root")
    assert msg.unknown == [(99, 0, b"\x05")]


def test_a_known_number_with_the_wrong_wire_type_is_treated_as_unknown():
    """protobuf-java's generated parser switches on the whole tag, not on the
    field number, so a mismatch falls through to `parseUnknownField` instead of
    raising.

    Read off the generated `FeedEntity` parser in the 0.0.4 jar, then measured
    against a jar built from the pinned SHA under JDK 17, which is what settles
    it. Two feeds, both writing `FeedEntity.id` (field 1, a string, so wire type
    2) as a varint instead:

        id as a varint and nothing else   ->  NO RESULTS FILE
        id as a varint plus a valid id    ->  results BYTE-IDENTICAL to control

    The second is the load-bearing one: the mis-typed field was absorbed with no
    effect on output, so it did not raise. The first only looks like a rejection
    and is not one, since `FeedEntity.id` is required and the mis-typed field
    never reached it, so `isInitialized` failed instead. Our decoder answers
    both the same way, raising `required field FeedEntity.id is not set` for the
    first and retaining `(1, 0, b"\\x05")` as unknown for the second."""
    msg = decode(tagged(1, 0) + b"\x05" + REQUIRED_TAG, schema(), "Root")
    assert not msg.has("name")
    assert msg.unknown == [(1, 0, b"\x05")]


def test_an_unrecognised_enum_value_becomes_an_unknown_field():
    """proto2 enums are closed. The field stays absent and the raw varint is
    retained, which is why upstream reads `schedule_relationship = DUPLICATED`
    as no value at all."""
    msg = decode(tagged(3, 0) + b"\x63" + REQUIRED_TAG, schema(), "Root")
    assert not msg.has("kind")
    assert msg.unknown == [(3, 0, b"\x63")]


def test_a_recognised_enum_value_survives_a_later_unrecognised_one():
    """The counterexample that decides the whole compat design: ONE then an
    unknown value leaves the field set to ONE, where decoding under a schema
    that knows the second value would take the second."""
    body = tagged(3, 0) + b"\x01" + tagged(3, 0) + b"\x63" + REQUIRED_TAG
    msg = decode(body, schema(), "Root")
    assert msg.has("kind")
    assert msg.get("kind") == 1


def test_a_missing_required_field_raises():
    with pytest.raises(DecodeError, match=r"Root\.tag"):
        decode(tagged(1, 2) + b"\x03abc", schema(), "Root")


def test_a_missing_required_field_in_a_nested_message_raises():
    """`isInitialized` is recursive, so an incomplete submessage sinks the whole
    parse and upstream writes no results file for the feed."""
    nested = tagged(4, 2) + b"\x00"
    with pytest.raises(DecodeError):
        decode(
            nested + REQUIRED_TAG,
            Schema(
                messages={
                    "Root": MessageDesc(
                        "Root",
                        (
                            FieldDesc(4, "child", "message", "optional", "Child"),
                            FieldDesc(6, "tag", "string", "required"),
                        ),
                    ),
                    "Child": MessageDesc("Child", (FieldDesc(1, "a", "int32", "required"),)),
                },
                enums={},
            ),
            "Root",
        )


def test_trailing_garbage_after_a_valid_message_raises():
    with pytest.raises(DecodeError):
        decode(REQUIRED_TAG + b"\x00", schema(), "Root")


def test_invalid_utf8_in_a_string_is_replaced_rather_than_fatal():
    """MEASURED against a jar built from the pinned SHA. Settled.

    This carried an UNVERIFIED marker for a while, because the choice was first
    reasoned from protobuf-java's source rather than from running it: proto2
    generated code stores a string field as a `ByteString` and converts on
    `getX()` with `toStringUtf8()`, which substitutes U+FFFD rather than
    throwing, while the throwing path (`readStringRequireUtf8`) is proto3's.

    Now run. A feed whose `TripDescriptor.trip_id` is `\\xff\\xfeT1` was fed to a
    jar built from `7041fa3` under JDK 17, against `bullrunner-gtfs.zip`:

        b-invalid-utf8.pb  ->  RESULTS WRITTEN (4041 bytes)
        prefix in that file:   "trip_id \\ufffd\\ufffdT1"

    So the file validates, the two invalid bytes become two U+FFFD, and the
    replacement characters reach occurrence text and therefore output bytes.
    Our decoder returns `'\\ufffd\\ufffdT1'` for the same input, which is the
    same string.

    It mattered: replace-versus-reject was the difference between an occurrence
    carrying a replacement character and no results file at all.
    """
    body = tagged(1, 2) + b"\x02\xff\xfe" + REQUIRED_TAG
    assert decode(body, schema(), "Root").get("name") == "��"


# ---------------------------------------------------------------------------
# Added after a code audit. Measured by running the same bytes through the
# pinned jars (gtfs-realtime-bindings 0.0.4 plus protobuf-java 2.6.1) under
# JDK 17, on real GTFS-Realtime messages rather than the stand-in schema above.
# ---------------------------------------------------------------------------


def test_an_absent_submessage_reads_as_its_default_instance_not_as_none():
    """protobuf-java hands back a default instance, and rules chain through it.

    Measured on a feed carrying one entity with an `id` and no `trip_update`:

        hasTripUpdate()                 -> false
        getTripUpdate() == null         -> false
        getTripUpdate() is the default  -> true
        getTripUpdate().getTrip().getTripId()  -> ""
        getTripUpdate().getTrip().hasTripId()  -> false

    This is the spec's own rule, "a getter on an absent field returns the proto
    default while `hasX()` stays false", applied to a message field. Returning
    `None` would turn every unguarded chain in the 57 ported rules into an
    `AttributeError` where the Java it was ported from reads a default.
    """
    from gtfs_rt_validator.proto.schema_2015 import SCHEMA as V2015

    data = bytes([0x0A, 0x05, 0x0A, 0x03, 0x32, 0x2E, 0x30, 0x12, 0x03, 0x0A, 0x01, 0x31])
    entity = decode(data, V2015).get("entity")[0]

    assert not entity.has("trip_update")
    assert entity.get("trip_update") is not None
    assert entity.get("trip_update").get("trip").get("trip_id") == ""
    assert not entity.get("trip_update").get("trip").has("trip_id")


def test_each_absent_submessage_read_is_a_fresh_object():
    """The default is built per call rather than shared, so a caller cannot
    mutate a cached instance and poison every later read of that field."""
    from gtfs_rt_validator.proto.schema_2015 import SCHEMA as V2015

    data = bytes([0x0A, 0x05, 0x0A, 0x03, 0x32, 0x2E, 0x30, 0x12, 0x03, 0x0A, 0x01, 0x31])
    entity = decode(data, V2015).get("entity")[0]
    assert entity.get("trip_update") is not entity.get("trip_update")


def test_an_absent_scalar_still_reads_the_effective_default_from_the_schema():
    """The companion to the case above, on the field the whole compat design
    turns on. `TripDescriptor.schedule_relationship` declares no default in
    either source, and protobuf-java answers SCHEDULED for it regardless."""
    from gtfs_rt_validator.proto.schema_2015 import SCHEMA as V2015

    data = bytes([0x0A, 0x05, 0x0A, 0x03, 0x32, 0x2E, 0x30, 0x12, 0x03, 0x0A, 0x01, 0x31])
    trip = decode(data, V2015).get("entity")[0].get("trip_update").get("trip")
    assert not trip.has("schedule_relationship")
    assert trip.get("schedule_relationship") == 0
