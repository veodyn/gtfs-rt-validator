"""P002: the `FeedEntity.id` carrying a trip moved between two messages.

The violating feed and its conformant twin differ in one byte of one entity id,
which is the whole rule: two sequential messages of one role, one trip, and the
question of whether the entity carrying it kept its name.

**The two-role test is the one a single-role test cannot be.** "Previous" is the
previous message of the same role (`runner/context.py`), so a run carrying
TripUpdates and VehiclePositions under two entity ids that are stable within
each role has nothing to report. Under a global "previous" every trip in that
run would be reported, and a fixture with one role cannot tell the two apart.
The last test here drives the real runner over such a run with the real rule
registered.

`FeedEntity.id` is `required` in both schemas, so nothing here is about a
missing one: the field is always there to compare.
"""

from __future__ import annotations

from pathlib import Path

from gtfs_rt_validator.proto.encode import encode
from gtfs_rt_validator.proto.schema_2015 import SCHEMA as V2015
from gtfs_rt_validator.rules.practice.p002 import check
from gtfs_rt_validator.runner.run import role_cycle, run
from runnerfixtures import a_config, a_rule, registry_of
from specfixtures import context, entity, message, occurrences, prefixes


def update(trip_id: str = "T1", vehicle_id: str | None = None) -> dict[str, object]:
    built: dict[str, object] = {"trip": {"trip_id": trip_id}}
    if vehicle_id is not None:
        built["vehicle"] = {"id": vehicle_id}
    return built


def position(trip_id: str = "T1") -> dict[str, object]:
    return {"trip": {"trip_id": trip_id}}


def run_over(now, was):
    return check(now, context(previous=was))


def reported(
    trip_id: str = "T1", previous: str = "e1", current: str = "e2", payload: str = "trip_update"
) -> str:
    return (
        f"the {payload} carrying trip_id {trip_id} has entity id {current} in this message "
        f"and had {previous} in the previous message of this feed"
    )


def test_an_entity_id_that_moved_between_two_messages_is_reported():
    was = message(entity(trip_update=update(), entity_id="e1"))
    now = message(entity(trip_update=update(), entity_id="e2"))

    assert prefixes(run_over(now, was)) == [reported()]


def test_the_same_trip_under_the_same_entity_id_is_silent():
    """The conformant twin: one byte of one id apart from the fixture above."""
    was = message(entity(trip_update=update(), entity_id="e1"))
    now = message(entity(trip_update=update(), entity_id="e1"))

    assert prefixes(run_over(now, was)) == []


def test_the_first_message_of_a_role_reports_nothing():
    """A trip seen once has no earlier id to have moved from, and absence is not
    a change."""
    now = message(entity(trip_update=update(), entity_id="e1"))

    assert prefixes(run_over(now, None)) == []


def test_a_trip_the_previous_message_did_not_carry_is_silent():
    was = message(entity(trip_update=update("T9"), entity_id="e1"))
    now = message(entity(trip_update=update("T1"), entity_id="e2"))

    assert prefixes(run_over(now, was)) == []


def test_a_vehicle_position_is_checked_as_well_as_a_trip_update():
    was = message(entity(vehicle=position(), entity_id="e1"))
    now = message(entity(vehicle=position(), entity_id="e2"))

    assert prefixes(run_over(now, was)) == [reported(payload="vehicle")]


def test_the_two_payloads_of_one_trip_are_answered_separately():
    """The walk keys on the payload and the trip together, so a feed whose
    TripUpdate moved and whose VehiclePosition did not reports once."""
    was = message(
        entity(trip_update=update(), entity_id="tu-1"),
        entity(vehicle=position(), entity_id="vp-1"),
    )
    now = message(
        entity(trip_update=update(), entity_id="tu-2"),
        entity(vehicle=position(), entity_id="vp-1"),
    )

    assert prefixes(run_over(now, was)) == [reported(previous="tu-1", current="tu-2")]


def test_a_vehicle_id_that_moved_is_not_this_rules_finding():
    """P003's. The entity id is what this rule reads and it did not move."""
    was = message(entity(trip_update=update(vehicle_id="V1"), entity_id="e1"))
    now = message(entity(trip_update=update(vehicle_id="V2"), entity_id="e1"))

    assert prefixes(run_over(now, was)) == []


def test_every_moved_trip_is_reported_in_this_messages_entity_order():
    was = message(
        entity(trip_update=update("T1"), entity_id="a1"),
        entity(trip_update=update("T2"), entity_id="b1"),
    )
    now = message(
        entity(trip_update=update("T2"), entity_id="b2"),
        entity(trip_update=update("T1"), entity_id="a2"),
    )

    assert prefixes(run_over(now, was)) == [
        reported("T2", previous="b1", current="b2"),
        reported("T1", previous="a1", current="a2"),
    ]


def test_the_occurrence_locates_this_messages_entity_and_names_both_ids():
    was = message(entity(trip_update=update(), entity_id="e1"))
    now = message(
        entity(vehicle=position("T9"), entity_id="other"),
        entity(trip_update=update(), entity_id="e2"),
    )

    found = occurrences(run_over(now, was))

    assert [one.rule_id for one in found] == ["P002"]
    assert [one.context["entityPath"] for one in found] == ["entity[1].trip_update"]
    assert [one.context["tripId"] for one in found] == ["T1"]
    assert [one.context["entityId"] for one in found] == ["e2"]
    assert [one.context["previousEntityId"] for one in found] == ["e1"]


def written(path: Path, timestamp: int, *entities: dict[str, object]) -> Path:
    """One message on disk. The header timestamp moves between cycles because
    the runner drops a message byte-identical to the last one of its role."""
    header = {"gtfs_realtime_version": "2.0", "incrementality": 0, "timestamp": timestamp}
    path.write_bytes(encode({"header": header, "entity": list(entities)}, V2015))
    return path


def test_a_two_role_run_compares_each_role_against_its_own_previous(tmp_path):
    """Both roles carry `T1`, under entity ids that are stable within a role and
    different between the roles. Nothing here moved. Under a global "previous"
    each cycle would compare the VehiclePositions message against the
    TripUpdates message beside it and report both ids, every cycle."""
    config = a_config(tmp_path, registry=registry_of(a_rule("P002", check)))
    tu = entity(trip_update=update(), entity_id="tu-e")
    vp = entity(vehicle=position(), entity_id="vp-e")
    first = {
        "tu": written(tmp_path / "tu-1.pb", 1_700_000_000, tu),
        "vp": written(tmp_path / "vp-1.pb", 1_700_000_000, vp),
    }
    second = {
        "tu": written(tmp_path / "tu-2.pb", 1_700_000_030, tu),
        "vp": written(tmp_path / "vp-2.pb", 1_700_000_030, vp),
    }

    result = run(config, [role_cycle(first), role_cycle(second)])

    assert result.notices.rule_ids() == ()


def test_a_two_role_run_reports_the_role_whose_id_actually_moved(tmp_path):
    """The other direction, so the test above cannot pass on a rule that never
    fires. Only the TripUpdates role renames its entity."""
    config = a_config(tmp_path, registry=registry_of(a_rule("P002", check)))
    vp = entity(vehicle=position(), entity_id="vp-e")
    first = {
        "tu": written(
            tmp_path / "tu-1.pb", 1_700_000_000, entity(trip_update=update(), entity_id="tu-1")
        ),
        "vp": written(tmp_path / "vp-1.pb", 1_700_000_000, vp),
    }
    second = {
        "tu": written(
            tmp_path / "tu-2.pb", 1_700_000_030, entity(trip_update=update(), entity_id="tu-2")
        ),
        "vp": written(tmp_path / "vp-2.pb", 1_700_000_030, vp),
    }

    result = run(config, [role_cycle(first), role_cycle(second)])

    found = result.notices.samples_for("P002")
    assert [one.prefix for one in found] == [reported(previous="tu-1", current="tu-2")]
    assert [Path(one.context["sourceFile"]).name for one in found] == ["tu-2.pb"]
