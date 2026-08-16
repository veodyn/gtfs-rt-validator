"""The encoder exists to build fixtures, so its contract is round-tripping.

Upstream ships no real .pb files: its four archive fixtures are 0 bytes and
`bullrunner-vehicle-positions` is a single 415-byte message. Every
`tests/test_rule_*.py` therefore constructs its own feed.
"""

from gtfs_rt_validator.proto.decode import decode
from gtfs_rt_validator.proto.encode import encode
from gtfs_rt_validator.proto.schema_current import SCHEMA


def test_a_minimal_feed_round_trips():
    data = encode({"header": {"gtfs_realtime_version": "2.0"}}, SCHEMA)
    assert decode(data, SCHEMA).get("header").get("gtfs_realtime_version") == "2.0"


def test_repeated_messages_round_trip_in_order():
    data = encode(
        {
            "header": {"gtfs_realtime_version": "2.0"},
            "entity": [
                {"id": "a", "trip_update": {"trip": {"trip_id": "T1"}}},
                {"id": "b", "trip_update": {"trip": {"trip_id": "T2"}}},
            ],
        },
        SCHEMA,
    )
    entities = decode(data, SCHEMA).get("entity")
    assert [e.get("id") for e in entities] == ["a", "b"]
    assert entities[1].get("trip_update").get("trip").get("trip_id") == "T2"


def test_scalars_of_every_width_round_trip():
    data = encode(
        {
            "header": {"gtfs_realtime_version": "2.0", "timestamp": 1_700_000_000},
            "entity": [
                {
                    "id": "v",
                    "vehicle": {
                        "position": {"latitude": 40.5, "longitude": -74.25, "bearing": 90.0},
                        "occupancy_percentage": 42,
                    },
                }
            ],
        },
        SCHEMA,
    )
    vehicle = decode(data, SCHEMA).get("entity")[0].get("vehicle")
    assert vehicle.get("position").get("latitude") == 40.5
    assert vehicle.get("position").get("longitude") == -74.25
    assert vehicle.get("occupancy_percentage") == 42


def test_a_negative_int32_survives_sign_extension():
    """`CarriageDetails.occupancy_percentage` is int32 with `[default = -1]`, so
    a real feed can carry a negative here. The encoder sign-extends it to 64
    bits, ten varint bytes, and the decoder has to read it back as -1 rather
    than as 18446744073709551615."""
    data = encode(
        {
            "header": {"gtfs_realtime_version": "2.0"},
            "entity": [
                {
                    "id": "v",
                    "vehicle": {
                        "multi_carriage_details": [
                            {"id": "c1", "occupancy_percentage": -1},
                            {"id": "c2", "occupancy_percentage": -7},
                        ]
                    },
                }
            ],
        },
        SCHEMA,
    )
    carriages = decode(data, SCHEMA).get("entity")[0].get("vehicle").get("multi_carriage_details")
    assert [c.get("occupancy_percentage") for c in carriages] == [-1, -7]


def test_an_omitted_required_field_fails_on_the_way_back_in():
    """The encoder does not police required fields; the decoder does, and that
    is the behaviour a fixture wants to exercise."""
    import pytest

    from gtfs_rt_validator.proto.errors import DecodeError

    data = encode({"header": {}}, SCHEMA)
    with pytest.raises(DecodeError):
        decode(data, SCHEMA)
