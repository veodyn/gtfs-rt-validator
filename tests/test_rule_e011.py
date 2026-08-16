"""E011, against upstream's own `StopValidatorTest` and the prefixes it never asserts.

Every assertion marked "upstream" is transcribed from the real
`StopValidatorTest.java` in the checkout at `jar-build/upstream/`
(`testE011`, lines 45-109), not from a second-hand summary of it. Upstream's
test asserts *counts* and nothing else, so every assertion about occurrence
text below is ours: the three prefix shapes come from reading
`StopValidator.java:53-101` directly.

The static feed mirrors `testagency.zip`, where `A` is a real stop and `DUMMY`
is not. Upstream builds one FeedEntity carrying a TripUpdate, a VehiclePosition
and an Alert at once, with `id = "TEST_ENTITY"` from `FeedMessageTest`, and
this ports that shape rather than splitting it: the single entity is what makes
the three-way ordering observable.

Messages go through the real encoder and decoder, so a field name the 2015
schema does not have fails here rather than reading as an absent default.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path

from gtfs_rt_validator.proto.decode import Msg, decode
from gtfs_rt_validator.proto.encode import encode
from gtfs_rt_validator.proto.schema_2015 import SCHEMA
from gtfs_rt_validator.rules.upstream.e011 import check
from gtfs_rt_validator.runner.clock import ClockSource, Reading
from gtfs_rt_validator.runner.context import RuleContext
from gtfs_rt_validator.static.adapter import load_static
from gtfs_rt_validator.static.context import StaticContext
from gtfsfixtures import build_feed, minimal_tables

#: `FeedMessageTest.ENTITY_ID`. Every entity upstream's rule tests build has it.
ENTITY_ID = "TEST_ENTITY"

READING = Reading(1_700_000_000_000, ClockSource.FIXED)

#: `testagency.zip`'s first two stops. Both are location_type 0 there, which is
#: why that feed can say nothing about E015.
TESTAGENCY_STOPS = {"A": 0, "B": 0}


def context(tmp_path: Path, stops: Mapping[str, int] = TESTAGENCY_STOPS) -> RuleContext:
    """A rule context over a static feed carrying exactly these stop ids.

    Built through `gtfsfixtures` and the real sibling loader, the same path
    `tests/test_static_context.py` uses, rather than by handing `StaticContext`
    a dict: `stop_ids` and `stop_location_types` are what the loader produced,
    so a change in how a blank `location_type` types is visible here.
    """
    tables = minimal_tables()
    tables["stops.txt"] += [
        {
            "stop_id": stop_id,
            "stop_name": stop_id,
            "stop_lat": "40",
            "stop_lon": "-73",
            "location_type": str(location_type),
        }
        for stop_id, location_type in stops.items()
    ]
    static = StaticContext.build(load_static(build_feed(tmp_path, tables)))
    return RuleContext(static=static, timezone="America/New_York", clock=READING, source="rt.pb")


def message(*entities: Mapping[str, object]) -> Msg:
    value = {"header": {"gtfs_realtime_version": "1.0"}, "entity": list(entities)}
    return decode(encode(value, SCHEMA), SCHEMA)


def entity(
    trip_update: Mapping[str, object] | None = None,
    vehicle: Mapping[str, object] | None = None,
    alert: Mapping[str, object] | None = None,
    entity_id: str = ENTITY_ID,
) -> dict[str, object]:
    built: dict[str, object] = {"id": entity_id}
    for name, value in (("trip_update", trip_update), ("vehicle", vehicle), ("alert", alert)):
        if value is not None:
            built[name] = value
    return built


def trip_update(*stop_ids: str | None, trip_id: str | None = None) -> dict[str, object]:
    """A TripUpdate whose stop_time_updates carry these stop_ids in order.

    `None` is a stop_time_update with no stop_id at all, which is the branch
    `hasStopId()` guards.
    """
    updates: list[dict[str, object]] = [
        {} if stop_id is None else {"stop_id": stop_id} for stop_id in stop_ids
    ]
    return {"trip": {} if trip_id is None else {"trip_id": trip_id}, "stop_time_update": updates}


def vehicle_position(
    stop_id: str | None = None, vehicle_id: str | None = None
) -> dict[str, object]:
    built: dict[str, object] = {}
    if stop_id is not None:
        built["stop_id"] = stop_id
    if vehicle_id is not None:
        built["vehicle"] = {"id": vehicle_id}
    return built


def alert(*stop_ids: str | None) -> dict[str, object]:
    return {"informed_entity": [{} if s is None else {"stop_id": s} for s in stop_ids]}


def prefixes(found) -> list[str]:
    return [occurrence.prefix for occurrence in found]


def run(tmp_path: Path, *entities: Mapping[str, object], stops=TESTAGENCY_STOPS) -> Sequence:
    return list(check(message(*entities), context(tmp_path, stops)))


# --- upstream's own case, stage by stage ------------------------------------


def test_a_real_stop_id_in_all_three_places_reports_nothing(tmp_path):
    """Upstream, testE011: stop_id `A` in the stop_time_update, the
    VehiclePosition and the informed_entity, `expected.clear()`."""
    found = run(
        tmp_path,
        entity(trip_update("A"), vehicle_position("A", "1"), alert("A")),
    )

    assert found == []


def test_a_dummy_stop_id_in_a_stop_time_update_reports_once(tmp_path):
    """Upstream, testE011: `expected.put(E011, 1)`."""
    found = run(
        tmp_path,
        entity(trip_update("A", "DUMMY"), vehicle_position("A", "1"), alert("A")),
    )

    assert len(found) == 1


def test_a_dummy_stop_id_in_the_vehicle_position_too_reports_twice(tmp_path):
    """Upstream, testE011: `expected.put(E011, 2)`."""
    found = run(
        tmp_path,
        entity(trip_update("A", "DUMMY"), vehicle_position("DUMMY", "1"), alert("A")),
    )

    assert len(found) == 2


def test_a_dummy_stop_id_in_an_informed_entity_too_reports_three_times(tmp_path):
    """Upstream, testE011: `expected.put(E011, 3)`, and alerts are in scope for
    E011 even though they are exempt from E015."""
    found = run(
        tmp_path,
        entity(trip_update("A", "DUMMY"), vehicle_position("DUMMY", "1"), alert("A", "DUMMY")),
    )

    assert len(found) == 3


# --- the occurrence text, which upstream's test never looks at --------------


def test_every_occurrence_carries_this_rules_id(tmp_path):
    found = run(tmp_path, entity(trip_update("DUMMY")))

    assert [occurrence.rule_id for occurrence in found] == ["E011"]


def test_the_trip_update_prefix_names_the_trip_and_the_stop(tmp_path):
    """Ours, read off StopValidator.java:60."""
    found = run(tmp_path, entity(trip_update("DUMMY", trip_id="T1")))

    assert prefixes(found) == ["trip_id T1 stop_id DUMMY"]


def test_an_absent_trip_id_leaves_a_double_space_in_the_prefix(tmp_path):
    """Ours. Unguarded `getTripId()`, so an absent one interpolates as the
    empty string and the two literals collide. Upstream's own testE011 builds
    exactly this descriptor, so this is what the jar emits for its own feed."""
    found = run(tmp_path, entity(trip_update("DUMMY")))

    assert prefixes(found) == ["trip_id  stop_id DUMMY"]


def test_the_vehicle_position_prefix_names_the_vehicle_when_it_has_an_id(tmp_path):
    """Ours, read off StopValidator.java:79. `vehicle_id` with an underscore,
    unlike the `vehicle.id` with a dot that `_shared/ids.py` carries."""
    found = run(tmp_path, entity(vehicle=vehicle_position("DUMMY", "1")))

    assert prefixes(found) == ["vehicle_id 1 stop_id DUMMY"]


def test_a_vehicle_position_with_no_vehicle_id_drops_the_clause_entirely(tmp_path):
    """Ours. The ternary yields the empty string rather than `"vehicle_id "`,
    so the prefix starts at `stop_id`."""
    found = run(tmp_path, entity(vehicle=vehicle_position("DUMMY")))

    assert prefixes(found) == ["stop_id DUMMY"]


def test_a_vehicle_descriptor_with_no_id_drops_the_clause_too(tmp_path):
    """Ours: the `v.getVehicle().hasId()` half of the same ternary."""
    found = run(tmp_path, entity(vehicle={"stop_id": "DUMMY", "vehicle": {"label": "bus"}}))

    assert prefixes(found) == ["stop_id DUMMY"]


def test_the_alert_prefix_names_the_feed_entity_id(tmp_path):
    """Ours, read off StopValidator.java:95. `entityId` is the FeedEntity's own
    id, not the informed_entity's."""
    found = run(tmp_path, entity(alert=alert("DUMMY"), entity_id="ALERT_1"))

    assert prefixes(found) == ["alert entity ID ALERT_1 stop_id DUMMY"]


# --- ordering, guards and de-duplication ------------------------------------


def test_one_entity_reports_stop_time_updates_then_the_vehicle_then_the_alerts(tmp_path):
    """Ours. One pass over entities, and within an entity the three branches
    run in the order the Java writes them (`:57`, `:74`, `:90`)."""
    found = run(
        tmp_path,
        entity(
            trip_update("X1", "X2", trip_id="T1"),
            vehicle_position("X3", "1"),
            alert("X4", "X5"),
        ),
    )

    assert prefixes(found) == [
        "trip_id T1 stop_id X1",
        "trip_id T1 stop_id X2",
        "vehicle_id 1 stop_id X3",
        "alert entity ID TEST_ENTITY stop_id X4",
        "alert entity ID TEST_ENTITY stop_id X5",
    ]


def test_entities_are_reported_in_feed_order(tmp_path):
    found = run(
        tmp_path,
        entity(vehicle=vehicle_position("X1"), entity_id="one"),
        entity(vehicle=vehicle_position("X2"), entity_id="two"),
    )

    assert prefixes(found) == ["stop_id X1", "stop_id X2"]


def test_the_same_bad_stop_id_is_reported_once_per_reference(tmp_path):
    """Ours. No de-duplication anywhere in `StopValidator`, unlike the
    `checkedStops` set in the unreachable `StopLocationTypeValidator`."""
    found = run(tmp_path, entity(trip_update("DUMMY", "DUMMY", trip_id="T1")))

    assert prefixes(found) == ["trip_id T1 stop_id DUMMY"] * 2


def test_a_reference_with_no_stop_id_at_all_is_not_a_finding(tmp_path):
    """Ours. All three sites are guarded by `hasStopId()`, so an absent
    stop_id is never compared against the empty string."""
    found = run(
        tmp_path,
        entity(trip_update(None, trip_id="T1"), vehicle_position(), alert(None)),
    )

    assert found == []


def test_an_entity_carrying_none_of_the_three_is_not_a_finding(tmp_path):
    found = run(tmp_path, entity())

    assert found == []


# --- the trap: the bare stop_id, never the compound AgencyAndId -------------


def test_the_lookup_is_the_bare_stop_id_not_the_agency_prefixed_one(tmp_path):
    """Ours, and the one mistake in this rule worth naming outright.

    `StopLocationTypeValidator` reads `stopTime.getStop().getId()`, whose
    `toString()` is `agencyId + "_" + id`, and it emits E010, which
    `BatchProcessor` never registers. `StopValidator` reads the bare
    `getStopId()`. The feed here has agency `A1` and stop `A`, so the two forms
    are distinguishable: `A` must pass and `A1_A` must fail."""
    assert run(tmp_path, entity(trip_update("A"))) == []
    assert prefixes(run(tmp_path, entity(trip_update("A1_A")))) == ["trip_id  stop_id A1_A"]
