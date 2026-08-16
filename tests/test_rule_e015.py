"""E015, against upstream's own `StopValidatorTest` and the prefixes it never asserts.

Every assertion marked "upstream" is transcribed from the real
`StopValidatorTest.java` in the checkout at `jar-build/upstream/`
(`testE015`, lines 119-181), not from a second-hand summary of it. As with
E011, upstream asserts *counts* only, so every assertion about occurrence text
is ours and comes from reading `StopValidator.java:53-101`.

The static feed mirrors `testagency2.zip`, whose header comment upstream writes
out in full: `stop_id A` has `location_type = 0` and `stop_id B` has
`location_type = 1`.

The two things that separate this rule from E011 are both asserted below.
Alerts are exempt, so upstream's fourth stage still expects 2. And the
`locationType != null` guard is dead: `Stop.locationType` is a primitive `int`
defaulting to 0 in onebusaway, so the map holds a value for every stop it
holds at all, and the guard only fires for a stop_id absent from the feed,
which is E011's case and not this one.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path

from gtfs_rt_validator.proto.decode import Msg, decode
from gtfs_rt_validator.proto.encode import encode
from gtfs_rt_validator.proto.schema_2015 import SCHEMA
from gtfs_rt_validator.rules.upstream.e015 import check
from gtfs_rt_validator.runner.clock import ClockSource, Reading
from gtfs_rt_validator.runner.context import RuleContext
from gtfs_rt_validator.static.adapter import load_static
from gtfs_rt_validator.static.context import StaticContext
from gtfsfixtures import build_feed, minimal_tables

#: `FeedMessageTest.ENTITY_ID`.
ENTITY_ID = "TEST_ENTITY"

READING = Reading(1_700_000_000_000, ClockSource.FIXED)

#: `testagency2.zip`, reduced to the two stops its own comment describes.
TESTAGENCY2_STOPS = {"A": 0, "B": 1}


def context(tmp_path: Path, stops: Mapping[str, int] = TESTAGENCY2_STOPS) -> RuleContext:
    """A rule context over a static feed carrying exactly these stops.

    Through `gtfsfixtures` and the real sibling loader, as
    `tests/test_static_context.py` does, so `stop_location_types` is what the
    loader produced rather than a dict this file asserted into existence.
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


def run(tmp_path: Path, *entities: Mapping[str, object], stops=TESTAGENCY2_STOPS) -> Sequence:
    return list(check(message(*entities), context(tmp_path, stops)))


# --- upstream's own case, stage by stage ------------------------------------


def test_a_location_type_zero_stop_in_all_three_places_reports_nothing(tmp_path):
    """Upstream, testE015: stop_id `A` everywhere, `expected.clear()`."""
    found = run(
        tmp_path,
        entity(trip_update("A"), vehicle_position("A"), alert("A")),
    )

    assert found == []


def test_a_location_type_one_stop_in_a_stop_time_update_reports_once(tmp_path):
    """Upstream, testE015: `expected.put(E015, 1)`."""
    found = run(
        tmp_path,
        entity(trip_update("A", "B"), vehicle_position("A"), alert("A")),
    )

    assert len(found) == 1


def test_a_location_type_one_stop_in_the_vehicle_position_too_reports_twice(tmp_path):
    """Upstream, testE015: `expected.put(E015, 2)`."""
    found = run(
        tmp_path,
        entity(trip_update("A", "B"), vehicle_position("B"), alert("A")),
    )

    assert len(found) == 2


def test_a_location_type_one_stop_in_an_informed_entity_is_still_only_two(tmp_path):
    """Upstream, testE015: `expected.put(E015, 2)` again, with its own comment
    saying why: "Alerts can reference location_types other than 0."."""
    found = run(
        tmp_path,
        entity(trip_update("A", "B"), vehicle_position("B"), alert("A", "B")),
    )

    assert len(found) == 2


def test_an_alert_alone_reports_nothing_however_bad_its_stop(tmp_path):
    """Ours, isolating what the stage above only shows by its count not moving:
    the alert branch of `StopValidator` has no E015 site at all (`:90-100`)."""
    found = run(tmp_path, entity(alert=alert("B", "B")))

    assert found == []


# --- the occurrence text, which upstream's test never looks at --------------


def test_every_occurrence_carries_this_rules_id(tmp_path):
    found = run(tmp_path, entity(trip_update("B")))

    assert [occurrence.rule_id for occurrence in found] == ["E015"]


def test_the_trip_update_prefix_names_the_trip_and_the_stop(tmp_path):
    """Ours. The same `prefix` local E011 uses, built at StopValidator.java:60
    and read by both sites in that branch."""
    found = run(tmp_path, entity(trip_update("B", trip_id="T1")))

    assert prefixes(found) == ["trip_id T1 stop_id B"]


def test_an_absent_trip_id_leaves_a_double_space_in_the_prefix(tmp_path):
    """Ours. Unguarded `getTripId()`, exactly as in E011, and exactly what
    upstream's own testE015 feed produces."""
    found = run(tmp_path, entity(trip_update("B")))

    assert prefixes(found) == ["trip_id  stop_id B"]


def test_the_vehicle_position_prefix_names_the_vehicle_when_it_has_an_id(tmp_path):
    """Ours, read off StopValidator.java:85, which rebuilds the same ternary
    the E011 site above it built."""
    found = run(tmp_path, entity(vehicle=vehicle_position("B", "1")))

    assert prefixes(found) == ["vehicle_id 1 stop_id B"]


def test_a_vehicle_position_with_no_vehicle_id_drops_the_clause_entirely(tmp_path):
    """Ours. Upstream's own testE015 sets no VehicleDescriptor, so this is the
    text the jar emits for its own test feed."""
    found = run(tmp_path, entity(vehicle=vehicle_position("B")))

    assert prefixes(found) == ["stop_id B"]


# --- the dead null guard, and the ordering ----------------------------------


def test_a_stop_id_absent_from_the_feed_is_e011s_case_and_not_this_one(tmp_path):
    """Ours. `getStopToLocationTypeMap().get(stopId)` returns null only for a
    stop the feed does not have, and the guard drops it. That reference is
    already an E011, and reporting it here as well would double-count it."""
    found = run(
        tmp_path,
        entity(trip_update("DUMMY"), vehicle_position("DUMMY")),
    )

    assert found == []


def test_any_nonzero_location_type_fires_not_only_one(tmp_path):
    """Ours. The condition is `locationType != 0`, so a station entrance
    (`location_type = 2`) is as much a finding as a station."""
    found = run(tmp_path, entity(trip_update("E2")), stops={"E2": 2})

    assert prefixes(found) == ["trip_id  stop_id E2"]


def test_one_entity_reports_stop_time_updates_then_the_vehicle(tmp_path):
    """Ours. Two branches rather than E011's three, in the Java's own order."""
    found = run(
        tmp_path,
        entity(trip_update("B", "B", trip_id="T1"), vehicle_position("B", "1"), alert("B")),
    )

    assert prefixes(found) == [
        "trip_id T1 stop_id B",
        "trip_id T1 stop_id B",
        "vehicle_id 1 stop_id B",
    ]


def test_a_reference_with_no_stop_id_at_all_is_not_a_finding(tmp_path):
    """Ours. Both sites sit inside the same `hasStopId()` guard E011 uses."""
    found = run(tmp_path, entity(trip_update(None, trip_id="T1"), vehicle_position()))

    assert found == []


# --- the trap: the bare stop_id, never the compound AgencyAndId -------------


def test_the_lookup_is_the_bare_stop_id_not_the_agency_prefixed_one(tmp_path):
    """Ours, and the mistake in this rule worth naming outright.

    E010's emitter keys on `stopTime.getStop().getId()`, an `AgencyAndId` whose
    `toString()` is `agencyId + "_" + id`; `StopValidator` keys on the bare
    `getStopId()`. The static feed has agency `A1`, so `A1_B` is the compound
    form of stop `B`. It is absent from `stop_location_types` under that
    spelling, so a rule that looked it up the E010 way would silently find
    nothing here and would report nothing for `B`.
    """
    assert prefixes(run(tmp_path, entity(trip_update("B")))) == ["trip_id  stop_id B"]
    assert run(tmp_path, entity(trip_update("A1_B"))) == []
