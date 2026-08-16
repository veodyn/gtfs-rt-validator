"""E027, against upstream's own `VehicleValidatorTest.testE027`.

Every assertion marked "upstream" is transcribed from the real
`VehicleValidatorTest.java` in the checkout at `jar-build/upstream/`
(`testE027`, lines 241-314), not from a second-hand summary of it. Upstream
asserts *counts* and nothing else, so every assertion about occurrence text
below is ours, read off `VehicleValidator.java:123-126`.

Upstream runs those cases against `bullrunner-gtfs.zip`, which is not in this
repository. `rulefixtures.minimal()` stands in for it, and upstream's own USF
campus coordinate is inside its agency box too, so E027 is the only rule that
can fire. The coordinate and every bearing here are upstream's.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path

import pytest

from gtfs_rt_validator.report.occurrence import ENTITY_PATH_KEY, Occurrence
from gtfs_rt_validator.rules.upstream.e027 import check
from rulefixtures import context, entity, message, minimal, occurrences, prefixes

#: `testE027`'s "Set valid lat and long ... as they are required fields".
USF_CAMPUS = (28.0587, -82.4139)


def vehicle(
    point: tuple[float, float] | None = USF_CAMPUS,
    bearing: float | None = None,
    *,
    vehicle_id: str | None = "1",
) -> dict[str, object]:
    built: dict[str, object] = {}
    if vehicle_id is not None:
        built["vehicle"] = {"id": vehicle_id}
    if point is not None:
        position: dict[str, object] = {"latitude": point[0], "longitude": point[1]}
        if bearing is not None:
            position["bearing"] = bearing
        built["position"] = position
    return built


def run(tmp_path: Path, *entities: Mapping[str, object]) -> Sequence[Occurrence]:
    return occurrences(check(message(*entities), context(tmp_path, minimal())))


def with_bearing(tmp_path: Path, bearing: float | None, **kwargs: object) -> Sequence[Occurrence]:
    return run(tmp_path, entity(vehicle=vehicle(bearing=bearing, **kwargs)))  # type: ignore[arg-type]


# --- upstream's own case, stage by stage ------------------------------------


def test_a_vehicle_with_no_position_reports_nothing(tmp_path):
    """Upstream, testE027: "No warnings, if position isn't populated"."""
    assert run(tmp_path, entity(vehicle=vehicle(None))) == []


def test_a_position_with_no_bearing_reports_nothing(tmp_path):
    """Upstream, testE027: "No warnings, if bearing isn't populated". The
    `!hasBearing()` short-circuit in `isBearingValid` is what makes this true,
    rather than the proto default of 0 happening to be in range."""
    assert with_bearing(tmp_path, None) == []


def test_a_bearing_of_fifteen_reports_nothing(tmp_path):
    """Upstream, testE027: `positionBuilder.setBearing(15)`, `expected.clear()`."""
    assert with_bearing(tmp_path, 15.0) == []


def test_a_bearing_of_minus_one_reports_once(tmp_path):
    """Upstream, testE027: `expected.put(E027, 1)`."""
    assert len(with_bearing(tmp_path, -1.0)) == 1


def test_a_bearing_of_three_hundred_and_sixty_one_reports_once(tmp_path):
    """Upstream, testE027: `expected.put(E027, 1)`."""
    assert len(with_bearing(tmp_path, 361.0)) == 1


# --- the occurrence text, which upstream's test never looks at --------------


def test_every_occurrence_carries_this_rules_id(tmp_path):
    assert [found.rule_id for found in with_bearing(tmp_path, 361.0)] == ["E027"]


def test_the_prefix_names_the_vehicle_and_the_bearing(tmp_path):
    """Ours, read off `:125`. `getBearing()` is a proto float, so an integral
    bearing prints with a `.0`: measured on JDK 17, `Float.toString(361f)` is
    `"361.0"` and `Float.toString(-1f)` is `"-1.0"`."""
    assert prefixes(with_bearing(tmp_path, 361.0)) == ["vehicle.id 1 has bearing of 361.0"]
    assert prefixes(with_bearing(tmp_path, -1.0)) == ["vehicle.id 1 has bearing of -1.0"]


def test_a_vehicle_with_no_id_falls_back_to_the_entity_id(tmp_path):
    """Ours: `getVehicleId(entity, v)` at `:108`."""
    assert prefixes(with_bearing(tmp_path, 361.0, vehicle_id=None)) == [
        "entity ID TEST_ENTITY has bearing of 361.0"
    ]


def test_an_explicitly_empty_vehicle_id_does_not_fall_back(tmp_path):
    """Ours, measured. `getVehicleId` branches on `hasId()`
    (GtfsUtils.java:226) rather than on emptiness, so `id = ""` keeps the
    `vehicle.id ` label and the empty id sits between two spaces. The jar wrote
    this prefix for a bearing of 361; a truthiness check would have produced the
    entity-ID fallback above and passed both of these tests."""
    assert prefixes(with_bearing(tmp_path, 361.0, vehicle_id="")) == [
        "vehicle.id  has bearing of 361.0"
    ]


def test_the_occurrence_locates_the_vehicle_position_it_came_from(tmp_path):
    found = with_bearing(tmp_path, 361.0)

    assert found[0].context[ENTITY_PATH_KEY] == "entity[0].vehicle"


# --- the bounds, and the independence from E026 -----------------------------


@pytest.mark.parametrize("bearing", [0.0, 360.0])
def test_both_ends_of_the_range_are_inclusive(tmp_path, bearing):
    """Ours, and the reason `isBearingValid` is negated rather than written as a
    range test: `:156` compares with `<` and `>`, so 0 and 360 are both valid."""
    assert with_bearing(tmp_path, bearing) == []


def test_an_invalid_bearing_is_reported_alongside_an_invalid_position(tmp_path):
    """Ours. `:123` is a sibling of the E026 if/else rather than its `else`, so
    a position that already reported E026 is still checked for bearing."""
    built = vehicle(point=(1000.0, -82.4139), bearing=361.0)

    assert len(run(tmp_path, entity(vehicle=built))) == 1


def test_entities_are_reported_in_feed_order(tmp_path):
    found = run(
        tmp_path,
        entity(vehicle=vehicle(bearing=-1.0), entity_id="one"),
        entity(vehicle=vehicle(bearing=361.0, vehicle_id="2"), entity_id="two"),
    )

    assert prefixes(found) == [
        "vehicle.id 1 has bearing of -1.0",
        "vehicle.id 2 has bearing of 361.0",
    ]
