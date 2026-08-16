"""The static feed as every rule will read it: upstream's `GtfsMetadata`, in Python.

Built once per run from a `RawTables`, then read by everything. It holds the 17
load-bearing members of `validation/GtfsMetadata.java` at
`7041fa3fcaf674bf730e17325c179d329cdff6f2`. The 18th, `mFeedUrl`, is absent on
purpose: it has no getter and appears only in log strings, so nothing can depend
on it.

Nothing here decides anything. It groups, sorts and buffers, and it never raises
on feed content: a feed that will not load has already failed in `adapter.py`,
and everything past that point is data. Four behaviours would look like bugs to
anyone who had not read the Java, and all four are deliberate:

1. **The shapes gate is feed-wide.** `shapePoints != null && !ignoreShapes &&
   shapePoints.size() > 3` (`GtfsMetadata.java:127`), where `shapePoints` is
   `getAllShapePoints()`, so four points spread over four shapes is still four.
   Below the gate there is no shape data at all: E029 is disabled and E028 falls
   back to the stops box, with its occurrence text changing to match. That
   collapse is parity and stays. The two ungated members below it, `shape_ids`
   and `shapes_withheld`, exist so a modern rule can ask which ids the feed
   declares without asking which geometry survived; no rule under
   `rules/upstream/` may read either.
2. **An agency with no `agency_id` is keyed by its name.** `BatchProcessor`
   never calls `setDefaultAgencyId`, so onebusaway's reader runs
   `agency.setId(agency.getName())` (`GtfsReader.java:221-228`). E034 therefore
   matches vehicle agency ids against agency *names* on such a feed.
3. **A box over no points is all-NaN, and DISJOINT from everything.** It does
   not raise, so E028 fires for every vehicle position on a feed whose stops
   have no coordinates. `geometry/bbox.py` reproduces that.
4. **`stop_location_types` can never hold `None`.** `Stop.locationType` is a
   primitive `int` defaulting to 0, contrary to the comment on the field in
   upstream's own source, so the `locationType != null` guards in `StopValidator`
   only ever fire for a stop_id missing from the map entirely.

Buffered trip shapes are an accessor rather than a field, because upstream fills
`mTripShapesBuffered` lazily in `getBufferedTripShape` and that
`ConcurrentHashMap` lives as long as the metadata: it persists across every file
of an archive replay. That lifetime is observable in wall clock, never in output
bytes.

The per-table reading lives in `_tables.py`, split off at the file cap; what is
left here is the shape of the answer. Stdlib plus this project only, and
`adapter.py` is the sole module allowed to import the sibling.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from gtfs_rt_validator.geometry.bbox import (
    REGION_BUFFER_DEGREES,
    TRIP_BUFFER_DEGREES,
    TRIP_BUFFER_METERS,
    Rectangle,
)
from gtfs_rt_validator.geometry.buffer import within_buffered_shape
from gtfs_rt_validator.static._tables import (
    Point,
    Row,
    agency_id_of,
    build_route_stop_ids,
    build_shapes,
    build_stops,
    build_trips,
    group_stop_times,
    repeated_stops,
    split_frequencies,
    timezone_of,
)
from gtfs_rt_validator.static.adapter import RawTables

# `GtfsMetadata.java:43-45`. Both buffers now live in `geometry/bbox.py`, beside
# `KM_TO_DEG`, because E029's occurrence text renders `TRIP_BUFFER_METERS` and
# the rules layer may not import `static/`. Re-exported here, where this module's
# readers have always found them. The trip buffer is applied to raw degrees with
# no latitude correction, so it spans 200 m north-south and 200 * cos(lat) m
# east-west, and reproducing that is the point. See `geometry/buffer.py`.

__all__ = ["TRIP_BUFFER_DEGREES", "TRIP_BUFFER_METERS", "BufferedTripShape", "StaticContext"]


@dataclass(frozen=True, slots=True)
class BufferedTripShape:
    """One trip's shape, and the question E029 asks of it.

    Upstream caches the buffered *polygon*; this caches the shape and the
    distance, because `within_buffered_shape` is the whole public surface of the
    JTS port and it takes the shape and the point together. The answers are the
    same, and the difference is wall clock: this rebuilds the offset curve per
    query where upstream builds it once. If that ever matters, the fix is to
    expose the curve from `geometry/buffer.py`, not to change this contract.
    """

    points: tuple[Point, ...]
    distance_degrees: float

    def contains(self, lon: float, lat: float) -> bool:
        """`isPositionWithinShape`: a point on the boundary counts as inside."""
        return within_buffered_shape(self.points, lon, lat, self.distance_degrees)


@dataclass(frozen=True, slots=True)
class StaticContext:
    """Everything a realtime rule may ask of the static feed.

    Member names follow upstream's, minus the Hungarian `m` and in snake_case,
    so the mapping to `GtfsMetadata.java` stays legible from either side. The
    two `shape_bounding_box` members are `None` rather than an empty rectangle
    when the gate is shut, because upstream initialises them to `null` and
    `VehicleValidator` branches on exactly that.
    """

    timezone: str | None
    agency_ids: frozenset[str]
    route_ids: frozenset[str]
    stop_ids: frozenset[str]
    trips: dict[str, Row]
    trip_stop_times: dict[str, list[Row]]
    exact_times_zero_trip_ids: frozenset[str]
    exact_times_one_trips: dict[str, list[Row]]
    shape_points: dict[str, list[Row]]
    trip_shapes: dict[str, list[Point]]
    stop_bounding_box: Rectangle
    stop_bounding_box_buffered: Rectangle
    shape_bounding_box: Rectangle | None
    shape_bounding_box_buffered: Rectangle | None
    stop_location_types: dict[str, int]
    trips_with_multi_stops: dict[str, list[str]]

    #: route_id to every stop_id some trip of that route serves. **The one
    #: member here that upstream's `GtfsMetadata` has no counterpart for**, and
    #: the only one whose name is therefore ours rather than a translation.
    #: P012 reads it and nothing in the 56 does.
    #:
    #: **It adds no table.** It is a join of `trips` and `trip_stop_times`, both
    #: already built above from `trips.txt` and `stop_times.txt`, so
    #: `adapter.SEVEN_TABLES` is still the exact set a realtime run reads and
    #: the comment above it is still true. `_tables.build_route_stop_ids` holds
    #: the join and says what it does with a route that serves nothing.
    route_stop_ids: dict[str, frozenset[str]]

    #: Every `shape_id` `shapes.txt` declares, **read before the gate**. The
    #: second member here with no `GtfsMetadata` counterpart, and the second one
    #: whose name is ours.
    #:
    #: `shape_points` above is the gated structure and is what the 56 read: it
    #: is empty for a feed of three shape points or fewer, because that is what
    #: `GtfsMetadata.java:127` does, and a compat rule that saw ids the jar
    #: could not see would diverge. But a three-point shape is a valid shape,
    #: and a modern rule asking which ids the static feed *declares* is asking a
    #: different question from one asking which geometry survived. S038 asks the
    #: first, so it reads this. Nothing under `rules/upstream/` may.
    #:
    #: **It adds no table.** `shapes.txt` is already one of
    #: `adapter.SEVEN_TABLES` and `build_shapes` is handed the same rows.
    #: `-ignoreShapes` still empties it, because that flag empties `RawTables`
    #: itself at the loader rather than at the gate. `shapes_withheld` below is
    #: how a reader tells that emptiness from a feed that declares no shapes.
    shape_ids: frozenset[str]

    #: Whether `-ignoreShapes` kept `shapes.txt` from being read at all. The
    #: third member with no `GtfsMetadata` counterpart, and the only one that is
    #: not feed content: it is a fact about the run.
    #:
    #: **It exists because "empty" is three different answers.** `shape_ids` is
    #: empty when the archive ships no `shapes.txt`, which means no static shape
    #: id exists and "this value is not one" is decidable. It is also empty
    #: under the flag, which means the ids were never looked at and the same
    #: question has no answer. `adapter.py` deliberately collapses the two into
    #: one `RawTables` because upstream's flag has the same effect on everything
    #: downstream, so the flag has to be carried separately to be recoverable at
    #: all. S016 and S044 return early on this rather than on an empty shape
    #: structure, which is what stops the flag from hiding a finding that never
    #: needed `shapes.txt`.
    #:
    #: **No rule under `rules/upstream/` reads it and none may**, so compat is
    #: untouched: the jar has no such distinction to reproduce, and a compat
    #: rule that branched on this would diverge by construction. It is a
    #: constructor argument the class already took and dropped; storing it adds
    #: no table and no work.
    shapes_withheld: bool

    # `mTripShapesBuffered`, and the only mutable state here. Not compared and
    # not printed: two contexts built from the same feed are the same context
    # whether or not either has been asked for a buffered shape yet.
    _buffered_trip_shapes: dict[str, BufferedTripShape] = field(
        default_factory=dict, repr=False, compare=False
    )

    @classmethod
    def build(cls, raw: RawTables, *, ignore_shapes: bool = False) -> StaticContext:
        """`GtfsMetadata`'s constructor, in its own order.

        The order matters twice: `trip_shapes` reads `shape_points`, so the
        shapes block runs first, and `trips_with_multi_stops` reads
        `trip_stop_times` after it has been sorted.
        """
        shape_points, shape_box, shape_box_buffered = build_shapes(
            raw.shapes, ignore_shapes=ignore_shapes
        )
        trip_stop_times = group_stop_times(raw.stop_times)
        trips, trip_shapes = build_trips(raw.trips, shape_points)
        stop_ids, location_types, stop_box = build_stops(raw.stops)
        exact_times_zero, exact_times_one = split_frequencies(raw.frequencies)
        return cls(
            timezone=timezone_of(raw.agency),
            agency_ids=frozenset(agency_id_of(row) for row in raw.agency),
            route_ids=frozenset(row["route_id"] for row in raw.routes),
            stop_ids=stop_ids,
            trips=trips,
            trip_stop_times=trip_stop_times,
            exact_times_zero_trip_ids=exact_times_zero,
            exact_times_one_trips=exact_times_one,
            shape_points=shape_points,
            trip_shapes=trip_shapes,
            stop_bounding_box=stop_box,
            stop_bounding_box_buffered=stop_box.buffered(REGION_BUFFER_DEGREES),
            shape_bounding_box=shape_box,
            shape_bounding_box_buffered=shape_box_buffered,
            stop_location_types=location_types,
            trips_with_multi_stops=repeated_stops(trip_stop_times),
            route_stop_ids=build_route_stop_ids(trips, trip_stop_times),
            shape_ids=frozenset(row["shape_id"] for row in raw.shapes),
            shapes_withheld=ignore_shapes,
        )

    def buffered_trip_shape(self, trip_id: str) -> BufferedTripShape | None:
        """`getBufferedTripShape`: `None` for a trip with no shape, else cached.

        `None` covers three cases upstream also collapses into one: the trip is
        not in the feed, the trip has no usable `shape_id`, and there is no shape
        data at all because `-ignoreShapes` was set or the gate is shut. E029
        returns early on all three, which is why the flag disables it silently.
        """
        cached = self._buffered_trip_shapes.get(trip_id)
        if cached is not None:
            return cached
        points = self.trip_shapes.get(trip_id)
        if points is None:
            return None
        shape = BufferedTripShape(tuple(points), TRIP_BUFFER_DEGREES)
        self._buffered_trip_shapes[trip_id] = shape
        return shape
