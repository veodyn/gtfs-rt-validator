"""W005, against upstream's own `FrequencyTypeZeroValidatorTest` and two missing spaces.

Assertions marked "upstream" are transcribed from the real
`FrequencyTypeZeroValidatorTest.java` in the checkout at `jar-build/upstream/`
(`testW005`, lines 207-264). Upstream asserts counts only, so the occurrence
text is ours, measured by running the pinned jar over a crafted feed against
upstream's own `bullrunner-gtfs.zip`.

**The VehiclePosition prefix is missing two spaces**, both of them in the Java
source at `:107` (`"entity ID" + entity.getId() + "with trip_id "`), and the jar
duly wrote `entity IDTEST_ENTITYwith trip_id 1`. Reproduced rather than
corrected: under `--compat` the bytes are the contract.

The two halves also ask different questions. The TripUpdate half tests
`!hasVehicle() || !getVehicle().hasId()`; the VehiclePosition half tests only
`!getVehicle().hasId()`, which the default instance answers false for anyway.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path

from gtfs_rt_validator.rules.upstream.w005 import check
from gtfsfixtures import minimal_tables
from rulefixtures import ENTITY_ID, context, entity, message, prefixes, trip_rows

BULL_RUNNER_TRIP = "1"

START_DATE = "4-24-2016"
START_TIME = "08:00:00AM"


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


def trip() -> dict[str, object]:
    """Upstream's descriptor, valid enough that only W005 can fire."""
    return {"trip_id": BULL_RUNNER_TRIP, "start_date": START_DATE, "start_time": START_TIME}


def half(vehicle: Mapping[str, object] | None) -> dict[str, object]:
    """A TripUpdate or VehiclePosition body. `None` omits the VehicleDescriptor
    entirely; `{}` is upstream's own case, a descriptor that carries no id."""
    built: dict[str, object] = {"trip": trip()}
    if vehicle is not None:
        built["vehicle"] = dict(vehicle)
    return built


def run(tmp_path: Path, *entities: Mapping[str, object]) -> Sequence:
    return list(check(message(*entities), context(tmp_path, tables())))


# --- upstream's own case, stage by stage ------------------------------------


def test_neither_half_carrying_a_vehicle_id_reports_twice(tmp_path):
    """Upstream, testW005: `expected.put(W005, 2)`. Its `vehicleDescriptorBuilder`
    is built with no id set, so both halves carry an empty VehicleDescriptor."""
    found = run(tmp_path, entity(half({}), half({})))

    assert len(found) == 2


def test_a_vehicle_id_on_the_vehicle_position_leaves_one(tmp_path):
    """Upstream, testW005: `expected.put(W005, 1)`, the TripUpdate's."""
    found = run(tmp_path, entity(half({}), half({"id": "1"})))

    assert len(found) == 1


def test_a_vehicle_id_on_both_halves_reports_nothing(tmp_path):
    """Upstream, testW005: `expected.clear()`."""
    found = run(tmp_path, entity(half({"id": "1"}), half({"id": "1"})))

    assert found == []


# --- the occurrence text, which upstream's test never looks at --------------


def test_the_two_prefixes_are_the_ones_the_jar_writes(tmp_path):
    """Ours, measured, and the VehiclePosition one is missing two spaces."""
    found = run(tmp_path, entity(half({}), half({})))

    assert prefixes(found) == ["trip_id 1", f"entity ID{ENTITY_ID}with trip_id 1"]
    assert {occurrence.rule_id for occurrence in found} == {"W005"}


def test_the_vehicle_position_prefix_names_the_feed_entity(tmp_path):
    """Ours. `entity.getId()` is the FeedEntity's own id, so it moves with the
    entity while the TripUpdate's prefix does not mention one at all."""
    found = run(tmp_path, entity(vehicle=half({}), entity_id="VP_1"))

    assert prefixes(found) == ["entity IDVP_1with trip_id 1"]


# --- the two halves ask different questions ---------------------------------


def test_a_trip_update_with_no_vehicle_descriptor_at_all_reports(tmp_path):
    """Ours: the `!tripUpdate.hasVehicle()` half of `:74`."""
    found = run(tmp_path, entity(half(None)))

    assert prefixes(found) == ["trip_id 1"]


def test_a_vehicle_position_with_no_vehicle_descriptor_at_all_reports(tmp_path):
    """Ours: `:105` has no `hasVehicle()` half, but `getVehicle()` returns the
    default instance and `hasId()` on that is false, so it reports anyway."""
    found = run(tmp_path, entity(vehicle=half(None)))

    assert prefixes(found) == [f"entity ID{ENTITY_ID}with trip_id 1"]


def test_a_descriptor_carrying_something_other_than_an_id_still_reports(tmp_path):
    """Ours. The test is `hasId()`, not "has a descriptor"."""
    found = run(tmp_path, entity(half({"label": "bus"}), half({"label": "bus"})))

    assert prefixes(found) == ["trip_id 1", f"entity ID{ENTITY_ID}with trip_id 1"]


# --- gating and order -------------------------------------------------------


def test_a_trip_that_is_not_exact_times_zero_is_not_checked(tmp_path):
    """Ours. Upstream's own comment at `:56-58` says missing trip_ids are W006's
    problem; a trip outside the zero set is nobody's problem here."""
    other = {"trip": {"trip_id": "T1"}}
    found = run(tmp_path, entity(other, other))

    assert found == []


def test_entities_are_reported_in_feed_order_halves_interleaved(tmp_path):
    """Ours, measured for E006 on the same validator: one pass over entities,
    TripUpdate then VehiclePosition within each."""
    found = run(
        tmp_path,
        entity(half({}), half({}), entity_id="one"),
        entity(half({}), half({}), entity_id="two"),
    )

    assert prefixes(found) == [
        "trip_id 1",
        "entity IDonewith trip_id 1",
        "trip_id 1",
        "entity IDtwowith trip_id 1",
    ]
