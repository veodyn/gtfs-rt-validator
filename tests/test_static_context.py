"""`StaticContext`'s tabular members, against what upstream's `GtfsMetadata` holds.

Every expectation here was read off `GtfsMetadata.java` at the pin, not from
what a GTFS reader ought to do. Three
of them would look like bugs to anyone who had not read the Java: an agency with
no `agency_id` is keyed by its *name*, `stop_location_types` can never hold
`None`, and the timezone is whichever `agency.txt` row came first in the file
rather than the one a sorted or deduplicated pass would pick.

The geometry members, the shapes gate and the buffered-shape accessor live in
`tests/test_static_context_geometry.py`; `-ignoreShapes` lives in
`tests/test_ignore_shapes.py`. The split is by concern and was forced by the
300-line file cap.
"""

from __future__ import annotations

from dataclasses import fields
from pathlib import Path

from gtfs_rt_validator.static.adapter import load_static
from gtfs_rt_validator.static.context import StaticContext
from gtfsfixtures import build_feed, minimal_tables

AGENCY_COLUMNS = ["agency_id", "agency_name", "agency_url", "agency_timezone"]


def context_from(tmp_path: Path, tables, *, ignore_shapes: bool = False, columns=None):
    """Build the feed, load it through the adapter, and build the context."""
    path = build_feed(tmp_path, tables, columns=columns)
    raw = load_static(path, ignore_shapes=ignore_shapes)
    return StaticContext.build(raw, ignore_shapes=ignore_shapes)


def trip(trip_id: str) -> dict[str, object]:
    return {"trip_id": trip_id, "route_id": "R1", "service_id": "SVC1", "direction_id": "0"}


def stop_time(trip_id: str, stop_id: str, sequence: str) -> dict[str, object]:
    return {
        "trip_id": trip_id,
        "arrival_time": "07:00:00",
        "departure_time": "07:00:00",
        "stop_id": stop_id,
        "stop_sequence": sequence,
    }


def frequency(trip_id: str, exact_times: str | None, headway: str = "900") -> dict[str, object]:
    return {
        "trip_id": trip_id,
        "start_time": "06:00:00",
        "end_time": "10:00:00",
        "headway_secs": headway,
        "exact_times": exact_times,
    }


def test_the_members_are_gtfs_metadatas_load_bearing_fields_and_three_of_our_own():
    """16 fields plus the memoised accessor. `mFeedUrl` is deliberately absent.

    Upstream has 18 fields; the 18th is log-only, has no getter, and nothing
    reads it. `mTripShapesBuffered` is a lazily-filled cache rather than a
    built value, so it is the accessor here and not a field.

    The last three translate nothing and are ours. `route_stop_ids` is a
    route-to-stops map upstream has no counterpart for, because none of its 56
    rules wants one; `tests/test_static_route_stop_ids.py` owns it. `shape_ids`
    is `shapes.txt`'s id column read *before* `GtfsMetadata.java:127`'s
    feed-wide point gate, which S038 needs and which `shape_points` cannot
    answer for a feed of three points or fewer. `shapes_withheld` is the only
    one that is not feed content: it says `-ignoreShapes` kept the table from
    being read, which is what separates an empty `shape_ids` that means "no
    shape ids exist" from one that means "nobody looked", and S016 and S044
    return early on it. `tests/test_ignore_shapes.py` owns that distinction.
    All three are last so that the 16 above still read as `GtfsMetadata`'s own
    list, in its order.
    """
    public = tuple(f.name for f in fields(StaticContext) if not f.name.startswith("_"))

    assert public == (
        "timezone",
        "agency_ids",
        "route_ids",
        "stop_ids",
        "trips",
        "trip_stop_times",
        "exact_times_zero_trip_ids",
        "exact_times_one_trips",
        "shape_points",
        "trip_shapes",
        "stop_bounding_box",
        "stop_bounding_box_buffered",
        "shape_bounding_box",
        "shape_bounding_box_buffered",
        "stop_location_types",
        "trips_with_multi_stops",
        "route_stop_ids",
        "shape_ids",
        "shapes_withheld",
    )
    assert callable(StaticContext.buffered_trip_shape)
    assert "mFeedUrl" not in public and "feed_url" not in public


def test_the_simple_id_sets_are_what_they_say(tmp_path):
    ctx = context_from(tmp_path, minimal_tables())

    assert ctx.agency_ids == frozenset({"A1"})
    assert ctx.route_ids == frozenset({"R1"})
    assert ctx.stop_ids == frozenset({"S1", "S2"})
    assert set(ctx.trips) == {"T1"}
    assert ctx.trips["T1"]["route_id"] == "R1", "the value is the raw trips.txt row"


def test_timezone_is_the_first_agency_row_in_file_order(tmp_path):
    """Not sorted, not deduplicated: `BatchProcessor` takes the first and breaks.

    `getAllAgencies()` is insertion-ordered, so it is the first row *read*. The
    two rows below are deliberately out of alphabetical order by both id and
    name, so a sorted pass would pick the other one.
    """
    tables = minimal_tables()
    tables["agency.txt"] = [
        {
            "agency_id": "Z9",
            "agency_name": "Zebra Transit",
            "agency_url": "https://example.com/z",
            "agency_timezone": "America/Denver",
        },
        {
            "agency_id": "A1",
            "agency_name": "Alpha Transit",
            "agency_url": "https://example.com/a",
            "agency_timezone": "America/New_York",
        },
    ]

    ctx = context_from(tmp_path, tables)

    assert ctx.timezone == "America/Denver"
    assert ctx.agency_ids == frozenset({"Z9", "A1"})


def test_zero_agencies_leaves_the_timezone_none(tmp_path):
    """The context reports `None` and decides nothing else.

    Upstream calls `TimeZone.getTimeZone(null)`, which throws an uncaught NPE on
    JDK 17 (measured). `Main.java:71` catches only `IOException` and
    `NoSuchAlgorithmException`, so the jar dies with a stack trace and writes no
    `.results.json` for *any* file in the archive.

    So under `--compat` a feed with zero agency rows must produce no output at
    all, for every file, because that is what the jar produces, and modern mode
    substitutes UTC and records the substitution. Neither decision belongs here:
    both are made once in `runner/gate.py`.
    """
    tables = minimal_tables()
    tables["agency.txt"] = []

    ctx = context_from(tmp_path, tables, columns={"agency.txt": AGENCY_COLUMNS})

    assert ctx.timezone is None
    assert ctx.agency_ids == frozenset()
    assert ctx.stop_ids == frozenset({"S1", "S2"}), "everything else still builds"


def test_agency_ids_hold_the_agency_name_when_agency_id_is_absent(tmp_path):
    """The id trap E034 depends on, and it is onebusaway's, not upstream's.

    `BatchProcessor` never calls `setDefaultAgencyId`, so `_defaultAgencyId` is
    null, and `GtfsReader.EntityHandlerImpl.handleEntity` runs
    `agency.setId(agency.getName())` for every agency row whose `agency_id` is
    null (onebusaway-gtfs 1.3.87, `GtfsReader.java:221-228`). An empty cell and
    an absent column both arrive here as `None` from the sibling's loader, so
    both take that branch, as they do in Java.
    """
    tables = minimal_tables()
    tables["agency.txt"][0]["agency_id"] = None

    ctx = context_from(tmp_path, tables)

    assert ctx.agency_ids == frozenset({"Test Transit"}), "the name, not the id"
    assert ctx.timezone == "America/New_York"


def test_trip_stop_times_are_sorted_by_stop_sequence(tmp_path):
    """`stop_times.txt` is not required to be sorted, and upstream sorts it.

    Written out of order on purpose. `stop_sequence` reaches this point as an
    `int` and can never be `None`: it is a required field, and the sibling marks
    a table with a missing required field UNPARSABLE_ROWS, which `load_static`
    turns into a `StaticLoadError` before the context is ever built (measured).
    """
    tables = minimal_tables()
    rows = tables["stop_times.txt"]
    rows[0]["stop_sequence"] = "7"
    rows[1]["stop_sequence"] = "3"

    ctx = context_from(tmp_path, tables)

    assert [stop.stop_sequence for stop in ctx.trip_stop_times["T1"]] == [3, 7]
    assert [stop.stop_id for stop in ctx.trip_stop_times["T1"]] == ["S2", "S1"]


def test_trip_stop_times_holds_no_trip_absent_from_trips(tmp_path):
    """Upstream's invariant, pinned so a loader change cannot quietly break it.

    `CsvEntityReader` aborts the whole read on an unresolvable foreign key
    (`EntityReferenceNotFoundException`), so upstream's `mTripStopTimes` cannot
    contain a trip_id that `trips.txt` does not declare.
    """
    tables = minimal_tables()
    tables["trips.txt"].append(trip("T2"))
    tables["stop_times.txt"].append(stop_time("T2", "S1", "1"))

    ctx = context_from(tmp_path, tables)

    assert set(ctx.trip_stop_times) <= set(ctx.trips)
    assert set(ctx.trip_stop_times) == {"T1", "T2"}


def test_the_sibling_does_not_enforce_that_invariant_and_upstream_does(tmp_path):
    """MEASURED DIVERGENCE, and it is the loader's, not this module's.

    Upstream's `trip_stop_times` can never hold a trip absent from `trips.txt`,
    because its reader aborts the entire read on a dangling foreign key. That is
    not true of the sibling at `35fac77`, which loads the row and reports no
    system error: measured here, on this feed.

    `StaticContext` groups what it is given, exactly as `GtfsMetadata` does, so
    the orphan survives into `trip_stop_times`. Filtering it out here would hide
    a real difference between the two readers behind a silent repair. The shape
    of the answer is the same as the agency-less NPE above: under `--compat` this
    feed must produce no output at all, and that refusal is made once in
    `runner/gate.py` rather than in any rule.
    """
    tables = minimal_tables()
    tables["stop_times.txt"].append(stop_time("GHOST", "S1", "1"))

    ctx = context_from(tmp_path, tables)

    assert "GHOST" in ctx.trip_stop_times
    assert "GHOST" not in ctx.trips


def test_stop_location_types_can_never_hold_none(tmp_path):
    """`Stop.locationType` is a primitive `int` defaulting to 0 in onebusaway.

    So the `locationType != null` guards in `StopValidator` only ever fire for a
    stop_id absent from the map entirely, never for a present one. A stop whose
    `location_type` cell is empty reaches this map as 0, not as `None`.
    """
    tables = minimal_tables()
    tables["stops.txt"][0]["location_type"] = None
    tables["stops.txt"][1]["location_type"] = "1"

    ctx = context_from(tmp_path, tables)

    assert ctx.stop_location_types == {"S1": 0, "S2": 1}
    assert all(type(value) is int for value in ctx.stop_location_types.values())


def test_trips_with_multi_stops_holds_a_key_only_when_the_list_is_non_empty(tmp_path):
    """`mTripsWithMultiStops.put` sits inside `if (!duplicateStopIds.isEmpty())`.

    The value is every *repeat* visit in stop_sequence order, so a stop visited
    three times appears twice. T1 below visits S1 at sequences 1 and 3; T2 never
    repeats and so is absent from the map rather than mapped to an empty list.
    """
    tables = minimal_tables()
    tables["trips.txt"].append(trip("T2"))
    tables["stop_times.txt"] = [
        stop_time("T1", "S1", "3"),
        stop_time("T1", "S1", "1"),
        stop_time("T1", "S2", "2"),
        stop_time("T2", "S1", "1"),
        stop_time("T2", "S2", "2"),
    ]

    ctx = context_from(tmp_path, tables)

    assert ctx.trips_with_multi_stops == {"T1": ["S1"]}
    assert "T2" not in ctx.trips_with_multi_stops


def test_frequencies_split_by_exact_times(tmp_path):
    """`exact_times` is a primitive `int` too, so an empty cell is 0, not absent."""
    tables = minimal_tables()
    tables["trips.txt"] += [trip("T2"), trip("T3")]
    tables["frequencies.txt"] += [frequency("T2", "0"), frequency("T3", None)]

    ctx = context_from(tmp_path, tables)

    assert ctx.exact_times_zero_trip_ids == frozenset({"T2", "T3"})
    assert set(ctx.exact_times_one_trips) == {"T1"}
    assert [row["headway_secs"] for row in ctx.exact_times_one_trips["T1"]] == [600]
