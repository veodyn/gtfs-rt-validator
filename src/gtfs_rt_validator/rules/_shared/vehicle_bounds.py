"""The two geometry checks inside `VehicleValidator`, and the alert scan E029 uses.

`checkE028` (`VehicleValidator.java:164-190`), `checkE029` (`:200-232`) and
`hasDetourAlert` (`:242-264`), split off `walk_vehicle.py` so that the loop and
the geometry it calls into stay separately readable. The nesting that makes E029
depend on E028 belongs to the loop and lives there; what is here is what each
check answers on its own.

No geometry is computed in this module. `geometry/bbox.py` and
`geometry/buffer.py` reproduce spatial4j 0.6 and JTS 1.13 already, the static
layer buffers the boxes and the trip shapes, and `_shared/positions.py` wraps
the point test. What this owns is which box is asked, and the text that goes out
when the answer is no.

**Two renderings reach output bytes and neither is Python's default.** The
coordinates are protobuf floats concatenated by Java, so they go through
`Float.toString` as JDK 17 writes it (`javafmt.float32_str`), and the buffer
distances are `double` constants, so `"1609.0"` and `"200.0"` rather than
`"1609"` and `"200"` (`javafmt.double_str`). The mile figures come from
`String.format("%.2f", ...)`, which is `javafmt.fmt2`.

**`%.2f` follows the JVM's default locale.** Upstream passes no `Locale` at
`:185` or `:229`, so a jar run under a comma-decimal locale writes `"1,00"`
where one run under `en_US` writes `"1.00"`. That is upstream's behaviour and
compat reproduces the dot, which is what the measured environment produces and
what `tools/diff_javafmt_against_java.py` re-checks against `Locale.ROOT` on
every run. A golden compared against a jar under another locale differs here,
and the jar is what changed.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from gtfs_rt_validator.geometry.bbox import REGION_BUFFER_METERS, TRIP_BUFFER_METERS
from gtfs_rt_validator.proto.decode import Msg
from gtfs_rt_validator.rules._shared.alert_index import index_of_entities
from gtfs_rt_validator.rules._shared.ids import vehicle_id_text
from gtfs_rt_validator.rules._shared.javafmt import double_str, float32_str, fmt2
from gtfs_rt_validator.rules._shared.positions import is_position_within_shape, to_miles

if TYPE_CHECKING:  # Type-only: `runner.context` reaches the static layer and so
    # the sibling, and nothing under `rules/` may import that at run time.
    from collections.abc import Sequence

    from gtfs_rt_validator.runner.context import RuleContext

__all__ = [
    "DETOUR_EFFECT",
    "TRIP_BUFFER_METERS",
    "e028_prefix",
    "e029_prefix",
    "has_detour_alert",
    "inside_agency_bounds",
    "position_text",
]

#: `GtfsMetadata.java:44`, a `double`, so it renders "200.0" and never "200".
#: Declared here rather than imported from `static/context.py`, which holds the
#: same constant beside the geometry that consumes it: the rules layer may not
#: import `static/`, and `tests/test_shared_walk_vehicle.py` asserts the two
#: have not drifted.

#: `Alert.Effect.DETOUR`. The number is 4 under the 2015 schema and under the
#: current one alike, so reading it here needs no schema and is therefore not a
#: mode branch; `tests/test_shared_detour_alert.py` asserts that stays true.
DETOUR_EFFECT = 4


def position_text(position: Msg) -> str:
    """`"(" + getLatitude() + "," + getLongitude() + ")"`. No space after the comma."""
    latitude = float32_str(position.get("latitude"))
    longitude = float32_str(position.get("longitude"))
    return "(" + latitude + "," + longitude + ")"


def inside_agency_bounds(position: Msg, ctx: RuleContext) -> tuple[bool, str]:
    """`checkE028`'s box choice and verdict: is it inside, and which box was it.

    The shapes box wins whenever it exists, and its existence flips the
    occurrence text as well as the geometry. It is `None` when `shapes.txt` is
    missing, when `-ignoreShapes` was passed, and when the feed-wide shape point
    count is three or fewer (`GtfsMetadata.java:127`, `shapePoints.size() > 3`,
    so four points open the gate). In all three cases the box is the stops box
    and the description reads `stops.txt`, which is an output-byte difference
    and not merely a sensitivity one.
    """
    bounds = ctx.static.shape_bounding_box_buffered
    if bounds is None:
        return is_position_within_shape(
            position, ctx.static.stop_bounding_box_buffered
        ), "stops.txt"
    return is_position_within_shape(position, bounds), "shapes.txt"


def e028_prefix(entity: Msg, vehicle_position: Msg, description: str) -> str:
    """`:184-186`, verbatim."""
    return (
        vehicle_id_text(entity, vehicle_position)
        + " at "
        + position_text(vehicle_position.get("position"))
        + " is more than "
        + double_str(REGION_BUFFER_METERS)
        + " meters ("
        + fmt2(to_miles(REGION_BUFFER_METERS))
        + " mile(s)) outside entire GTFS "
        + description
        + " coverage area"
    )


def e029_prefix(entity: Msg, vehicle_position: Msg, trip_id: str) -> str:
    """`:228-229`, verbatim. The text says 200 metres; the buffer is applied in
    raw degrees with no latitude correction, so east-west it is about
    `200 * cos(lat)`. `geometry/buffer.py` reproduces that on purpose."""
    return (
        vehicle_id_text(entity, vehicle_position)
        + " trip_id "
        + trip_id
        + " at "
        + position_text(vehicle_position.get("position"))
        + " is more than "
        + double_str(TRIP_BUFFER_METERS)
        + " meters ("
        + fmt2(to_miles(TRIP_BUFFER_METERS))
        + " mile(s)) from the GTFS trip shape"
    )


def has_detour_alert(entities: Sequence[Msg], trip_id: str, route_id: str | None) -> bool:
    """`hasDetourAlert`, `:242-264`: a whole-feed scan, run per failing position.

    Upstream's own comment calls it expensive and it caches nothing, so neither
    does this. Two details are easy to get wrong. The route comparison reads
    `informed_entity.trip.route_id`, not `informed_entity.route_id`, so a
    selector naming a route directly fails `hasTrip()` and is skipped. And it is
    guarded by `routeId != null`, which is E029's `hasRouteId()` ternary rather
    than anything about the selector, so a vehicle whose TripDescriptor sets
    `route_id` to the empty string matches every DETOUR selector that names a
    trip and no route.

    **The scan itself lives in `_shared/alert_index.py` now**, because P006, P012
    and P015 ask three more questions of the same selector list and a second
    traversal beside this one would be two readings of `:242-264` to keep in
    step. Both details above are properties of that index, stated there and
    pinned by `tests/test_shared_alert_index.py` against every shape
    `tests/test_shared_detour_alert.py` builds. This signature is unchanged and
    so is what E029 sees.
    """
    return index_of_entities(entities).has_effect(DETOUR_EFFECT, trip_id, route_id)
