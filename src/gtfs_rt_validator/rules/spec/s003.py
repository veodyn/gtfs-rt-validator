"""S003: two TripUpdate entities describing one trip instance.

`:157`. The instance key is the one the `TripDescriptor` comment gives at
`:803-806`: "For non frequency-based trips, this field is enough to uniquely
identify the trip. For frequency-based trip, start_time and start_date might
also be necessary." So the key is `(trip_id, start_date, start_time)` with the
two optional halves included only when the descriptor states them. Two
descriptors that agree on `trip_id` and disagree on `start_date` are two
instances and neither is a duplicate of the other.

**`start_time` leaves the key when the static feed says the trip is not
frequency-based.** `:817` allows it there only "omitted or equal to the value
in the GTFS feed", so on such a trip the field distinguishes nothing and one
descriptor stating it while another omits it is two spellings of the instance
`:803` says `trip_id` alone identifies. `start_date` is not treated that way,
and the asymmetry is the reason each field carries: an omitted `start_date`
names every service date at once, where an omitted `start_time` on a
non-frequency trip names the one time the schedule fixes. Nothing here reads
that time; knowing the trip is not in `frequencies.txt` is the whole question,
and `ctx.static` already answers it. A `trip_id` the static feed does not carry
keeps its `start_time`, because an ADDED trip has no scheduled start for the
field to be redundant with.

**A descriptor with no `trip_id` names no instance.** `:797` describes the
route-scoped form, "To specify all the trips along a given route, only the
route_id should be set", which S018 and S019 are about. Keying it under the
empty string would collapse every route-scoped TripUpdate in a feed into one
imaginary trip and report a correct feed.

Nothing in the 56 counts TripUpdates per trip. E047 and W003 pair a TripUpdate
against a VehiclePosition, which is a different relation and is why a
VehiclePosition for the same trip is not a finding here.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from gtfs_rt_validator.report import manifest
from gtfs_rt_validator.report.occurrence import Occurrence
from gtfs_rt_validator.rules._shared.walk_entities import entities
from gtfs_rt_validator.rules.registry import rule

if TYPE_CHECKING:  # Type-only: `runner.context` reaches the static layer and so
    # the sibling, which nothing under `rules/` may import at run time.
    from gtfs_rt_validator.proto.decode import Msg
    from gtfs_rt_validator.runner.context import RuleContext, RuleResult

RULE_ID = "S003"

CLAUSE = "There can be at most one TripUpdate entity for each actual trip instance."

REPEATED = "{instance} has {count} TripUpdate entities"

#: The instance key, in the order the occurrence renders it. `trip_id` is what
#: makes an instance nameable at all, so a descriptor without it is skipped.
KEY_FIELDS = ("trip_id", "start_date", "start_time")

#: The same key for a trip `frequencies.txt` does not carry: `:817` fixes its
#: `start_time` to the scheduled one, so stating it names nothing new.
SCHEDULED_KEY_FIELDS = ("trip_id", "start_date")


@rule(RULE_ID, source=f"spec: {CLAUSE}", severity=manifest.Severity.ERROR)
def check(message: Msg, ctx: RuleContext) -> RuleResult:
    """One occurrence per trip instance more than one TripUpdate describes."""
    seen: dict[tuple[tuple[str, str], ...], list[int]] = {}
    for record in entities(message, ctx).carrying("trip_update"):
        key = _instance(record.entity.get("trip_update").get("trip"), ctx)
        if key is not None:
            seen.setdefault(key, []).append(record.index)
    return [
        Occurrence(
            RULE_ID,
            REPEATED.format(instance=_text(key), count=len(indexes)),
            {**dict(key), "entityIndexes": indexes},
        )
        for key, indexes in seen.items()
        if len(indexes) > 1
    ]


def _instance(trip: Msg, ctx: RuleContext) -> tuple[tuple[str, str], ...] | None:
    """The instance this descriptor names, or `None` for the route-scoped form."""
    if not trip.has("trip_id"):
        return None
    fields = SCHEDULED_KEY_FIELDS if _scheduled(trip.get("trip_id"), ctx) else KEY_FIELDS
    return tuple((name, trip.get(name)) for name in fields if trip.has(name))


def _scheduled(trip_id: str, ctx: RuleContext) -> bool:
    """Whether the static feed carries this trip and carries no frequency for it.

    Both halves are needed. A trip the feed does not have may be an ADDED one,
    whose `start_time` the schedule does not fix, and `frequencies.txt` is the
    only thing that makes `:817` require the field rather than allow it.
    """
    static = ctx.static
    if trip_id not in static.trips:
        return False
    return (
        trip_id not in static.exact_times_zero_trip_ids
        and trip_id not in static.exact_times_one_trips
    )


def _text(key: tuple[tuple[str, str], ...]) -> str:
    return " ".join(f"{name} {value}" for name, value in key)
