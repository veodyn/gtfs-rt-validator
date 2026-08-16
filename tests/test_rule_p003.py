"""P003: the `vehicle.id` carrying a trip moved between two messages.

The violating feed and its conformant twin differ in one vehicle id: two
sequential messages of one role, one trip, and the question of whether the
vehicle named on it kept its name.

**Absent and blank are two different feeds and this rule answers them
differently**, which is most of what is tested here. `None` is "the payload
named no vehicle, or named one with no id" and is not an id at all, so a trip
that gains or loses a `VehicleDescriptor` is silent: nothing that could have
changed did. `""` is "the feed set the id to the empty string", which is a value
a consumer keys on and which can therefore move.

**E052 is the other half of `:89` and this test states the split.** E052 reports
two VehiclePositions in one message claiming one `vehicle.id`, which is the
*unique* half; nothing upstream compares one message's ids against the next
message's, which is the *stable* half and is this rule. A feed with one entity
per message can never be E052's and is exactly this rule's.

The last two tests drive the real runner over a two-role run, because "previous"
is per role and a single-role fixture cannot tell a per-role comparison from a
global one.
"""

from __future__ import annotations

from pathlib import Path

from gtfs_rt_validator.proto.encode import encode
from gtfs_rt_validator.proto.schema_2015 import SCHEMA as V2015
from gtfs_rt_validator.rules.practice.p003 import check
from gtfs_rt_validator.runner.run import role_cycle, run
from runnerfixtures import a_config, a_rule, registry_of
from specfixtures import context, entity, message, occurrences, prefixes

#: What `_shared/walk_sequence_ids.py` answers for a payload that names no
#: vehicle at all, spelled so a fixture reads as the feed rather than as Python.
ABSENT = None


def update(vehicle_id: str | None = ABSENT, trip_id: str = "T1") -> dict[str, object]:
    built: dict[str, object] = {"trip": {"trip_id": trip_id}}
    if vehicle_id is not ABSENT:
        built["vehicle"] = {"id": vehicle_id}
    return built


def position(vehicle_id: str | None = ABSENT, trip_id: str = "T1") -> dict[str, object]:
    return update(vehicle_id, trip_id)


def run_over(now, was):
    return check(now, context(previous=was))


def reported(
    trip_id: str = "T1", previous: str = "V1", current: str = "V2", payload: str = "trip_update"
) -> str:
    return (
        f'the {payload} carrying trip_id {trip_id} has vehicle.id "{current}" in this message '
        f'and had "{previous}" in the previous message of this feed'
    )


def test_a_vehicle_id_that_moved_between_two_messages_is_reported():
    was = message(entity(trip_update=update("V1"), entity_id="e1"))
    now = message(entity(trip_update=update("V2"), entity_id="e1"))

    assert prefixes(run_over(now, was)) == [reported()]


def test_the_same_trip_under_the_same_vehicle_id_is_silent():
    """The conformant twin."""
    was = message(entity(trip_update=update("V1"), entity_id="e1"))
    now = message(entity(trip_update=update("V1"), entity_id="e1"))

    assert prefixes(run_over(now, was)) == []


def test_the_first_message_of_a_role_reports_nothing():
    now = message(entity(trip_update=update("V1"), entity_id="e1"))

    assert prefixes(run_over(now, None)) == []


def test_a_trip_the_previous_message_did_not_carry_is_silent():
    was = message(entity(trip_update=update("V1", "T9"), entity_id="e1"))
    now = message(entity(trip_update=update("V2", "T1"), entity_id="e1"))

    assert prefixes(run_over(now, was)) == []


def test_a_trip_that_named_no_vehicle_and_now_names_one_is_silent():
    """Absent is not an id, so a descriptor appearing is not an id moving. The
    missing id is its own defect and W002 is the rule that reports it, for a
    VehiclePosition; reporting it here would report it a second time under a
    citation about stability."""
    was = message(entity(trip_update=update(ABSENT), entity_id="e1"))
    now = message(entity(trip_update=update("V1"), entity_id="e1"))

    assert prefixes(run_over(now, was)) == []


def test_a_trip_that_named_a_vehicle_and_now_names_none_is_silent():
    """The same argument in the other direction."""
    was = message(entity(trip_update=update("V1"), entity_id="e1"))
    now = message(entity(trip_update=update(ABSENT), entity_id="e1"))

    assert prefixes(run_over(now, was)) == []


def test_two_messages_naming_no_vehicle_at_all_are_silent():
    was = message(entity(trip_update=update(ABSENT), entity_id="e1"))
    now = message(entity(trip_update=update(ABSENT), entity_id="e1"))

    assert prefixes(run_over(now, was)) == []


def test_a_blank_id_that_became_a_real_one_is_a_change():
    """`""` is a value the feed set, unlike an absent descriptor, so it is an id
    that moved. `StringUtils.isEmpty` collapses the two and this rule may not."""
    was = message(entity(trip_update=update(""), entity_id="e1"))
    now = message(entity(trip_update=update("V1"), entity_id="e1"))

    assert prefixes(run_over(now, was)) == [reported(previous="", current="V1")]


def test_a_real_id_that_became_blank_is_a_change():
    was = message(entity(trip_update=update("V1"), entity_id="e1"))
    now = message(entity(trip_update=update(""), entity_id="e1"))

    assert prefixes(run_over(now, was)) == [reported(previous="V1", current="")]


def test_a_blank_id_that_stayed_blank_is_silent():
    was = message(entity(trip_update=update(""), entity_id="e1"))
    now = message(entity(trip_update=update(""), entity_id="e1"))

    assert prefixes(run_over(now, was)) == []


def test_an_entity_id_that_moved_is_not_this_rules_finding():
    """P002's."""
    was = message(entity(trip_update=update("V1"), entity_id="e1"))
    now = message(entity(trip_update=update("V1"), entity_id="e2"))

    assert prefixes(run_over(now, was)) == []


def test_a_vehicle_position_is_checked_as_well_as_a_trip_update():
    was = message(entity(vehicle=position("V1"), entity_id="e1"))
    now = message(entity(vehicle=position("V2"), entity_id="e1"))

    assert prefixes(run_over(now, was)) == [reported(payload="vehicle")]


def test_two_vehicle_positions_sharing_one_id_in_one_message_are_e052s_finding():
    """Within one message, `:89`'s unique half is E052's and this rule is silent
    on it: both trips kept the vehicle they had."""
    was = message(
        entity(vehicle=position("V1", "T1"), entity_id="a"),
        entity(vehicle=position("V1", "T2"), entity_id="b"),
    )
    now = message(
        entity(vehicle=position("V1", "T1"), entity_id="a"),
        entity(vehicle=position("V1", "T2"), entity_id="b"),
    )

    assert prefixes(run_over(now, was)) == []


def test_every_moved_trip_is_reported_in_this_messages_entity_order():
    was = message(
        entity(trip_update=update("V1", "T1"), entity_id="a"),
        entity(trip_update=update("V2", "T2"), entity_id="b"),
    )
    now = message(
        entity(trip_update=update("V9", "T2"), entity_id="b"),
        entity(trip_update=update("V8", "T1"), entity_id="a"),
    )

    assert prefixes(run_over(now, was)) == [
        reported("T2", previous="V2", current="V9"),
        reported("T1", previous="V1", current="V8"),
    ]


def test_the_occurrence_locates_this_messages_payload_and_names_both_ids():
    was = message(entity(trip_update=update("V1"), entity_id="e1"))
    now = message(
        entity(vehicle=position("V9", "T9"), entity_id="other"),
        entity(trip_update=update("V2"), entity_id="e1"),
    )

    found = occurrences(run_over(now, was))

    assert [one.rule_id for one in found] == ["P003"]
    assert [one.context["entityPath"] for one in found] == ["entity[1].trip_update"]
    assert [one.context["tripId"] for one in found] == ["T1"]
    assert [one.context["vehicleId"] for one in found] == ["V2"]
    assert [one.context["previousVehicleId"] for one in found] == ["V1"]


def written(path: Path, timestamp: int, *entities: dict[str, object]) -> Path:
    header = {"gtfs_realtime_version": "2.0", "incrementality": 0, "timestamp": timestamp}
    path.write_bytes(encode({"header": header, "entity": list(entities)}, V2015))
    return path


def two_role_run(tmp_path: Path, first_tu: str, second_tu: str):
    """A two-cycle run whose VehiclePositions role names a vehicle the
    TripUpdates role never does, so a global "previous" would report both."""
    config = a_config(tmp_path, registry=registry_of(a_rule("P003", check)))
    vp = entity(vehicle=position("VP-V"), entity_id="vp-e")
    first = {
        "tu": written(tmp_path / "tu-1.pb", 1_700_000_000, entity(trip_update=update(first_tu))),
        "vp": written(tmp_path / "vp-1.pb", 1_700_000_000, vp),
    }
    second = {
        "tu": written(tmp_path / "tu-2.pb", 1_700_000_030, entity(trip_update=update(second_tu))),
        "vp": written(tmp_path / "vp-2.pb", 1_700_000_030, vp),
    }
    return run(config, [role_cycle(first), role_cycle(second)])


def test_a_two_role_run_compares_each_role_against_its_own_previous(tmp_path):
    """Each role's vehicle id is stable within the role and different between
    the roles, so nothing here moved."""
    assert two_role_run(tmp_path, "TU-V", "TU-V").notices.rule_ids() == ()


def test_a_two_role_run_reports_the_role_whose_id_actually_moved(tmp_path):
    """The other direction, so the test above cannot pass on a rule that never
    fires."""
    found = two_role_run(tmp_path, "TU-V", "TU-W").notices.samples_for("P003")

    assert [one.prefix for one in found] == [reported(previous="TU-V", current="TU-W")]
    assert [Path(one.context["sourceFile"]).name for one in found] == ["tu-2.pb"]
