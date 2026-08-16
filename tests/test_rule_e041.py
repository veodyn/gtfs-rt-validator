"""E041, against upstream's own `testE41`, plus the post-2015 enum case.

Every assertion marked "upstream" is transcribed from the real
`StopTimeUpdateValidatorTest.java` (`testE41`, `:969-1029`), not from the
reference's summary of it. Upstream asserts counts and nothing else, so every
assertion about occurrence text is ours.

The post-2015 case at the bottom is ours as well, and it is the one thing about
this rule that a single-schema port cannot reproduce. It is deliberately *not*
described as losing the CANCELED exemption: CANCELED is in the 2015 enum and its
exemption works under both schemas. What a post-2015 value changes is that
`hasScheduleRelationship()` answers false, so the trip is neither exempt nor
recognisable.
"""

from __future__ import annotations

from gtfs_rt_validator.proto.decode import decode
from gtfs_rt_validator.proto.encode import encode
from gtfs_rt_validator.proto.schema_2015 import SCHEMA
from gtfs_rt_validator.rules.upstream.e041 import check
from rulefixtures import entity
from stufixtures import found, rule_context, run, stu, trip_update

#: `TripDescriptor.ScheduleRelationship`. CANCELED is in both schemas;
#: DUPLICATED was added after 2015 and is in neither the 2015 enum nor the 2015
#: schema module, so the decoder leaves it in the unknown-field bytes.
CANCELED = 3
DUPLICATED = 6


# --- upstream's testE41 -----------------------------------------------------


def test_a_trip_with_no_stop_time_updates_reports_once(tmp_path):
    """Upstream, testE41: `expected.put(E041, 1)`."""
    assert len(run(check, tmp_path, trip_update(trip_id="1"))) == 1


def test_one_stop_time_update_is_enough(tmp_path):
    """Upstream, testE41: a single stop_time_update carrying stop_id `1.1` and a
    departure delay, `expected.clear()`."""
    updates = trip_update(stu(stop_id="1.1", departure={"delay": 60}), trip_id="1")

    assert run(check, tmp_path, updates) == []


def test_an_empty_trip_that_is_canceled_reports_nothing(tmp_path):
    """Upstream, testE41: no stop_time_updates but `schedule_relationship`
    CANCELED, `expected.clear()`."""
    updates = trip_update(trip_id="1", schedule_relationship=CANCELED)

    assert run(check, tmp_path, updates) == []


# --- the occurrence text and the other relationships, which upstream skips ---


def test_the_prefix_names_the_trip(tmp_path):
    """Ours, read off `:313`."""
    assert found(run(check, tmp_path, trip_update(trip_id="1"))) == ["trip_id 1"]


def test_an_empty_trip_with_no_trip_id_falls_back_to_the_entity_id(tmp_path):
    """Ours. `getTripId` has no trip_id to use, so it names the FeedEntity."""
    assert found(run(check, tmp_path, trip_update())) == ["entity ID TEST_ENTITY"]


def test_only_canceled_is_exempt(tmp_path):
    """Ours. `:309` compares against CANCELED alone, so ADDED and UNSCHEDULED,
    both recognised in the 2015 enum, are reported like any other."""
    added = trip_update(trip_id="1", schedule_relationship=1)
    unscheduled = trip_update(trip_id="1", schedule_relationship=2)

    assert found(run(check, tmp_path, added, unscheduled)) == ["trip_id 1", "trip_id 1"]


def test_each_empty_trip_update_reports_once(tmp_path):
    """Ours. The check is per TripUpdate and runs before the loop, so two empty
    entities give two occurrences."""
    assert len(run(check, tmp_path, trip_update(trip_id="1"), trip_update(trip_id="2"))) == 2


def test_a_post_2015_schedule_relationship_reports(tmp_path):
    """Ours, and the case the two-schema decoder exists for.

    DUPLICATED is 6, which the 2015 enum does not have, so `proto/decode.py`
    leaves it in the unknown-field bytes exactly as protobuf 2.6.1 does and
    `hasScheduleRelationship()` is false. The exemption at `:307` therefore does
    not apply and the empty trip is reported. Encoded through the real encoder
    with the number on the wire, because that is the only way to put a value the
    2015 schema does not know into a 2015 message."""
    wire = encode(
        {
            "header": {"gtfs_realtime_version": "1.0"},
            "entity": [
                entity(
                    trip_update={
                        "trip": {"trip_id": "1", "schedule_relationship": DUPLICATED},
                        "stop_time_update": [],
                    }
                )
            ],
        },
        SCHEMA,
    )
    message = decode(wire, SCHEMA)
    trip = message.get("entity")[0].get("trip_update").get("trip")

    assert not trip.has("schedule_relationship")
    assert found(list(check(message, rule_context(tmp_path)))) == ["trip_id 1"]
