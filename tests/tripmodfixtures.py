"""Scaffolding the ten `TripModifications` rules share, so S041 to S050 do not
each invent it.

`rulefixtures` builds under `schema_2015`, which has no `TripModifications` at
all, so a fixture for one built there would encode as nothing and every test over
it would pass by being empty. `specfixtures` builds under `schema_current` but
its context has an empty static feed, which is what its own docstring says to do
for a memoisation test and not what a rule reading `stops.txt` needs. So these
compose the two: the message from `specfixtures`, the static feed from
`rulefixtures.static_context`, which goes through a real archive on disk and the
real loader.

`load_static_as_onebusaway` is what `rulefixtures` uses, because every rule it
was written for is a port of the jar's. Cohort H's rules have no jar to match, so
the reader they see should be the strict one modern mode uses; `static_feed`
below says so and calls `load_static` itself.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, MutableMapping, Sequence
from pathlib import Path

from gtfs_rt_validator.proto.schema_current import SCHEMA
from gtfs_rt_validator.report.occurrence import ENTITY_PATH_KEY, Occurrence
from gtfs_rt_validator.runner.clock import Reading
from gtfs_rt_validator.runner.context import RuleContext
from gtfs_rt_validator.static.adapter import load_static
from gtfs_rt_validator.static.context import StaticContext
from gtfsfixtures import build_feed, minimal_tables
from rulefixtures import minimal, stop_rows
from specfixtures import context, entity, message

__all__ = [
    "context",
    "entity",
    "message",
    "minimal",
    "modification",
    "paths",
    "prefixes",
    "relationship",
    "rule_context",
    "static_feed",
    "stop_rows",
    "trip_modifications",
]


def relationship(name: str) -> int:
    """The `TripDescriptor.ScheduleRelationship` number the encoder wants.

    Read out of the pinned schema rather than written down, because the numbers
    are not contiguous and a test asserting against 5 says nothing about which
    member it meant. `_shared/schedule_relationship.py` makes the same argument
    on the reading side.
    """
    return SCHEMA.enums["TripDescriptor.ScheduleRelationship"][name]


def modification(
    *stops: Mapping[str, object],
    start: Mapping[str, object] | None = None,
    end: Mapping[str, object] | None = None,
) -> dict[str, object]:
    """One `Modification`, its two stop selectors named rather than positional.

    Every modification here declares a `start_stop_selector` unless a test is
    about S041, because a rule under test should fail on its own defect and not
    on a neighbouring one it shares a fixture with.
    """
    built: dict[str, object] = {"replacement_stops": [dict(stop) for stop in stops]}
    if start is not None:
        built["start_stop_selector"] = dict(start)
    if end is not None:
        built["end_stop_selector"] = dict(end)
    return built


def trip_modifications(
    *modifications: Mapping[str, object],
    entity_id: str = "TM",
    trip_ids: Sequence[str] = (),
    shape_id: str | None = None,
    service_dates: Sequence[str] = (),
) -> dict[str, object]:
    """One `FeedEntity` carrying a `TripModifications`.

    `selected_trips` is written only when a test names trips or a shape, so a
    fixture for a stop-level rule does not quietly acquire a `SelectedTrips`
    that S044 and S045 would then have an opinion about.
    """
    selected: dict[str, object] = {}
    if trip_ids:
        selected["trip_ids"] = list(trip_ids)
    if shape_id is not None:
        selected["shape_id"] = shape_id
    payload: dict[str, object] = {"modifications": [dict(one) for one in modifications]}
    if selected:
        payload["selected_trips"] = [selected]
    if service_dates:
        payload["service_dates"] = list(service_dates)
    return entity(entity_id, trip_modifications=payload)


def static_feed(
    tmp_path: Path,
    tables: MutableMapping[str, list[dict[str, str]]] | None = None,
    *,
    ignore_shapes: bool = False,
) -> StaticContext:
    """A `StaticContext` through the strict loader, which is modern mode's.

    `rulefixtures.static_context` reads through onebusaway because every rule it
    serves is a port of the jar's and the jar's feed comes out of that reader.
    Nothing in cohort H has a jar to match, so the reader here is the one a
    modern run actually uses.

    `ignore_shapes` skips `shapes.txt` on both halves, as a real run does, which
    is the state S044 has to return early on rather than report every `shape_id`
    in the feed as unresolvable.
    """
    return StaticContext.build(
        load_static(
            build_feed(tmp_path, tables if tables is not None else minimal_tables()),
            ignore_shapes=ignore_shapes,
        ),
        ignore_shapes=ignore_shapes,
    )


def rule_context(
    tmp_path: Path,
    tables: MutableMapping[str, list[dict[str, str]]] | None = None,
    *,
    clock: Reading | None = None,
    ignore_shapes: bool = False,
) -> RuleContext:
    """`specfixtures.context` over a real static feed."""
    overrides: dict[str, object] = {
        "static": static_feed(tmp_path, tables, ignore_shapes=ignore_shapes)
    }
    if clock is not None:
        overrides["clock"] = clock
    return context(**overrides)


def prefixes(result: Iterable[Occurrence] | None) -> list[str]:
    """What a rule reported, in order. `None` is a rule that returned early."""
    return [] if result is None else [found.prefix for found in result]


def paths(result: Iterable[Occurrence] | None) -> list[object]:
    """The `entityPath` of each occurrence, which is where a rule located it."""
    return [] if result is None else [found.context[ENTITY_PATH_KEY] for found in result]
