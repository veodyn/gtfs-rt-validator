"""The static feed and the descriptors `TripDescriptorValidator`'s tests need.

Sixteen modules read this: the walk's own test and one per rule. `rulefixtures`
carries what every rule cohort needs; this carries what only this cohort does.

**One feed, where upstream switches between three.** `TripDescriptorValidatorTest`
picks `gtfsData` (`testagency.zip`), `gtfsData2` (`testagency2.zip`) or
`bullRunnerGtfs` (`bullrunner-gtfs.zip`) per assertion. A Python test has no
reason to reload a different archive halfway through, so `feed_tables` below is
the union of the rows those three contribute, keeping upstream's own ids so a
ported assertion still reads as upstream's:

- `1.1`, `1.2` and `1.3` on route `1`, `2.1` on route `2`, `3.1` on route `3`,
  from the two testagency feeds. The direction_ids are **testagency2's** (0, 1
  and blank), because testagency's are all blank and only E024 looks at them.
- `1` on route `A`, and routes `A` and `B`, from bullrunner. Route `B` has to
  exist for E035's three-occurrence case to be reachable at all: `checkE035`
  returns early when the realtime route_id is not in `routes.txt`, and it is
  there in bullrunner (measured by unzipping it, `routes.txt` lines A through F).
- agency id `agency`, from testagency, for E034.

Two trips carry a frequency so E023's two exemptions are reachable: `f0` with
`exact_times` 0 and `f1` with `exact_times` 1. `1.3`'s first stop_time has no
`arrival_time`, which is how E023's -999 sentinel is reached.

The realtime side is dicts, not builders, and the enum members are ints because
that is what the wire carries. `DUPLICATED` is 6, a value the 2015 enum does not
have, and it is here so the enum gap can be tested with a real post-2015 value
rather than a mocked absence.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

from gtfs_rt_validator.report.occurrence import Occurrence
from gtfs_rt_validator.runner.context import RuleContext
from rulefixtures import context, entity, message, minimal

#: `TripDescriptor.ScheduleRelationship`, by number. The first three are in the
#: 2015 enum; `DUPLICATED` was added later and is what the two-schema decoder
#: files as an unknown field.
SCHEDULED = 0
ADDED = 1
CANCELED = 3
DUPLICATED = 6

#: testagency.zip's agency_id, which E034 matches against.
AGENCY_ID = "agency"


def feed_tables() -> dict[str, list[dict[str, str]]]:
    """`minimal_tables()` plus the rows this cohort's fifteen rules read."""
    return minimal(
        agency=[
            {
                "agency_id": AGENCY_ID,
                "agency_name": "Fake Agency",
                "agency_url": "http://fake.example.com",
                "agency_timezone": "America/New_York",
            }
        ],
        routes=[
            {
                "route_id": route_id,
                "agency_id": AGENCY_ID,
                "route_short_name": route_id,
                "route_long_name": route_id,
                "route_type": "3",
            }
            for route_id in ("1", "2", "3", "A", "B")
        ],
        trips=[
            {"trip_id": trip_id, "route_id": route_id, "service_id": "alldays", **extra}
            for trip_id, route_id, extra in (
                ("1.1", "1", {"direction_id": "0"}),
                ("1.2", "1", {"direction_id": "0"}),
                ("1.3", "1", {"direction_id": "0"}),
                ("2.1", "2", {"direction_id": "1"}),
                ("3.1", "3", {"direction_id": ""}),
                ("1", "A", {"direction_id": ""}),
                ("f0", "1", {"direction_id": ""}),
                ("f1", "1", {"direction_id": ""}),
            )
        ],
        stop_times=[
            {
                "trip_id": trip_id,
                "arrival_time": arrival,
                "departure_time": departure,
                "stop_id": stop_id,
                "stop_sequence": str(sequence),
            }
            for trip_id, sequence, stop_id, arrival, departure in (
                ("1.2", 1, "S1", "00:20:00", "00:20:00"),
                ("1.2", 2, "S2", "00:30:00", "00:30:00"),
                ("1.3", 1, "S1", "", "00:40:00"),
                ("1.3", 2, "S2", "00:50:00", "00:50:00"),
                ("f0", 1, "S1", "00:20:00", "00:20:00"),
                ("f1", 1, "S1", "00:20:00", "00:20:00"),
            )
        ],
        frequencies=[
            {
                "trip_id": trip_id,
                "start_time": "06:00:00",
                "end_time": "10:00:00",
                "headway_secs": "600",
                "exact_times": exact_times,
            }
            for trip_id, exact_times in (("f0", "0"), ("f1", "1"))
        ],
    )


def feed_context(tmp_path: Path, **overrides: Any) -> RuleContext:
    """A rule context over `feed_tables()`."""
    return context(tmp_path, feed_tables(), **overrides)


def td(**fields: object) -> dict[str, object]:
    """A TripDescriptor. Every field is optional, which is the point of it.

    `td()` is the empty descriptor a TripUpdate must still carry, since
    `TripUpdate.trip` is required at both pins.
    """
    return dict(fields)


def selector(**fields: object) -> dict[str, object]:
    """One `EntitySelector`. `trip=td(...)` sets the sub-message."""
    return dict(fields)


def alert(*selectors: Mapping[str, object]) -> dict[str, object]:
    """An `Alert`. No arguments is the empty informed_entity list E032 reports."""
    return {"informed_entity": [dict(one) for one in selectors]}


def both(descriptor: Mapping[str, object]) -> dict[str, object]:
    """Upstream's own entity: a TripUpdate and a VehiclePosition, one descriptor.

    Most of `TripDescriptorValidatorTest` sets `tripUpdateBuilder.setTrip` and
    `vehiclePositionBuilder.setTrip` from the same builder and expects two
    occurrences, which is why so many of its counts are 2.

    The VehiclePosition carries no `vehicle` descriptor, because
    `FeedMessageTest`'s never does. Every text built through
    `getVehicleAndTripIdText` therefore comes out with the double space an
    unguarded `getVehicle().getId()` leaves behind, and so does E003's and
    E016's inline vehicle text.
    """
    return entity(trip_update={"trip": dict(descriptor)}, vehicle={"trip": dict(descriptor)})


def run(
    check: Any, tmp_path: Path, *entities: Mapping[str, object], **overrides: Any
) -> list[Occurrence]:
    """Call one rule over these entities and return what it found."""
    result: Iterable[Occurrence] | None = check(
        message(*entities), feed_context(tmp_path, **overrides)
    )
    return [] if result is None else list(result)
