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
) -> tuple[dict[str, tuple[Point, ...]], Rectangle | None, Rectangle | None]:
    """`GtfsMetadata.java:124-150`, gate included.

    Below the gate this returns nothing at all, which is what leaves both boxes
    `null` upstream, disables E029 and flips E028 onto the stops box. The box is
    built over the points in file order, before the per-shape lists are sorted,
    because that is the order upstream feeds the multipoint builder; the answer
    does not depend on it, a bounding box being a min and a max.

    **Coordinate pairs rather than the loaded rows.** Once a shape is sorted and
    the box is built, the only thing anything asks of it is its geometry: no rule
    reads `shape_points` at all, and the two that want a polyline want
    `(lon, lat)`. Holding the rows instead cost 163 MB of a real feed for 393,779
    of them. Sorting still happens on the rows, because `shape_pt_sequence` is
    what orders them and it is not one of the two values kept.
    """
    if ignore_shapes or len(rows) <= SHAPE_POINT_GATE:
        return {}, None, None
    grouped: dict[str, list[Row]] = {}
    points: list[Point] = []
    for row in rows:
        grouped.setdefault(row["shape_id"], []).append(row)
        points.append((row["shape_pt_lon"], row["shape_pt_lat"]))
    box = Rectangle.from_points(points)
    polylines = {
        shape_id: tuple(
            (row["shape_pt_lon"], row["shape_pt_lat"])
            for row in sorted(group, key=lambda row: row["shape_pt_sequence"])
        )
        for shape_id, group in grouped.items()
    }
    return polylines, box, box.buffered(REGION_BUFFER_DEGREES)


def build_trips(
    rows: list[Row], shape_points: dict[str, tuple[Point, ...]]
) -> tuple[dict[str, Row], dict[str, tuple[Point, ...]]]:
    """`GtfsMetadata.java:166-189`: the trip map, and a polyline per trip.

    A trip gets a shape only when its `shape_id` is set and names a shape that
    survived the gate. Upstream's test is hibernate's `isEmpty`, which is null or
    zero-length, and the sibling's loader maps an empty cell to `None`, so the
    two agree. Points are `(lon, lat)`, matching `pointXY(p.getLon(), p.getLat())`
    and every other coordinate pair in this project.

    **A trip does not get a polyline of its own; it gets the shape's**, where
    upstream builds one per trip inside its loop. Trips outnumber shapes heavily
    on a real feed: 92,360 against 1,157 on the MBTA's archive, so converting per
    trip held 25,737,031 point tuples for 393,779 points on disk, 1.75 GB of the
    3.55 GB a prepared feed retained then. Identical values cannot reach output
    differently, so the sharing is invisible to every rule and every report.

    Since `build_shapes` now returns polylines rather than rows, `trip_shapes`
    is a second set of references to the very tuples `shape_points` already
    holds, and costs a dict rather than any geometry at all. Those tuples being
    immutable is what makes that safe: `PreparedFeed.static` reaches a caller and
    may outlive hundreds of runs, and one shared list would have turned a stray
    `append` into a change to every trip on that shape.
    """
    trips: dict[str, Row] = {}
    trip_shapes: dict[str, tuple[Point, ...]] = {}
    for row in rows:
        trip_id = row["trip_id"]
        trips[trip_id] = row
        shape_id = row["shape_id"]
        if shape_id is None:
            continue
        polyline = shape_points.get(shape_id)
        if polyline is not None:
            trip_shapes[trip_id] = polyline
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
