"""W004, against upstream's own `VehicleValidatorTest.testW004`.

Every assertion marked "upstream" is transcribed from the real
`VehicleValidatorTest.java` in the checkout at `jar-build/upstream/`
(`testW004`, lines 100-168), not from a second-hand summary of it. Upstream
asserts *counts* and nothing else, so every assertion about occurrence text
below is ours, read off `VehicleValidator.java:96-104`.

Upstream runs those cases against `bullrunner-gtfs.zip`, which is not in this
repository. `rulefixtures.minimal()` stands in for it, and upstream's own USF
campus coordinate is inside its agency box too, so W004 is the only rule that
can fire. The coordinate and all four speeds here are upstream's.

The mph figure goes through `String.format("%.2f", ...)` with no `Locale`
argument, so its decimal separator follows the JVM default. The expectations
below are dot-separated because that is what the measured environment produces;
a jar run under a comma-decimal locale writes `"69,35"` and differs here.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path

import pytest

from gtfs_rt_validator.report.occurrence import ENTITY_PATH_KEY, Occurrence
from gtfs_rt_validator.rules.upstream.w004 import check
from rulefixtures import context, entity, message, minimal, occurrences, prefixes

#: `testW004`'s "Valid lat and long (USF Campus in Tampa, FL), as they are
#: required fields".
USF_CAMPUS = (28.0587, -82.4139)


def vehicle(
    speed: float | None = None,
    *,
    point: tuple[float, float] | None = USF_CAMPUS,
    vehicle_id: str | None = "1",
) -> dict[str, object]:
    built: dict[str, object] = {}
    if vehicle_id is not None:
        built["vehicle"] = {"id": vehicle_id}
    if point is not None:
        position: dict[str, object] = {"latitude": point[0], "longitude": point[1]}
        if speed is not None:
            position["speed"] = speed
        built["position"] = position
    return built


def run(tmp_path: Path, *entities: Mapping[str, object]) -> Sequence[Occurrence]:
    return occurrences(check(message(*entities), context(tmp_path, minimal())))


def at_speed(tmp_path: Path, speed: float | None, **kwargs: object) -> Sequence[Occurrence]:
    return run(tmp_path, entity(vehicle=vehicle(speed, **kwargs)))  # type: ignore[arg-type]


# --- upstream's own case, stage by stage ------------------------------------


def test_a_vehicle_with_no_position_reports_nothing(tmp_path):
    """Upstream, testW004: "No warnings, if speed isn't populated" is asserted
    with no position at all, since the position is set only afterwards."""
    assert at_speed(tmp_path, None, point=None) == []


def test_a_position_with_no_speed_reports_nothing(tmp_path):
    """Ours, the other half of `:96`: `hasPosition() && hasSpeed()`."""
    assert at_speed(tmp_path, None) == []


def test_thirteen_metres_per_second_reports_nothing(tmp_path):
    """Upstream, testW004: `13.0f`, "Valid speed of ~30 miles per hour"."""
    assert at_speed(tmp_path, 13.0) == []


def test_minus_thirteen_metres_per_second_reports_once(tmp_path):
    """Upstream, testW004: `-13.0f`, `expected.put(W004, 1)`."""
    assert len(at_speed(tmp_path, -13.0)) == 1


def test_thirty_one_metres_per_second_reports_once(tmp_path):
    """Upstream, testW004: `31.0f` (~70 mph), `expected.put(W004, 1)`."""
    assert len(at_speed(tmp_path, 31.0)) == 1


# --- the occurrence text, which upstream's test never looks at --------------


def test_every_occurrence_carries_this_rules_id(tmp_path):
    assert [found.rule_id for found in at_speed(tmp_path, 31.0)] == ["W004"]


def test_the_prefix_names_the_vehicle_the_speed_and_the_speed_in_mph(tmp_path):
    """Ours, read off `:100-101`. Measured on JDK 17:
    `31.0f + ""` is `"31.0"` and `String.format("%.2f", 31.0f * 2.23694f)` is
    `"69.35"`. Python's `f"{31.0 * 2.23694:.2f}"` is `"69.35"` too, but its
    rounding is banker's and the multiplier is the double 2.23694 rather than
    the float, so the agreement is a coincidence of this value."""
    assert prefixes(at_speed(tmp_path, 31.0)) == ["vehicle.id 1 speed of 31.0 m/s (69.35 mph)"]


def test_a_negative_speed_keeps_its_sign_in_both_figures(tmp_path):
    """Ours. Measured on JDK 17: `String.format("%.2f", -13.0f * 2.23694f)` is
    `"-29.08"`."""
    assert prefixes(at_speed(tmp_path, -13.0)) == ["vehicle.id 1 speed of -13.0 m/s (-29.08 mph)"]


def test_a_vehicle_with_no_id_falls_back_to_the_entity_id(tmp_path):
    """Ours: `getVehicleId(entity, v)` at `:100`."""
    assert prefixes(at_speed(tmp_path, 31.0, vehicle_id=None)) == [
        "entity ID TEST_ENTITY speed of 31.0 m/s (69.35 mph)"
    ]


def test_an_explicitly_empty_vehicle_id_keeps_the_label_and_leaves_a_double_space(tmp_path):
    """Ours, measured. `getVehicleId` branches on `hasId()`
    (GtfsUtils.java:226), not on emptiness, so a descriptor carrying `id = ""`
    takes the `vehicle.id ` arm and the empty id sits between two spaces. The
    jar wrote exactly this for an entity with a valid position and a speed of
    31; a truthiness check would have written `entity ID TEST_ENTITY ...`
    instead and passed the case above.
    """
    assert prefixes(at_speed(tmp_path, 31.0, vehicle_id="")) == [
        "vehicle.id  speed of 31.0 m/s (69.35 mph)"
    ]


def test_the_occurrence_locates_the_vehicle_position_it_came_from(tmp_path):
    found = at_speed(tmp_path, 31.0)

    assert found[0].context[ENTITY_PATH_KEY] == "entity[0].vehicle"


# --- the two bounds, both strict --------------------------------------------


@pytest.mark.parametrize("speed", [0.0, 26.0])
def test_both_bounds_are_strict_so_neither_endpoint_reports(tmp_path, speed):
    """Ours, read off `:97-98`: `speed > 26.0f || speed < 0f`. `26.0f` is
    exactly representable, so the boundary is not a rounding question."""
    assert at_speed(tmp_path, speed) == []


def test_just_past_the_upper_bound_reports(tmp_path):
    """Ours. The float32 just above 26.0 is 26.000002, which is what a feed
    carrying a value slightly over the limit actually holds."""
    found = at_speed(tmp_path, 26.000002)

    assert prefixes(found) == ["vehicle.id 1 speed of 26.000002 m/s (58.16 mph)"]


def test_entities_are_reported_in_feed_order(tmp_path):
    found = run(
        tmp_path,
        entity(vehicle=vehicle(31.0), entity_id="one"),
        entity(vehicle=vehicle(13.0, vehicle_id="2"), entity_id="two"),
        entity(vehicle=vehicle(-13.0, vehicle_id="3"), entity_id="three"),
    )

    assert prefixes(found) == [
        "vehicle.id 1 speed of 31.0 m/s (69.35 mph)",
        "vehicle.id 3 speed of -13.0 m/s (-29.08 mph)",
    ]
