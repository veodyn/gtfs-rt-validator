"""`VehicleValidator.hasDetourAlert`, the whole-feed alert scan E029 alone uses.

`VehicleValidator.java:242-264`, which lives in `_shared/vehicle_bounds.py`.
Split out of `test_shared_walk_vehicle.py`, which pins the loop: this is a pure
function over the entity list and the two ids E029 already resolved, and it fits
neither the loop's fixtures nor its subject.

Upstream's `VehicleValidatorTest.testE029` exercises it through E029 rather than
directly, so its six alert variants are ported in `test_rule_e029.py` where the
counts they assert can be compared. Everything here is ours, read off the Java.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from gtfs_rt_validator.proto.decode import Msg
from gtfs_rt_validator.proto.schema_2015 import SCHEMA as V2015
from gtfs_rt_validator.proto.schema_current import SCHEMA as CURRENT
from gtfs_rt_validator.rules._shared.vehicle_bounds import DETOUR_EFFECT, has_detour_alert
from rulefixtures import entity, message

UNKNOWN_EFFECT = V2015.enums["Alert.Effect"]["UNKNOWN_EFFECT"]


def alert(effect: int | None = DETOUR_EFFECT, **selector: object) -> dict[str, object]:
    """An Alert with one informed_entity whose `trip` carries these fields."""
    built: dict[str, object] = {"informed_entity": [{"trip": dict(selector)}]}
    if effect is not None:
        built["effect"] = effect
    return built


def entities(*built: Mapping[str, object]) -> Sequence[Msg]:
    return message(*built).get("entity")


def test_a_detour_alert_for_the_trip_id_matches():
    found = entities(entity(alert=alert(trip_id="2")))

    assert has_detour_alert(found, "2", None) is True


def test_a_different_trip_id_does_not_match():
    found = entities(entity(alert=alert(trip_id="10")))

    assert has_detour_alert(found, "2", None) is False


def test_a_detour_for_the_route_id_matches_only_when_a_route_id_was_given():
    """`:254` guards on `routeId != null`, which is E029's own
    `hasRouteId()` ternary, not a property of the selector."""
    found = entities(entity(alert=alert(route_id="A")))

    assert has_detour_alert(found, "2", "A") is True
    assert has_detour_alert(found, "2", None) is False


def test_the_route_match_reads_the_selectors_trip_route_id_not_its_own():
    """`:254` is `entitySelector.getTrip().getRouteId()`. A selector naming a
    route directly, with no trip at all, fails `hasTrip()` at `:249`."""
    built = {"effect": DETOUR_EFFECT, "informed_entity": [{"route_id": "A"}]}
    found = entities(entity(alert=built))

    assert has_detour_alert(found, "2", "A") is False


def test_any_effect_other_than_detour_does_not_match():
    found = entities(entity(alert=alert(UNKNOWN_EFFECT, trip_id="2")))

    assert has_detour_alert(found, "2", None) is False


def test_an_alert_with_no_effect_at_all_does_not_match():
    """`hasEffect()` guards the comparison at `:247`, so a feed that leaves the
    field off never reaches the proto default."""
    found = entities(entity(alert=alert(None, trip_id="2")))

    assert has_detour_alert(found, "2", None) is False


def test_an_entity_with_no_alert_is_skipped():
    found = entities(entity(trip_update={"trip": {"trip_id": "2"}}))

    assert has_detour_alert(found, "2", None) is False


def test_the_scan_covers_every_entity_in_the_message():
    found = entities(
        entity(trip_update={"trip": {"trip_id": "2"}}, entity_id="one"),
        entity(alert=alert(trip_id="2"), entity_id="two"),
    )

    assert has_detour_alert(found, "2", None) is True


def test_every_informed_entity_of_one_alert_is_scanned():
    built = {
        "effect": DETOUR_EFFECT,
        "informed_entity": [{"trip": {"trip_id": "10"}}, {"trip": {"trip_id": "2"}}],
    }
    found = entities(entity(alert=built))

    assert has_detour_alert(found, "2", None) is True


def test_the_detour_effect_number_is_the_same_under_both_schemas():
    """Which is why the walk can hold the number without branching on mode: the
    rules layer picks no schema, and a mode branch inside a rule is banned."""
    assert V2015.enums["Alert.Effect"]["DETOUR"] == DETOUR_EFFECT
    assert CURRENT.enums["Alert.Effect"]["DETOUR"] == DETOUR_EFFECT
