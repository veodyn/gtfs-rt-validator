"""E006, against upstream's own `FrequencyTypeZeroValidatorTest` and the text it never asserts.

Every assertion marked "upstream" is transcribed from the real
`FrequencyTypeZeroValidatorTest.java` in the checkout at `jar-build/upstream/`
(`testE006`, lines 35-100), not from a second-hand summary of it. Upstream
asserts *counts* only, so every assertion about occurrence text below is ours.
Ours does not mean guessed: each prefix here was produced by running the pinned
jar over a crafted feed against upstream's own `bullrunner-gtfs.zip`, so the
double space in `"vehicle_id  trip_id 1"` is a byte the jar wrote and not a
reading of `FrequencyTypeZeroValidator.java:91`.

The static feed mirrors `bullrunner-gtfs.zip`, whose `frequencies.txt` gives
trip `1` `exact_times = 0`. Upstream builds one FeedEntity carrying both a
TripUpdate and a VehiclePosition, with `id = "TEST_ENTITY"` from
`FeedMessageTest`, and this ports that shape: the single entity is what makes
the TripUpdate-before-VehiclePosition order observable.

Messages go through the real encoder and decoder, so a field name the 2015
schema does not have fails here rather than reading as an absent default.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Mapping, Sequence
from pathlib import Path

from gtfs_rt_validator.rules.upstream.e006 import check
from gtfsfixtures import minimal_tables
from rulefixtures import context, entity, message, prefixes, trip_rows

#: `bullrunner-gtfs.zip`'s first frequency row, which is what makes trip `1` the
#: exact_times = 0 trip upstream's own test uses.
BULL_RUNNER_TRIP = "1"

#: Upstream's `tripDescriptorBuilder`, whose two values are deliberately
#: malformed: E006 does not validate either format, E021 and E020 do.
START_DATE = "4-24-2016"
START_TIME = "08:00:00AM"


def tables(exact_times: str = "0") -> dict[str, list[dict[str, object]]]:
    """`minimal_tables` with bullrunner's exact_times = 0 trip in it.

    The whole of `frequencies.txt` is replaced rather than appended to, because
    the fixture's own row is an exact_times = 1 row for another trip and this
    rule reads only the zero set.
    """
    built = minimal_tables()
    built["trips.txt"] += trip_rows({BULL_RUNNER_TRIP: "R1"})
    built["frequencies.txt"] = [
        {
            "trip_id": BULL_RUNNER_TRIP,
            "start_time": "07:00:00",
            "end_time": "24:00:00",
            "headway_secs": "600",
            "exact_times": exact_times,
        }
    ]
    return built


def trip(trip_id: str = BULL_RUNNER_TRIP, **fields: object) -> dict[str, object]:
    return {"trip_id": trip_id, **fields}


def half(trip_descriptor: Mapping[str, object], vehicle_id: str | None = "vehicle_A") -> dict:
    """A TripUpdate or a VehiclePosition body: they share both fields E006 reads."""
    built: dict[str, object] = {"trip": dict(trip_descriptor)}
    if vehicle_id is not None:
        built["vehicle"] = {"id": vehicle_id}
    return built


def run(tmp_path: Path, *entities: Mapping[str, object], exact_times: str = "0") -> Sequence:
    return list(check(message(*entities), context(tmp_path, tables(exact_times))))


def both_halves(
    trip_descriptor: Mapping[str, object], vehicle_id: str | None = "vehicle_A"
) -> dict[str, object]:
    """Upstream's own entity: one TripUpdate and one VehiclePosition on one entity."""
    return entity(half(trip_descriptor, vehicle_id), half(trip_descriptor, vehicle_id))


# --- upstream's own case, stage by stage ------------------------------------


def test_a_trip_with_neither_start_date_nor_start_time_reports_four_times(tmp_path):
    """Upstream, testE006: `expected.put(E006, 4)`. Two independent tests per
    half, so a trip missing both fields reports twice on each side."""
    found = run(tmp_path, both_halves(trip()))

    assert len(found) == 4


def test_adding_start_date_leaves_two(tmp_path):
    """Upstream, testE006: `expected.put(E006, 2)`, with `4-24-2016`, which is
    not a valid GTFS date. E006 checks presence; E021 checks the format."""
    found = run(tmp_path, both_halves(trip(start_date=START_DATE)))

    assert len(found) == 2


def test_adding_start_time_too_leaves_none(tmp_path):
    """Upstream, testE006: `expected.clear()`, with `08:00:00AM`, which is not a
    valid GTFS time either. E020 checks that format."""
    found = run(tmp_path, both_halves(trip(start_date=START_DATE, start_time=START_TIME)))

    assert found == []


# --- the occurrence text, which upstream's test never looks at --------------


def test_every_occurrence_carries_this_rules_id(tmp_path):
    found = run(tmp_path, both_halves(trip()))

    assert {occurrence.rule_id for occurrence in found} == {"E006"}


def test_the_four_prefixes_are_the_ones_the_jar_writes(tmp_path):
    """Ours, measured: the pinned jar over this feed wrote exactly these four,
    in this order. start_date before start_time within a half, TripUpdate
    before VehiclePosition within an entity."""
    found = run(tmp_path, both_halves(trip()))

    assert prefixes(found) == [
        "trip_id 1 is missing start_date",
        "trip_id 1 is missing start_time",
        "vehicle_id vehicle_A trip_id 1 is missing start_date",
        "vehicle_id vehicle_A trip_id 1 is missing start_time",
    ]


def test_a_vehicle_position_with_no_vehicle_id_leaves_a_double_space(tmp_path):
    """Ours, measured. `vehiclePosition.getVehicle().getId()` is read with no
    guard at `:91`, so an absent VehicleDescriptor interpolates as the empty
    string and the two literals collide."""
    found = run(tmp_path, entity(vehicle=half(trip(), vehicle_id=None)))

    assert prefixes(found) == [
        "vehicle_id  trip_id 1 is missing start_date",
        "vehicle_id  trip_id 1 is missing start_time",
    ]


def test_only_the_missing_field_is_reported(tmp_path):
    """Ours. The two conditions are independent `if`s, not an if/else."""
    found = run(tmp_path, entity(half(trip(start_date=START_DATE))))

    assert prefixes(found) == ["trip_id 1 is missing start_time"]


# --- gating, and the asymmetry between the two halves -----------------------


def test_a_trip_that_is_not_exact_times_zero_is_not_checked(tmp_path):
    """Ours, measured: the same feed with `exact_times = 1` produced no results
    for this rule at all. The gate is membership of the zero set, nothing else."""
    found = run(tmp_path, both_halves(trip()), exact_times="1")

    assert found == []


def test_entities_are_reported_in_feed_order_halves_interleaved(tmp_path):
    """Ours, measured: with two entities the jar wrote entity one's TripUpdate
    and VehiclePosition before entity two's, not all TripUpdates first."""
    found = run(
        tmp_path,
        entity(half(trip()), half(trip()), entity_id="one"),
        entity(half(trip()), half(trip()), entity_id="two"),
    )

    assert (
        prefixes(found)
        == [
            "trip_id 1 is missing start_date",
            "trip_id 1 is missing start_time",
            "vehicle_id vehicle_A trip_id 1 is missing start_date",
            "vehicle_id vehicle_A trip_id 1 is missing start_time",
        ]
        * 2
    )


def test_a_trip_descriptor_with_no_trip_id_is_looked_up_as_the_empty_string(tmp_path):
    """Ours, and the asymmetry between the two halves is deliberate.

    The TripUpdate half (`:55`) has no `hasTrip()` or `hasTripId()` guard, so an
    absent trip_id looks `""` up in the zero set; the VehiclePosition half
    (`:83-84`) guards on `hasTrip()` and never gets that far. No archive can
    hold a frequencies row whose trip_id is the empty string, so the static
    context is edited directly here: this is the one case the jar cannot be
    made to show, and it is why the two halves are written differently.

    `TripUpdate.trip` is required at both pins, so the TripUpdate keeps an empty
    TripDescriptor rather than dropping it; a TripUpdate with no `trip` at all
    fails `isInitialized` and the jar skips the file (measured).
    """
    ctx = context(tmp_path, tables())
    ctx = dataclasses.replace(
        ctx, static=dataclasses.replace(ctx.static, exact_times_zero_trip_ids=frozenset({""}))
    )
    feed = message(entity({"trip": {}}, {}))

    found = list(check(feed, ctx))

    assert prefixes(found) == ["trip_id  is missing start_date", "trip_id  is missing start_time"]
