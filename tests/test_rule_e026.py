"""E026, against upstream's own `VehicleValidatorTest.testE026` and the text it never reads.

Every assertion marked "upstream" is transcribed from the real
`VehicleValidatorTest.java` in the checkout at `jar-build/upstream/`
(`testE026`, lines 174-235), not from a second-hand summary of it. Upstream
asserts *counts* and nothing else, so every assertion about occurrence text
below is ours, read off `VehicleValidator.java:109-114`.

Upstream runs those four cases against `bullrunner-gtfs.zip`, which is not in
this repository. `rulefixtures.minimal()` stands in for it: its stops and its
one shape both sit around Tampa, so upstream's own USF campus coordinate is
inside the agency box here too and E026 is the only rule that can fire. Its
coordinates are upstream's.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path

import pytest

from gtfs_rt_validator.proto.decode import Msg, decode
from gtfs_rt_validator.proto.encode import encode
from gtfs_rt_validator.proto.errors import DecodeError
from gtfs_rt_validator.proto.schema_2015 import SCHEMA as V2015
from gtfs_rt_validator.report.occurrence import ENTITY_PATH_KEY, Occurrence
from gtfs_rt_validator.rules.upstream.e026 import check
from rulefixtures import context, entity, message, minimal, occurrences, prefixes

#: `testE026`'s own coordinates, in its own order.
USF_CAMPUS = (28.0587, -82.4139)
BAD_LATITUDE = (1000.0, -82.4572)
BAD_LONGITUDE = (27.9506, -1000.0)


def vehicle(
    point: tuple[float, float] | None, *, vehicle_id: str | None = "1"
) -> dict[str, object]:
    built: dict[str, object] = {}
    if vehicle_id is not None:
        built["vehicle"] = {"id": vehicle_id}
    if point is not None:
        built["position"] = {"latitude": point[0], "longitude": point[1]}
    return built


def run(tmp_path: Path, *entities: Mapping[str, object]) -> Sequence[Occurrence]:
    return occurrences(check(message(*entities), context(tmp_path, minimal())))


def at(tmp_path: Path, point: tuple[float, float] | None, **kwargs: object) -> Sequence[Occurrence]:
    return run(tmp_path, entity(vehicle=vehicle(point, **kwargs)))  # type: ignore[arg-type]


# --- upstream's own case, stage by stage ------------------------------------


def test_a_vehicle_with_no_position_reports_nothing(tmp_path):
    """Upstream, testE026: "No warnings, if position isn't populated"."""
    assert at(tmp_path, None) == []


def test_a_position_on_the_usf_campus_reports_nothing(tmp_path):
    """Upstream, testE026: lat `28.0587f`, lon `-82.4139f`, `expected.clear()`."""
    assert at(tmp_path, USF_CAMPUS) == []


def test_a_latitude_of_one_thousand_reports_once(tmp_path):
    """Upstream, testE026: `expected.put(E026, 1)`."""
    assert len(at(tmp_path, BAD_LATITUDE)) == 1


def test_a_longitude_of_minus_one_thousand_reports_once(tmp_path):
    """Upstream, testE026: `expected.put(E026, 1)`."""
    assert len(at(tmp_path, BAD_LONGITUDE)) == 1


# --- the occurrence text, which upstream's test never looks at --------------


def test_every_occurrence_carries_this_rules_id(tmp_path):
    assert [found.rule_id for found in at(tmp_path, BAD_LATITUDE)] == ["E026"]


def test_the_prefix_names_the_vehicle_and_both_coordinates(tmp_path):
    """Ours, read off `:114`. No space after the comma, and both coordinates
    reach the text through `Float.toString`: measured on JDK 17,
    `Float.toString(-82.4572f)` is `"-82.4572"` and `Float.toString(1000f)` is
    `"1000.0"`, which Python's `repr` of the widened double is not."""
    assert prefixes(at(tmp_path, BAD_LATITUDE)) == [
        "vehicle.id 1 has latitude/longitude of (1000.0,-82.4572)"
    ]


def test_the_other_coordinate_renders_the_same_way(tmp_path):
    assert prefixes(at(tmp_path, BAD_LONGITUDE)) == [
        "vehicle.id 1 has latitude/longitude of (27.9506,-1000.0)"
    ]


def test_a_vehicle_with_no_id_falls_back_to_the_entity_id(tmp_path):
    """Ours: `getVehicleId(entity, v)` at `:108`, whose fallback is the
    FeedEntity's own id and not the empty string."""
    assert prefixes(at(tmp_path, BAD_LATITUDE, vehicle_id=None)) == [
        "entity ID TEST_ENTITY has latitude/longitude of (1000.0,-82.4572)"
    ]


def test_an_explicitly_empty_vehicle_id_does_not_fall_back(tmp_path):
    """Ours, measured. `getVehicleId` branches on `hasId()`
    (GtfsUtils.java:226) rather than on emptiness, so `id = ""` keeps the
    `vehicle.id ` label and only the id itself is missing. The jar wrote this
    prefix for these coordinates; a truthiness check would have produced the
    entity-ID fallback above and passed both of these tests."""
    assert prefixes(at(tmp_path, BAD_LATITUDE, vehicle_id="")) == [
        "vehicle.id  has latitude/longitude of (1000.0,-82.4572)"
    ]


def test_the_occurrence_locates_the_vehicle_position_it_came_from(tmp_path):
    found = at(tmp_path, BAD_LATITUDE)

    assert found[0].context[ENTITY_PATH_KEY] == "entity[0].vehicle"


# --- the bounds, and one occurrence per position ----------------------------


@pytest.mark.parametrize("point", [(-90.0, -180.0), (90.0, 180.0), (0.0, 0.0)])
def test_the_world_bounds_are_inclusive(tmp_path, point):
    """Ours. `isPositionValid` compares against -90, 90, -180 and 180 with
    non-strict operators; `tests/test_shared_positions.py` ports upstream's own
    `testValidPosition` for the helper, and this is the rule reading it."""
    assert at(tmp_path, point) == []


@pytest.mark.parametrize("point", [(-91.0, 0.0), (91.0, 0.0), (0.0, -181.0), (0.0, 181.0)])
def test_a_coordinate_just_outside_the_world_reports(tmp_path, point):
    assert len(at(tmp_path, point)) == 1


def test_each_bad_position_is_reported_once_per_entity(tmp_path):
    found = run(
        tmp_path,
        entity(vehicle=vehicle(BAD_LATITUDE), entity_id="one"),
        entity(vehicle=vehicle(BAD_LONGITUDE, vehicle_id="2"), entity_id="two"),
    )

    assert [occurrence.prefix.split(" of ")[1] for occurrence in found] == [
        "(1000.0,-82.4572)",
        "(27.9506,-1000.0)",
    ]


# --- the branch the wire cannot reach ---------------------------------------


def test_a_position_without_a_latitude_never_reaches_a_rule(tmp_path):
    """Ours. `Position.latitude` and `.longitude` are `required` in the 2015
    schema and in the current one alike, so `isInitialized` fails and the whole
    parse sinks. That is why upstream's own test never exercises the "missing
    lat/long" branch, and why the jar skips such a file entirely."""
    with pytest.raises(DecodeError, match=r"required field Position\.latitude is not set"):
        decode(encode({"longitude": 1.0}, V2015, "Position"), V2015, "Position")


def test_the_missing_branch_is_ported_anyway(tmp_path):
    """Ours, and the only way to reach `:111`: the position is assembled
    directly rather than decoded, because no bytes can produce this state.
    Everything around it still came through the real encoder and decoder."""
    built = message(entity(vehicle=vehicle(USF_CAMPUS)))
    position = built.get("entity")[0].get("vehicle").get("position")
    position._values.pop("longitude")

    found = occurrences(check(built, context(tmp_path, minimal())))

    assert prefixes(found) == ["vehicle.id 1 position is missing lat/long"]


def test_the_missing_branch_wins_over_the_invalid_one(tmp_path):
    """Ours. `:109` is tested first, so a Position with an out-of-range
    latitude and no longitude reports the missing text, not the coordinates."""
    built = message(entity(vehicle=vehicle(BAD_LATITUDE)))
    position: Msg = built.get("entity")[0].get("vehicle").get("position")
    position._values.pop("longitude")

    found = occurrences(check(built, context(tmp_path, minimal())))

    assert prefixes(found) == ["vehicle.id 1 position is missing lat/long"]
