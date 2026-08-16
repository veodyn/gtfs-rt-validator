"""The same bytes, decoded under both schemas, disagreeing on purpose.

These cases are why the decoder takes a schema instead of masking after the
fact. Both are reachable on feeds published today.

Every field number the fixtures below hard-code was re-read from
`upstream/gtfs-realtime.proto` at the pin and cross-checked against both
generated schemas before these assertions were written:
`FeedMessage.header`=1, `.entity`=2, `FeedHeader.gtfs_realtime_version`=1,
`FeedEntity.id`=1, `.trip_update`=3, `.alert`=5, `TripUpdate.trip`=1,
`TripDescriptor.schedule_relationship`=4, `Alert.image`=15,
`TranslatedImage.localized_image`=1. Verify against the vendored proto again
before changing any assertion here.
"""

import pytest

from gtfs_rt_validator.proto.decode import decode
from gtfs_rt_validator.proto.errors import DecodeError
from gtfs_rt_validator.proto.schema_2015 import SCHEMA as V2015
from gtfs_rt_validator.proto.schema_current import SCHEMA as CURRENT


def field(number: int, wire_type: int) -> bytes:
    return bytes([(number << 3) | wire_type])


def length_prefixed(number: int, payload: bytes) -> bytes:
    return field(number, 2) + bytes([len(payload)]) + payload


def a_feed(entity: bytes) -> bytes:
    """A minimal valid FeedMessage: header with version "2.0", one entity."""
    header = length_prefixed(1, field(1, 2) + b"\x032.0")
    return header + length_prefixed(2, entity)


def test_a_duplicated_trip_reads_as_absent_in_2015_and_present_today():
    """`schedule_relationship = DUPLICATED` (6) does not exist in the 2015 enum,
    so the jar files it as an unknown field and `hasScheduleRelationship()`
    returns false. Rules E003, E016 and E020 then treat the trip as SCHEDULED."""
    trip = field(4, 0) + b"\x06"  # TripDescriptor.schedule_relationship = 6
    entity = field(1, 2) + b"\x011" + length_prefixed(3, length_prefixed(1, trip))
    data = a_feed(entity)

    old_trip = decode(data, V2015).get("entity")[0].get("trip_update").get("trip")
    assert not old_trip.has("schedule_relationship")
    # SCHEDULED, protobuf-java's effective default for a bare optional enum.
    assert old_trip.get("schedule_relationship") == 0

    new_trip = decode(data, CURRENT).get("entity")[0].get("trip_update").get("trip")
    assert new_trip.has("schedule_relationship")
    assert new_trip.get("schedule_relationship") == 6


def test_an_earlier_valid_enum_survives_a_later_unknown_one_in_2015():
    """ADDED then DUPLICATED. The 2015 view keeps ADDED, because the second
    occurrence never reaches the field. A mask applied after a current-schema
    decode could only make the field absent, which is a third answer neither
    implementation gives."""
    trip = field(4, 0) + b"\x01" + field(4, 0) + b"\x06"
    entity = field(1, 2) + b"\x011" + length_prefixed(3, length_prefixed(1, trip))
    data = a_feed(entity)

    old_trip = decode(data, V2015).get("entity")[0].get("trip_update").get("trip")
    assert old_trip.has("schedule_relationship")
    assert old_trip.get("schedule_relationship") == 1  # ADDED

    new_trip = decode(data, CURRENT).get("entity")[0].get("trip_update").get("trip")
    assert new_trip.get("schedule_relationship") == 6  # DUPLICATED, last wins


def test_an_incomplete_localized_image_is_skipped_in_2015_and_fatal_today():
    """`LocalizedImage.url` and `.media_type` are required, and the message did
    not exist in 2015. To the jar the whole `Alert.image` field is an unknown
    length-delimited blob; to a current-schema decode it is a required-field
    violation that sinks the file."""
    empty_image = length_prefixed(1, b"")  # TranslatedImage.localized_image, empty
    alert = length_prefixed(15, empty_image)  # Alert.image, field 15 at the pin
    entity = field(1, 2) + b"\x011" + length_prefixed(5, alert)
    data = a_feed(entity)

    old = decode(data, V2015)
    assert old.get("entity")[0].get("alert").unknown  # retained, not rejected

    with pytest.raises(DecodeError, match="LocalizedImage"):
        decode(data, CURRENT)
