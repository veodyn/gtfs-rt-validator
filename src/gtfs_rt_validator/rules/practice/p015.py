"""P015: a vehicle more than 200 metres from its trip's shape, that E029 cleared.

`:120`. E029 asks the same question and answers it in **degrees**:
`TRIP_BUFFER_DEGREES` is 0.0017986 and `geometry/buffer.py` applies it planar,
with no latitude correction, because reproducing JTS 1.13 byte for byte is what
E029 is for. That buffer is not 200 metres anywhere except by coincidence:

- **East to west it is `200 * cos(lat)` metres**, so 141 at 45 degrees north and
  100 at 60. There E029 is *stricter* than the document, it over-reports by this
  document's lights, and a rule that may only add notices cannot repair it. That
  half is recorded as a divergence against clause `120#1` and is deliberately not
  this rule's.
- **North to south it is 0.0017986 times the length of a degree of latitude**,
  which is 198.9 metres at the equator and 200.39 at 60 degrees north. It crosses
  200 metres at about 48.3 degrees, so above that latitude there are positions
  E029 clears and `:120` does not. That shell is this rule's, and
  `tests/test_rule_p015.py` fires inside it and is silent below it rather than
  asserting the paragraph.

**The threshold is this rule's own constant and not an import.**
`geometry/bbox.TRIP_BUFFER_METERS` is the same number today, but it is
`GtfsMetadata.java:44` and this one is `:120` of the Best Practices. Importing it
would let a change to a compat constant silently move a cited threshold, and it
would put a practice rule on a module the compat path owns. The comparison is
strict, because "should be within 200 meters" is satisfied at exactly 200.

## How it avoids reporting a vehicle E029 already reported

**It stands inside E029's nest rather than beside it**, and it reads that nest
from the same walk E029 filters rather than from any occurrence container.
`_shared/walk_vehicle.vehicles` is memoised per message by
`_shared/walks.walk_events`, so this rule is handed the identical tuple of events
E029 is handed, and it skips every `entity[i].vehicle` path that produced one of
three ids:

- **E029**: the vehicle is already reported as far from its shape.
- **E028**: the vehicle is outside the agency's coverage area, so E029 was never
  evaluated for it. Measuring it against a trip shape as well is exactly the
  double report `e029.py`'s docstring warns a naive port into.
- **E026**: the coordinates are not a place on the earth, so a distance from
  them is a number rather than a measurement.

Nothing in the walk is modified, and nothing it calls is modified, so E028 and
E029 see what they saw. They are compat byte contracts and this is the one shared
module either cited tier reads that the compat writer also reaches, so the
differential is re-run in the commit that lands this.

## The two things it does that E029 cannot

**It measures on the ellipsoid.** `_shared/geodesic.distance_to_polyline` works
in a local east-north plane over WGS-84 earth-centred coordinates, so no earth
radius is assumed and no axis is privileged. `None` back from it means the
polyline had no points, and it is handled rather than compared: `inf > 200` would
have been a silent report of every vehicle in a feed whose shapes did not decode.

**It can read a realtime `Shape`, and prefers one.** `Shape` postdates the 2015
schema, so E029 cannot see one at all. A trip reaches one through
`TripUpdate.TripProperties.shape_id` or `TripModifications.SelectedTrips`, since
neither `VehiclePosition` nor `TripDescriptor` carries a `shape_id` of its own.
**The realtime shape wins when the trip claims one**, because a trip that
publishes its own geometry has said that `shapes.txt` is not its path: a NEW trip
has no static shape at all, and a modified one's static shape is the path it is
no longer taking. A realtime shape is used only when it decodes whole and yields
at least one point; a truncated one is S040's finding and is not a path.

One consequence cannot be repaired here and is recorded rather than worked
around: when a trip has both a stale static shape and a realtime one, E029
measures against the static shape and may fire, which suppresses this rule even
though the realtime shape says the vehicle is fine. A practice rule may only add
notices, so that false positive stays upstream's.

**The DETOUR exemption is `:120`'s own**, and its scope is the whole cycle
wherever the context has one, from every role of it. `_shared/alert_index`'s
`visible_index` is that read, and it is `ctx.cycle` rather than `ctx.combined`:
the cycle is on every role's context, while `combined` is the host's token for
"I am the one who reports" and belongs to the cross-feed rules. A
VehiclePositions message in a `-tu -vp -sa` run is not the host and used to fall
back to its own message, which by construction carries no Alerts, so every
detoured vehicle in that layout was reported. It is not any more.

**With no cycle at all it reads its own message, and that is the complete
answer.** One message standing alone is the whole feed, so its Alerts are every
Alert there is. That case is not "I am not the host", which is the confusion this
rule and P006 used to resolve in opposite directions until the context grew
`cycle` beside `combined`; they now agree in all three cases, and what makes
this one safe is that widening a suppressor only ever removes an occurrence and
can never invent one. E029 still scans its own message and no more, because it
is a compat byte contract.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from gtfs_rt_validator.report import manifest
from gtfs_rt_validator.report.occurrence import ENTITY_PATH_KEY, Occurrence
from gtfs_rt_validator.rules._shared.alert_index import visible_index
from gtfs_rt_validator.rules._shared.geodesic import distance_to_polyline
from gtfs_rt_validator.rules._shared.realtime_shapes import shapes_by_trip
from gtfs_rt_validator.rules._shared.vehicle_bounds import DETOUR_EFFECT
from gtfs_rt_validator.rules._shared.walk_vehicle import vehicles
from gtfs_rt_validator.rules._shared.walks import walk_events
from gtfs_rt_validator.rules.registry import rule

if TYPE_CHECKING:  # Type-only: `runner.context` reaches the static layer and so
    # the sibling, which nothing under `rules/` may import at run time.
    from collections.abc import Iterator

    from gtfs_rt_validator.proto.decode import Msg
    from gtfs_rt_validator.rules._shared.alert_index import AlertIndex
    from gtfs_rt_validator.rules._shared.realtime_shapes import Points
    from gtfs_rt_validator.runner.context import RuleContext, RuleResult

RULE_ID = "P015"

CLAUSE = (
    "The vehicle position should be within 200 meters of the GTFS `shapes.txt` data for the "
    "current trip unless there is an alert with the effect of `DETOUR` for this `trip_id`."
)

#: `:120`'s own number, in metres. Not `geometry/bbox.TRIP_BUFFER_METERS`; see
#: the module docstring for why the two are kept apart.
THRESHOLD_METERS = 200.0

#: The three ids whose presence on a vehicle's path means this rule was either
#: already answered there or never reached.
NESTED = frozenset({"E026", "E028", "E029"})

STATIC_SOURCE = "shapes.txt"
REALTIME_SOURCE = "a realtime Shape entity"

FAR = (
    "trip_id {trip_id} is {distance:.1f} meters from the trip shape in {source}, which is "
    "more than {limit:.0f}, and no alert with an effect of DETOUR names the trip"
)


@rule(RULE_ID, source=f"practice: {CLAUSE}", severity=manifest.Severity.WARNING)
def check(message: Msg, ctx: RuleContext) -> RuleResult:
    """One occurrence per vehicle position, in entity order."""
    already = _reported_paths(message, ctx)
    alerts = visible_index(message, ctx)
    shapes = shapes_by_trip(message, ctx)
    return [
        found
        for position, entity in enumerate(message.get("entity"))
        if entity.has("vehicle") and f"entity[{position}].vehicle" not in already
        for found in _measure(
            entity.get("vehicle"), f"entity[{position}].vehicle", alerts, shapes, ctx
        )
    ]


def _measure(
    vehicle_position: Msg,
    path: str,
    alerts: AlertIndex,
    shapes: dict[str, Points],
    ctx: RuleContext,
) -> Iterator[Occurrence]:
    """The check for one VehiclePosition that E029's nest let through."""
    trip = vehicle_position.get("trip")
    if not vehicle_position.has("position") or not vehicle_position.has("trip"):
        return
    if not trip.has("trip_id"):
        return
    trip_id = trip.get("trip_id")
    # `route_id if hasRouteId() else None` is E029's own ternary, reproduced so
    # the exemption this rule honours is the exemption E029 honours.
    route_id = trip.get("route_id") if trip.has("route_id") else None
    if alerts.has_effect(DETOUR_EFFECT, trip_id, route_id):
        return
    points, source = _shape_for(trip_id, shapes, ctx)
    if points is None:
        return
    position = vehicle_position.get("position")
    distance = distance_to_polyline(points, position.get("longitude"), position.get("latitude"))
    if distance is None or distance <= THRESHOLD_METERS:
        return
    yield Occurrence(
        RULE_ID,
        FAR.format(trip_id=trip_id, distance=distance, source=source, limit=THRESHOLD_METERS),
        {
            ENTITY_PATH_KEY: path,
            "tripId": trip_id,
            "distanceMeters": round(distance, 1),
            "shapeSource": source,
        },
    )


def _reported_paths(message: Msg, ctx: RuleContext) -> frozenset[str]:
    """The vehicle paths E029 answered, or never reached. See the docstring.

    `walk_events` is the memo, so this is the same tuple `e029.check` filters
    rather than a second traversal, and the walk is read and never changed.
    """
    return frozenset(
        str(event.context[ENTITY_PATH_KEY])
        for event in walk_events(vehicles, message, ctx)
        if event.rule_id in NESTED
    )


def _shape_for(
    trip_id: str, shapes: dict[str, Points], ctx: RuleContext
) -> tuple[Points | None, str]:
    """The trip's geometry as `(lon, lat)` points, and where it came from."""
    claimed = shapes.get(trip_id)
    if claimed:
        return claimed, REALTIME_SOURCE
    static = ctx.static.trip_shapes.get(trip_id)
    if static:
        return tuple(static), STATIC_SOURCE
    return None, ""
