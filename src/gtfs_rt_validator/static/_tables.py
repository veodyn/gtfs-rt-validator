"""The row-reading half of `StaticContext`: one builder per GTFS table.

Split out of `context.py` at the 300-line file cap, and split here rather than
anywhere else because this is the only code in the project that knows GTFS
column names. `context.py` keeps the shape of the answer; this keeps the reading
of the feed. Every function below is a named block of `GtfsMetadata`'s
constructor and cites the lines it reproduces.

Nothing here raises on feed content. A feed that will not load has already
failed in `adapter.py`, and by this point every field these functions sort or
measure by is present and typed, so the sort keys and the coordinate reads are
safe. Both readers guarantee it and neither leans on the other: the strict path
marks a table with a missing required field UNPARSABLE_ROWS, and the compat path
refuses the four cells named in `onebusaway.REQUIRED` outright. Either way
`load_static` raises before a context is ever built.
"""

from __future__ import annotations

from typing import Any

from gtfs_rt_validator.geometry.bbox import REGION_BUFFER_DEGREES, Rectangle

# A loaded row. `Any` rather than `object` because the cell type is per column
# and known from the GTFS schema (`stop_lat` is a float, `stop_sequence` an int),
# so `object` would only buy a cast at every read. `adapter.py`'s docstring is
# the authority on which column carries which type.
Row = dict[str, Any]
Point = tuple[float, float]

# `shapePoints.size() > 3` (`GtfsMetadata.java:127`), written as a threshold so
# the comparison reads the way the Java does. Feed-wide, not per shape:
# `shapePoints` is `getAllShapePoints()`, so four points spread over four shapes
# is still four, and the gate stays shut.
SHAPE_POINT_GATE = 3


def timezone_of(agency: list[Row]) -> str | None:
    """`BatchProcessor.java:137-145`: the first agency read, then `break`.

    `getAllAgencies()` is insertion-ordered, so this is file order rather than
    sorted order, and duplicates never reach it because the reader drops an
    agency whose id it already holds. Zero agencies gives `None` here and an
    uncaught `NullPointerException` there, out of `TimeZone.getTimeZone(null)`,
    which kills the run and writes no results for any file in the archive.
    Whether `--compat` reproduces that silence is the runner's decision.
    """
    return agency[0]["agency_timezone"] if agency else None


def agency_id_of(row: Row) -> str:
    """The id trap: no `agency_id` means the id *is* the `agency_name`.

    Not a fallback invented here. `GtfsReader.EntityHandlerImpl.handleEntity`
    does it because `BatchProcessor` never calls `setDefaultAgencyId`, and an
    empty cell reaches this function as `None` exactly as it reaches Java as
    null. E034 compares realtime agency ids against the set this builds.
    """
    agency_id = row["agency_id"]
    return row["agency_name"] if agency_id is None else agency_id


def build_shapes(
    rows: list[Row], *, ignore_shapes: bool
) -> tuple[dict[str, list[Row]], Rectangle | None, Rectangle | None]:
    """`GtfsMetadata.java:124-150`, gate included.

    Below the gate this returns nothing at all, which is what leaves both boxes
    `null` upstream, disables E029 and flips E028 onto the stops box. The box is
    built over the points in file order, before the per-shape lists are sorted,
    because that is the order upstream feeds the multipoint builder; the answer
    does not depend on it, a bounding box being a min and a max.
    """
    if ignore_shapes or len(rows) <= SHAPE_POINT_GATE:
        return {}, None, None
    grouped: dict[str, list[Row]] = {}
    points: list[Point] = []
    for row in rows:
        grouped.setdefault(row["shape_id"], []).append(row)
        points.append((row["shape_pt_lon"], row["shape_pt_lat"]))
    box = Rectangle.from_points(points)
    for group in grouped.values():
        group.sort(key=lambda row: row["shape_pt_sequence"])
    return grouped, box, box.buffered(REGION_BUFFER_DEGREES)


def group_stop_times(rows: list[Row]) -> dict[str, list[Row]]:
    """`mTripStopTimes`, sorted by `stop_sequence`.

    Upstream sorts inside its trips loop, so a trip_id present in
    `stop_times.txt` and absent from `trips.txt` would go unsorted. It cannot
    reach that state, because its reader aborts the entire read on an
    unresolvable foreign key. The sibling at `35fac77` does not abort (measured
    in `tests/test_static_context.py`), so sorting every group here is both
    simpler and the only version that stays right on a feed upstream would have
    refused outright.
    """
    grouped: dict[str, list[Row]] = {}
    for row in rows:
        grouped.setdefault(row["trip_id"], []).append(row)
    for group in grouped.values():
        group.sort(key=lambda row: row["stop_sequence"])
    return grouped


def build_trips(
    rows: list[Row], shape_points: dict[str, list[Row]]
) -> tuple[dict[str, Row], dict[str, list[Point]]]:
    """`GtfsMetadata.java:166-189`: the trip map, and a polyline per trip.

    A trip gets a shape only when its `shape_id` is set and names a shape that
    survived the gate. Upstream's test is hibernate's `isEmpty`, which is null or
    zero-length, and the sibling's loader maps an empty cell to `None`, so the
    two agree. Points are `(lon, lat)`, matching `pointXY(p.getLon(), p.getLat())`
    and every other coordinate pair in this project.
    """
    trips: dict[str, Row] = {}
    trip_shapes: dict[str, list[Point]] = {}
    for row in rows:
        trip_id = row["trip_id"]
        trips[trip_id] = row
        shape_id = row["shape_id"]
        if shape_id is None:
            continue
        points = shape_points.get(shape_id)
        if points is not None:
            trip_shapes[trip_id] = [(p["shape_pt_lon"], p["shape_pt_lat"]) for p in points]
    return trips, trip_shapes


def build_stops(rows: list[Row]) -> tuple[frozenset[str], dict[str, int], Rectangle]:
    """`GtfsMetadata.java:219-232`: ids, location types, and the stops box.

    A stop joins the box only when both coordinates are set (`isLonSet() &&
    isLatSet()`), so one of the two is not enough. `location_type` is a
    primitive `int` in onebusaway, defaulting to 0, so an absent cell is 0 and
    the map can never hold `None` however much its comment upstream says it can.

    A feed where no stop has both coordinates yields an all-NaN rectangle that
    is DISJOINT from every point and raises nothing, so E028 fires for every
    vehicle position. That is measured, and `geometry/bbox.py` reproduces it.
    """
    stop_ids: set[str] = set()
    location_types: dict[str, int] = {}
    points: list[Point] = []
    for row in rows:
        stop_id = row["stop_id"]
        stop_ids.add(stop_id)
        location_type = row["location_type"]
        location_types[stop_id] = 0 if location_type is None else location_type
        lat, lon = row["stop_lat"], row["stop_lon"]
        if lat is not None and lon is not None:
            points.append((lon, lat))
    return frozenset(stop_ids), location_types, Rectangle.from_points(points)


def split_frequencies(rows: list[Row]) -> tuple[frozenset[str], dict[str, list[Row]]]:
    """`GtfsMetadata.java:238-252`. `exact_times` is a primitive too, so blank is 0.

    Anything other than 0 or 1 falls through both branches and is dropped, which
    is upstream's `if / else if` with no `else`.
    """
    zero: set[str] = set()
    one: dict[str, list[Row]] = {}
    for row in rows:
        trip_id = row["trip_id"]
        exact_times = row["exact_times"]
        exact_times = 0 if exact_times is None else exact_times
        if exact_times == 0:
            zero.add(trip_id)
        elif exact_times == 1:
            one.setdefault(trip_id, []).append(row)
    return frozenset(zero), one


def build_route_stop_ids(
    trips: dict[str, Row], trip_stop_times: dict[str, list[Row]]
) -> dict[str, frozenset[str]]:
    """Every `stop_id` some trip of a route serves. **No table is read for this.**

    The one member of `StaticContext` with no `GtfsMetadata` counterpart, because
    none of upstream's 56 rules asks a route which stops it serves and P012 does.
    Both arguments are already built by the time this runs: `trips` came from
    `trips.txt` and `trip_stop_times` from `stop_times.txt`, two of the seven
    `adapter.SEVEN_TABLES`. So "the exact set a realtime run reads" stays seven,
    and `tests/test_static_route_stop_ids.py` asserts that rather than trusting
    this sentence.

    A route whose trips visit nothing is absent rather than mapped to an empty
    frozenset, which is `repeated_stops`'s convention above and is load bearing
    here: P012 fires when an alert names every stop of a route, and every alert
    names every stop of the empty set.

    The walk is over `trips`, so a `stop_times.txt` row naming a trip no
    `trips.txt` row declares reaches no route. `group_stop_times` keeps it,
    because the sibling does not reject it, but it belongs to no route.
    """
    out: dict[str, set[str]] = {}
    for trip_id, row in trips.items():
        stop_times = trip_stop_times.get(trip_id)
        if not stop_times:
            continue
        out.setdefault(row["route_id"], set()).update(stop["stop_id"] for stop in stop_times)
    return {route_id: frozenset(stop_ids) for route_id, stop_ids in out.items()}


def repeated_stops(trip_stop_times: dict[str, list[Row]]) -> dict[str, list[str]]:
    """`GtfsMetadata.java:196-213`: every *repeat* visit, in stop_sequence order.

    A stop visited three times contributes two entries. The key is inserted only
    when the list is non-empty, so a trip that visits nothing twice is absent
    from the map rather than mapped to `[]`, and `containsKey` and `get` answer
    consistently.
    """
    out: dict[str, list[str]] = {}
    for trip_id, rows in trip_stop_times.items():
        seen: set[str] = set()
        duplicates: list[str] = []
        for row in rows:
            stop_id = row["stop_id"]
            if stop_id in seen:
                duplicates.append(stop_id)
            seen.add(stop_id)
        if duplicates:
            out[trip_id] = duplicates
    return out
