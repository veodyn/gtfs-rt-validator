"""E013, against upstream's own `FrequencyTypeZeroValidatorTest` and one measured enum.

Assertions marked "upstream" are transcribed from the real
`FrequencyTypeZeroValidatorTest.java` in the checkout at `jar-build/upstream/`
(`testE013`, lines 105-202). Upstream asserts counts only, so the occurrence
text is ours, measured by running the pinned jar over a crafted feed against
upstream's own `bullrunner-gtfs.zip`.

Upstream's first stage, "empty schedule_relationship is fine", is commented out
at `:137-139` with a FIXME saying the builder could not be made to clear the
field. The behaviour it wanted is what the code does, and it is asserted here.

**The post-2015 enum case is measured, not reasoned.** A TripDescriptor with
`schedule_relationship = DUPLICATED` (6) was encoded with the current schema and
handed to the jar: it produced no E013 at all, because 6 is not in the 2015 enum,
so it lands in the unknown-field set, `hasScheduleRelationship()` is false, and
E013 reads the field as empty, which is allowed.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path

from gtfs_rt_validator.proto.decode import Msg, decode
from gtfs_rt_validator.proto.encode import encode
from gtfs_rt_validator.proto.schema_2015 import SCHEMA
from gtfs_rt_validator.proto.schema_current import SCHEMA as CURRENT
from gtfs_rt_validator.rules.upstream.e013 import check
from gtfsfixtures import minimal_tables
from rulefixtures import context, entity, message, prefixes, trip_rows

BULL_RUNNER_TRIP = "1"

START_DATE = "4-24-2016"
START_TIME = "08:00:00AM"

#: `TripDescriptor.ScheduleRelationship` at the 2015 pin. Written out rather
#: than imported so that a test asserting on the *name* does not read its
#: expectation from the same table the rule renders with.
SCHEDULED, ADDED, UNSCHEDULED, CANCELED = 0, 1, 2, 3

#: `DUPLICATED`, added to the enum long after 2015 and absent from the schema a
#: compat run decodes with.
DUPLICATED = 6


def tables() -> dict[str, list[dict[str, object]]]:
    """`minimal_tables` with bullrunner's exact_times = 0 trip in it."""
    built = minimal_tables()
    built["trips.txt"] += trip_rows({BULL_RUNNER_TRIP: "R1"})
    built["frequencies.txt"] = [
        {
            "trip_id": BULL_RUNNER_TRIP,
            "start_time": "07:00:00",
            "end_time": "24:00:00",
            "headway_secs": "600",
            "exact_times": "0",
        }
    ]
    return built


def trip(**fields: object) -> dict[str, object]:
    """Upstream's descriptor: a valid trip_id, start_date and start_time, so
    that only E013 can fire whatever this test does to the enum."""
    return {
        "trip_id": BULL_RUNNER_TRIP,
        "start_date": START_DATE,
        "start_time": START_TIME,
        **fields,
    }


def half(trip_descriptor: Mapping[str, object], vehicle_id: str | None = "vehicle_A") -> dict:
    built: dict[str, object] = {"trip": dict(trip_descriptor)}
    if vehicle_id is not None:
        built["vehicle"] = {"id": vehicle_id}
    return built


def both_halves(trip_descriptor: Mapping[str, object], vehicle_id: str | None = "vehicle_A"):
    return entity(half(trip_descriptor, vehicle_id), half(trip_descriptor, vehicle_id))


def run(tmp_path: Path, *entities: Mapping[str, object]) -> Sequence:
    return list(check(message(*entities), context(tmp_path, tables())))


def under_both_schemas(*entities: Mapping[str, object]) -> Msg:
    """Encoded with the current schema, decoded with the 2015 one.

    The only way to put a post-2015 enum value on the wire: the 2015 encoder
    refuses a number its enum does not declare, which is the point of it.
    """
    value = {"header": {"gtfs_realtime_version": "1.0"}, "entity": list(entities)}
    return decode(encode(value, CURRENT), SCHEMA)


# --- upstream's own case, stage by stage ------------------------------------


def test_unscheduled_is_allowed(tmp_path):
    """Upstream, testE013: `expected.clear()` for UNSCHEDULED."""
    found = run(tmp_path, both_halves(trip(schedule_relationship=UNSCHEDULED)))

    assert found == []


def test_added_reports_twice(tmp_path):
    """Upstream, testE013: `expected.put(E013, 2)` for ADDED."""
    found = run(tmp_path, both_halves(trip(schedule_relationship=ADDED)))

    assert len(found) == 2


def test_canceled_reports_twice(tmp_path):
    """Upstream, testE013: `expected.put(E013, 2)` for CANCELED."""
    found = run(tmp_path, both_halves(trip(schedule_relationship=CANCELED)))

    assert len(found) == 2


def test_scheduled_reports_twice(tmp_path):
    """Upstream, testE013: `expected.put(E013, 2)` for SCHEDULED, which is the
    enum's zero value and still not allowed on an exact_times = 0 trip."""
    found = run(tmp_path, both_halves(trip(schedule_relationship=SCHEDULED)))

    assert len(found) == 2


def test_an_absent_schedule_relationship_is_allowed(tmp_path):
    """Upstream's commented-out first stage at `:137-139`, which its builder
    could not reach. The condition is `!(!hasScheduleRelationship() || ...)`, so
    an absent field is the allowed "empty" case."""
    found = run(tmp_path, both_halves(trip()))

    assert found == []


# --- the occurrence text, which upstream's test never looks at --------------


def test_the_two_prefixes_are_the_ones_the_jar_writes(tmp_path):
    """Ours, measured. The enum is concatenated by `Enum.toString()`, which is
    the protobuf constant name."""
    found = run(tmp_path, both_halves(trip(schedule_relationship=ADDED)))

    assert prefixes(found) == [
        "trip_id 1 schedule_relationship ADDED",
        "vehicle_id vehicle_A trip_id 1 schedule_relationship ADDED",
    ]
    assert {occurrence.rule_id for occurrence in found} == {"E013"}


def test_a_vehicle_position_with_no_vehicle_id_leaves_a_double_space(tmp_path):
    """Ours, measured, with CANCELED: `getVehicle().getId()` is unguarded at
    `:101` exactly as it is in E006's branch."""
    found = run(tmp_path, entity(vehicle=half(trip(schedule_relationship=CANCELED), None)))

    assert prefixes(found) == ["vehicle_id  trip_id 1 schedule_relationship CANCELED"]


def test_every_enum_value_prints_its_own_constant_name(tmp_path):
    """Ours. Three of the four names the 2015 enum declares, one occurrence
    each; UNSCHEDULED is the fourth and is the value that never fires."""
    found = [
        prefixes(run(tmp_path, entity(half(trip(schedule_relationship=value)))))[0]
        for value in (SCHEDULED, ADDED, CANCELED)
    ]

    assert found == [
        "trip_id 1 schedule_relationship SCHEDULED",
        "trip_id 1 schedule_relationship ADDED",
        "trip_id 1 schedule_relationship CANCELED",
    ]


# --- the enum gap -----------------------------------------------------------


def test_a_post_2015_schedule_relationship_does_not_fire(tmp_path):
    """Ours, measured against the jar: DUPLICATED produced no E013.

    Under the 2015 schema the value is an unknown field, so
    `hasScheduleRelationship()` is false and E013 treats it as empty, which is
    allowed. A port that decoded with the current schema and masked afterwards
    could not reproduce this, which is what `tests/test_two_views.py` is about.
    """
    feed = under_both_schemas(both_halves(trip(schedule_relationship=DUPLICATED)))

    assert list(check(feed, context(tmp_path, tables()))) == []


def test_a_value_both_schemas_declare_still_fires_across_the_pair(tmp_path):
    """Ours, and the control for the case above: the same encode-with-current,
    decode-with-2015 path carries ADDED through untouched, so the silence above
    is the enum gap and not the fixture."""
    feed = under_both_schemas(both_halves(trip(schedule_relationship=ADDED)))

    assert prefixes(check(feed, context(tmp_path, tables()))) == [
        "trip_id 1 schedule_relationship ADDED",
        "vehicle_id vehicle_A trip_id 1 schedule_relationship ADDED",
    ]
