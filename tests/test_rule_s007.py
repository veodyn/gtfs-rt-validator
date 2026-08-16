"""S007: an `exact_times=0` trip whose stop_time_updates are SCHEDULED.

**Not E013, and the difference is the whole reason this rule exists.** E013
reads the *trip's* schedule_relationship and accepts "UNSCHEDULED or empty" for
an `exact_times=0` trip, which was right in 2015 when
`StopTimeUpdate.ScheduleRelationship` had three members. The pinned proto adds
`UNSCHEDULED = 3` to that enum and says the frequency-based trip's
stop_time_updates should use it. E013 never looks at them, so nothing about
E013 changes and the fix for a rule too lenient for the current source is a new
id.

The value read is the resolved one. An absent `schedule_relationship` is
SCHEDULED to every consumer by proto2's default, so a producer that omits it has
still given the update a SCHEDULED value, which is what the clause is about.

**One occurrence per trip**, which is the sentence's own subject and the
argument the rule module carries. The three tests at the bottom are the shape
that argument had to answer: the recorded Clovis Transit trip carries 95
stop_time_updates and declares nothing, and reporting it 95 times said one thing
95 times.
"""

from __future__ import annotations

from gtfs_rt_validator.proto.schema_current import SCHEMA
from gtfs_rt_validator.rules.spec.s007 import check
from specfixtures import entity, feed_context, message, minimal, prefixes

STOP_TIME = SCHEMA.enums["TripUpdate.StopTimeUpdate.ScheduleRelationship"]


def tables(exact_times: str = "0"):
    """`minimal_tables()` gives T1 one frequency; this sets its `exact_times`."""
    built = minimal()
    built["frequencies.txt"][0]["exact_times"] = exact_times
    return built


def update(relationship: str | None = None) -> dict[str, object]:
    built: dict[str, object] = {"stop_id": "S1"}
    if relationship is not None:
        built["schedule_relationship"] = STOP_TIME[relationship]
    return built


def trip_update(*updates: dict[str, object], trip_id: str = "T1") -> dict[str, object]:
    return {"trip": {"trip_id": trip_id}, "stop_time_update": list(updates)}


def run(tmp_path, *entities, exact_times: str = "0"):
    return check(message(*entities), feed_context(tmp_path, tables(exact_times)))


def test_an_unscheduled_update_on_a_frequency_trip_is_what_the_clause_asks_for(tmp_path):
    found = run(tmp_path, entity(trip_update=trip_update(update("UNSCHEDULED"))))

    assert prefixes(found) == []


def test_a_scheduled_update_on_a_frequency_trip_is_reported(tmp_path):
    found = run(tmp_path, entity(trip_update=trip_update(update("SCHEDULED"))))

    assert prefixes(found) == [
        "trip_id T1 has 1 of 1 stop_time_updates SCHEDULED on an exact_times=0 trip"
    ]


def test_an_absent_relationship_is_scheduled_and_is_reported(tmp_path):
    """proto2's default. A consumer reads SCHEDULED either way, so a producer
    that omitted the field has not thereby satisfied the clause."""
    found = run(tmp_path, entity(trip_update=trip_update(update())))

    assert prefixes(found) == [
        "trip_id T1 has 1 of 1 stop_time_updates SCHEDULED on an exact_times=0 trip"
    ]


def test_an_empty_exact_times_cell_reads_as_zero(tmp_path):
    """`GtfsMetadata.java:238-252` types `exact_times` as a primitive, so blank
    is 0 and the trip is frequency-based."""
    found = run(tmp_path, entity(trip_update=trip_update(update())), exact_times="")

    assert len(found) == 1


def test_an_exact_times_one_trip_is_not_in_scope(tmp_path):
    found = run(tmp_path, entity(trip_update=trip_update(update())), exact_times="1")

    assert prefixes(found) == []


def test_a_trip_absent_from_frequencies_txt_is_not_in_scope(tmp_path):
    found = run(tmp_path, entity(trip_update=trip_update(update(), trip_id="T2")))

    assert prefixes(found) == []


def test_skipped_and_no_data_updates_are_not_scheduled(tmp_path):
    """The clause names one value. SKIPPED and NO_DATA are the producer saying
    something else, not the producer saying SCHEDULED."""
    found = run(tmp_path, entity(trip_update=trip_update(update("SKIPPED"), update("NO_DATA"))))

    assert prefixes(found) == []


def test_a_trip_reports_once_however_many_of_its_updates_are_scheduled(tmp_path):
    """The sentence's subject is the trip, so one trip is one occurrence.

    Two SCHEDULED updates and one UNSCHEDULED: the trip has a SCHEDULED value,
    which is the whole of what the clause forbids it.
    """
    found = run(
        tmp_path, entity(trip_update=trip_update(update(), update("UNSCHEDULED"), update()))
    )

    assert prefixes(found) == [
        "trip_id T1 has 2 of 3 stop_time_updates SCHEDULED on an exact_times=0 trip"
    ]
    assert [occurrence.context["entityPath"] for occurrence in found] == [
        "entity[0].trip_update.trip"
    ]
    assert [occurrence.rule_id for occurrence in found] == ["S007"]


def test_the_recorded_shape_of_a_producer_that_declares_nothing(tmp_path):
    """Clovis Transit's, at the corpus pin: a frequency-based trip carrying 95
    stop_time_updates and no `schedule_relationship` at either level, so the
    proto default resolves SCHEDULED on every one of them. One descriptor is
    wrong, and it is named once."""
    found = run(tmp_path, entity(trip_update=trip_update(*[update() for _ in range(95)])))

    assert prefixes(found) == [
        "trip_id T1 has 95 of 95 stop_time_updates SCHEDULED on an exact_times=0 trip"
    ]


def test_each_trip_update_carrying_the_descriptor_reports_on_its_own(tmp_path):
    """Per descriptor, not per message: two TripUpdates are two wrong descriptors."""
    found = run(
        tmp_path,
        entity(trip_update=trip_update(update(), update())),
        entity(trip_update=trip_update(update())),
    )

    assert [occurrence.context["entityPath"] for occurrence in found] == [
        "entity[0].trip_update.trip",
        "entity[1].trip_update.trip",
    ]
