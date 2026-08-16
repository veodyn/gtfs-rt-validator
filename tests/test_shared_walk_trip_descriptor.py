"""`TripDescriptorValidator`'s one pass, as a walk fifteen rule modules read.

What is asserted here is the part no single rule test can see: which of the
three halves of an entity runs first, and how many times a rule can fire per
entity. Each rule's counts and occurrence text are pinned in its own file,
against upstream's `TripDescriptorValidatorTest`. W009's whole-feed suppression
list lives in `test_rule_w009.py` with the rule it distorts, and the
schedule_relationship enum gap in `test_rule_e003.py`, `test_rule_e016.py` and
`test_rule_w009.py`, those three being the rules it reaches.

Nothing below is ported. Upstream has no test for emission order, because its
validator builds fifteen lists and never interleaves them. The order matters
here because `--compat` writes one group per rule and the occurrences inside a
group in the order the loop produced them.

**The two vehicle-bearing halves are not symmetric** (`:95-141` against
`:142-176`). The VehiclePosition side has an `isEmpty(tripId)` guard the
TripUpdate side lacks, and its four unconditional checks run E004 before E021
where the TripUpdate side runs E021 before E004. Upstream writes each to its own
list, so there the order reaches no output byte; here it is one stream, so it
has to be the Java's.
"""

from __future__ import annotations

from pathlib import Path

from gtfs_rt_validator.report.occurrence import ENTITY_PATH_KEY
from gtfs_rt_validator.rules._shared.walk_trip_descriptor import trip_descriptors
from gtfs_rt_validator.rules._shared.walks import walk_events
from rulefixtures import ENTITY_ID, entity, message
from tripfixtures import AGENCY_ID, SCHEDULED, alert, feed_context, selector, td


def events(tmp_path: Path, *entities) -> list[tuple[str, str]]:
    """Every event the walk yields, as `(rule_id, prefix)` pairs in its order."""
    found = walk_events(trip_descriptors, message(*entities), feed_context(tmp_path))
    return [(event.rule_id, event.prefix) for event in found]


#: A descriptor wrong in as many ways as one entity can be at once, so that the
#: order of the checks around it is observable in one stream.
BAD_TRIP = td(trip_id="100", route_id="999", start_time="bad", start_date="bad", direction_id=1)

E035_ON_TRIP_ONE = (
    f"GTFS-rt entity ID {ENTITY_ID} trip_id 1 has route_id B but belongs to GTFS route_id A"
)
E030_ON_TRIP_ONE = (
    f"alert ID {ENTITY_ID} informed_entity.trip.trip_id 1 does not belong to "
    "informed_entity.route_id 2 (GTFS says it belongs to route_id A)"
)
E031_ON_TRIP_ONE = (
    f"alert ID {ENTITY_ID} informed_entity.route_id 2 does not equal "
    "informed_entity.trip.route_id B"
)


# --- the three halves, and the order of the checks inside each ---------------


def test_the_trip_update_half_runs_its_checks_in_the_javas_order(tmp_path: Path) -> None:
    """`:95-141`: the trip_id block, then E020 under `hasStartTime()`, then
    E021, E004, E024 and E035, then the stop_time_update W009s, then the
    trip-level W009."""
    found = events(
        tmp_path,
        entity(trip_update={"trip": BAD_TRIP, "stop_time_update": [{"stop_id": "S1"}]}),
    )

    assert found == [
        ("E003", "trip_id 100"),
        ("E020", "trip_id 100 start_time is bad"),
        ("E021", "trip_id 100 start_date is bad"),
        ("E004", "route_id 999"),
        ("W009", "trip_id 100 stop_id S1 (and potentially more for this trip)"),
        ("W009", "trip_id 100"),
    ]


def test_the_vehicle_half_runs_e004_before_e021_where_the_trip_update_half_does_not(
    tmp_path: Path,
) -> None:
    """`:167-175`. E004 reads `getVehicleAndRouteId` (`:262`) and E021 reads
    `getVehicleAndTripIdText` (`:316`), so what the two halves reverse is the
    call order of two different helpers rather than two overloads of one."""
    found = events(tmp_path, entity(vehicle={"trip": BAD_TRIP, "vehicle": {"id": "V1"}}))

    assert found == [
        ("E003", "vehicle_id V1 trip_id 100"),
        ("E020", "vehicle_id V1 trip_id 100 start_time is bad"),
        ("E004", "vehicle_id V1 route_id 999"),
        ("E021", "vehicle_id V1 trip_id 100 start_date is bad"),
        ("W009", "trip_id 100"),
    ]


def test_the_alert_half_runs_e033_e034_e035_then_e030_e031_then_w006_and_w009(
    tmp_path: Path,
) -> None:
    """`:181-192`, per informed_entity. The second selector is here for W006 and
    W009, which need a trip with no trip_id and so cannot coexist with E030 and
    E035 on the same selector."""
    found = events(
        tmp_path,
        entity(
            alert=alert(
                selector(agency_id="bad", route_id="2", trip=td(trip_id="1", route_id="B")),
                selector(route_id="2", trip=td()),
            )
        ),
    )

    assert found == [
        ("E034", f"alert ID {ENTITY_ID} agency_id bad"),
        ("E035", E035_ON_TRIP_ONE),
        ("E030", E030_ON_TRIP_ONE),
        ("E031", E031_ON_TRIP_ONE),
        ("W009", "trip_id 1"),
        ("W006", f"entity ID {ENTITY_ID}"),
        ("W009", f"entity ID {ENTITY_ID}"),
    ]


def test_one_entity_reports_its_trip_update_then_its_vehicle_then_its_alert(
    tmp_path: Path,
) -> None:
    """The three halves at `:95`, `:142` and `:177`. This is upstream's own
    `testW009TripDescriptor` feed, whose three warnings it counts but does not
    order."""
    descriptor = td(trip_id="1")
    found = events(
        tmp_path,
        entity(
            trip_update={"trip": descriptor},
            vehicle={"trip": descriptor, "vehicle": {"id": "V1"}},
            alert=alert(selector(trip=descriptor)),
        ),
    )

    assert found == [("W009", "trip_id 1")] * 3


def test_entities_are_walked_in_feed_order(tmp_path: Path) -> None:
    found = events(
        tmp_path,
        entity(trip_update={"trip": td(trip_id="100")}, entity_id="one"),
        entity(trip_update={"trip": td(trip_id="101")}, entity_id="two"),
    )

    assert [prefix for rule_id, prefix in found if rule_id == "E003"] == [
        "trip_id 100",
        "trip_id 101",
    ]


def test_the_entity_path_locates_every_site_the_walk_reports_from(tmp_path: Path) -> None:
    """Ours, and modern-mode only: `--compat` writes the prefix alone. A rule
    inside a shared loop cannot rebuild the position the loop was standing at,
    which is why `Event` carries a context at all."""
    descriptor = td(trip_id="100")
    found = walk_events(
        trip_descriptors,
        message(
            entity(
                trip_update={"trip": descriptor, "stop_time_update": [{"stop_id": "S1"}]},
                vehicle={"trip": descriptor, "vehicle": {"id": "V1"}},
                alert=alert(selector(agency_id="bad")),
            )
        ),
        feed_context(tmp_path),
    )

    assert [event.context[ENTITY_PATH_KEY] for event in found] == [
        "entity[0].trip_update.trip",
        "entity[0].trip_update.stop_time_update[0]",
        "entity[0].trip_update.trip",
        "entity[0].vehicle.trip",
        "entity[0].vehicle.trip",
        "entity[0].alert.informed_entity[0]",
    ]


# --- the guards that make the two vehicle-bearing halves differ --------------


def test_an_empty_trip_id_is_looked_up_on_one_side_and_skipped_on_the_other(
    tmp_path: Path,
) -> None:
    """`:148`'s `StringUtils.isEmpty(tripId)`, which `:100` has no counterpart
    for. `hasTripId()` is true for a trip_id set to the empty string, so W006
    stays quiet on both sides and only the TripUpdate half goes on to look the
    empty string up in `trips.txt`."""
    empty = td(trip_id="", schedule_relationship=SCHEDULED)
    found = events(
        tmp_path,
        entity(trip_update={"trip": empty}, vehicle={"trip": empty, "vehicle": {"id": "V1"}}),
    )

    assert found == [("E003", "trip_id ")]


def test_a_vehicle_position_with_no_trip_is_not_examined_at_all(tmp_path: Path) -> None:
    """`:142`'s `hasVehicle() && getVehicle().hasTrip()`. Without the second
    half a VehiclePosition carrying nothing would report W006 and W009."""
    assert events(tmp_path, entity(vehicle={"vehicle": {"id": "V1"}})) == []


def test_a_trip_update_with_no_trip_id_reports_w006_and_looks_up_nothing(
    tmp_path: Path,
) -> None:
    """`:97-98`: the `if` arm, so E003, E016 and E023 are all unreachable for it."""
    found = events(tmp_path, entity(trip_update={"trip": td(route_id="1")}))

    assert found == [("W006", f"entity ID {ENTITY_ID}"), ("W009", f"entity ID {ENTITY_ID}")]


def test_e004_is_never_called_for_an_alert(tmp_path: Path) -> None:
    """`checkE004` has exactly two call sites, `:123` and `:171`, and neither is
    in the alert half. An informed_entity.trip.route_id that exists in no
    `routes.txt` is therefore not an E004, and nobody found a comment saying
    why. Compat must not add one."""
    descriptor = td(trip_id="1", route_id="999", schedule_relationship=SCHEDULED)

    from_alert = events(tmp_path, entity(alert=alert(selector(trip=descriptor))))
    from_trip_update = events(tmp_path, entity(trip_update={"trip": descriptor}))

    assert from_alert == []
    assert from_trip_update == [("E004", "route_id 999")]


def test_e035_is_called_for_every_selector_and_ahead_of_the_hastrip_guard(
    tmp_path: Path,
) -> None:
    """`:184` calls `checkE035(entitySelector.getTrip())` outside the
    `hasTrip()` guard at `:189` that wraps W006 and W009, so a selector with no
    trip hands it the default TripDescriptor and it short-circuits on
    `hasTripId()`.

    A selector that produces nothing is no evidence of that: it reads the same
    whether the call is made and returns early, moved inside the guard, or
    deleted. So the silent selector is only half the feed, and the assertion
    rests on the second one, which fires. Two mutations it catches, both
    measured against a mutant of the walk: deleting the call loses the E035
    altogether, and moving it inside the `hasTrip()` guard emits it after E030
    and E031 instead of before them, since a guarded call would run where W006
    and W009 do."""
    found = events(
        tmp_path,
        entity(
            alert=alert(
                selector(agency_id=AGENCY_ID),
                selector(route_id="2", trip=td(trip_id="1", route_id="B")),
            )
        ),
    )

    assert found == [
        ("E035", E035_ON_TRIP_ONE),
        ("E030", E030_ON_TRIP_ONE),
        ("E031", E031_ON_TRIP_ONE),
        ("W009", "trip_id 1"),
    ]


def test_an_alert_with_no_informed_entity_reports_e032_and_nothing_else(
    tmp_path: Path,
) -> None:
    """`:194-197`, the `else` of the non-empty test."""
    found = events(tmp_path, entity(alert=alert(), entity_id="A1"))

    assert found == [("E032", "alert ID A1 does not have an informed_entity")]
