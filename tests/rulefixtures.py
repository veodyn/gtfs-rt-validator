"""Scaffolding every upstream rule test needs, so 56 of them do not each invent it.

Three things repeat across a rule test and only the third is interesting:

1. **Building a decoded message.** Every rule takes a `Msg`, and building one by
   hand skips the decoder, so a field name the 2015 schema does not have would
   read as an absent default instead of failing. `message` and `entity` go
   through the real `encode` then `decode`, which is what makes a typo loud.
2. **Building a `RuleContext`.** Most rules read `ctx.static`, several read
   `ctx.clock` or `ctx.timezone`, and a handful read `ctx.previous`. Assembling
   one takes a static feed, a clock and a timezone; only one of the three is
   usually the point of the test.
3. **Calling the rule and looking at what came back.** A rule returns an
   iterable of `Occurrence`, or `None` when it returns early, so every test
   needs the same normalisation before it can assert anything.

The convention these follow is upstream's own: `FeedMessageTest` gives every
entity `id = "TEST_ENTITY"` and builds one entity carrying a TripUpdate, a
VehiclePosition and an Alert at once. Porting that shape rather than splitting
it is what makes three-way ordering observable, so `entity` takes all three.

What this deliberately does **not** do is build the static feed itself. That is
`gtfsfixtures.minimal_tables` plus the real sibling loader, the same path
`tests/test_static_context.py` uses, because a `StaticContext` handed a dict
would hide how the loader types a blank column. `static_context` wraps that path
and takes the tables so a cohort can add the rows its rules need.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, MutableMapping, Sequence
from pathlib import Path
from typing import Any

from gtfs_rt_validator.proto.decode import Msg, decode
from gtfs_rt_validator.proto.encode import encode
from gtfs_rt_validator.proto.schema_2015 import SCHEMA
from gtfs_rt_validator.report.occurrence import Occurrence
from gtfs_rt_validator.runner.clock import ClockSource, Reading
from gtfs_rt_validator.runner.context import RuleContext
from gtfs_rt_validator.static.adapter import load_static_as_onebusaway
from gtfs_rt_validator.static.context import StaticContext
from gtfsfixtures import build_feed, minimal_tables

__all__ = [
    "ENTITY_ID",
    "READING",
    "TESTAGENCY_TIMEZONE",
    "context",
    "entity",
    "message",
    "occurrences",
    "prefixes",
    "static_context",
    "stop_rows",
    "trip_rows",
]

#: `FeedMessageTest.ENTITY_ID`. Every entity upstream's rule tests build has it,
#: so a ported prefix reading "entity ID TEST_ENTITY" is upstream's text.
ENTITY_ID = "TEST_ENTITY"

#: A fixed clock, so nothing here depends on when the suite runs. Rules that are
#: about time take their own reading rather than this one.
READING = Reading(1_700_000_000_000, ClockSource.FIXED)

#: `testagency.zip`'s zone, inferred from the one occurrence text upstream pins
#: byte for byte (`TimestampValidatorTest.java:1117`). The reference records it
#: as inferred rather than read, so a test that turns on it should say so.
TESTAGENCY_TIMEZONE = "America/New_York"


def message(*entities: Mapping[str, object], version: str = "1.0", **header: object) -> Msg:
    """A decoded `FeedMessage` under the 2015 schema, one entity per mapping.

    Round trips through the real encoder and decoder on purpose. Extra header
    fields are keyword arguments, because the rules that care about the header
    care about `timestamp` and `incrementality` specifically.
    """
    head: dict[str, object] = {"gtfs_realtime_version": version, **header}
    return decode(encode({"header": head, "entity": list(entities)}, SCHEMA), SCHEMA)


def entity(
    trip_update: Mapping[str, object] | None = None,
    vehicle: Mapping[str, object] | None = None,
    alert: Mapping[str, object] | None = None,
    entity_id: str = ENTITY_ID,
    is_deleted: bool | None = None,
) -> dict[str, object]:
    """One `FeedEntity`, in the shape upstream's own tests build.

    All three payloads on one entity, which is how `FeedMessageTest` does it and
    what makes the TripUpdate-then-VehiclePosition-then-Alert order observable.
    """
    built: dict[str, object] = {"id": entity_id}
    if trip_update is not None:
        built["trip_update"] = dict(trip_update)
    if vehicle is not None:
        built["vehicle"] = dict(vehicle)
    if alert is not None:
        built["alert"] = dict(alert)
    if is_deleted is not None:
        built["is_deleted"] = is_deleted
    return built


def stop_rows(stops: Mapping[str, int]) -> list[dict[str, str]]:
    """`stops.txt` rows, id to `location_type`, at a fixed coordinate.

    The coordinate is deliberately far from anything E028 or E029 would accept,
    so a geometry rule reading these rows fires rather than passing by accident.
    Those two build their own feed.
    """
    return [
        {
            "stop_id": stop_id,
            "stop_name": stop_id,
            "stop_lat": "40",
            "stop_lon": "-73",
            "location_type": str(location_type),
        }
        for stop_id, location_type in stops.items()
    ]


def trip_rows(trips: Mapping[str, str]) -> list[dict[str, str]]:
    """`trips.txt` rows, trip_id to route_id, on the fixture's one service."""
    return [
        {"route_id": route_id, "service_id": "WEEK", "trip_id": trip_id}
        for trip_id, route_id in trips.items()
    ]


def static_context(
    tmp_path: Path,
    tables: MutableMapping[str, list[dict[str, str]]] | None = None,
    *,
    ignore_shapes: bool = False,
) -> StaticContext:
    """A `StaticContext` built the way a real run builds one.

    Through `gtfsfixtures.build_feed` and a real archive on disk, never by
    handing `StaticContext` a dict, so what a rule reads is what the loader
    produced. Pass `tables` from `minimal_tables()` with the rows your cohort
    needs added.

    **The compat reader**, because every rule this module serves is an upstream
    rule ported from the jar, and the jar's static feed comes out of
    onebusaway's `GtfsReader`. A cohort testing a `spec` or `practice` rule that
    turns on the strict path's typing should call `load_static` itself and say
    why.

    **`ignore_shapes` goes to both halves, because a real run puts it in both.**
    `adapter._requested` drops `shapes.txt` from the tables it asks for, so
    `RawTables.shapes` is empty before `StaticContext.build` ever sees it, and
    the gate then shuts on an empty list for a second reason. An earlier version
    passed the flag only to `build`, which modelled the gate and not the loader;
    that was invisible while `shape_points` was the only shape structure and
    stopped being invisible when `shape_ids` arrived, which is read before the
    gate and so would have kept every id the flag is supposed to drop.
    `tripmodfixtures.static_feed` already did it this way.
    """
    return StaticContext.build(
        load_static_as_onebusaway(
            build_feed(tmp_path, tables if tables is not None else minimal_tables()),
            ignore_shapes=ignore_shapes,
        ),
        ignore_shapes=ignore_shapes,
    )


def context(
    tmp_path: Path,
    tables: MutableMapping[str, list[dict[str, str]]] | None = None,
    *,
    timezone: str = TESTAGENCY_TIMEZONE,
    clock: Reading = READING,
    source: str = "rt.pb",
    previous: Msg | None = None,
    previous_clock: Reading | None = None,
    ignore_shapes: bool = False,
) -> RuleContext:
    """One rule context. Everything but `tmp_path` has a default worth having.

    `memo` is left to the dataclass, which builds a fresh dict per context, so
    two calls never share a walk's cached events.
    """
    return RuleContext(
        static=static_context(tmp_path, tables, ignore_shapes=ignore_shapes),
        timezone=timezone,
        clock=clock,
        source=source,
        previous=previous,
        previous_clock=previous_clock,
    )


def occurrences(result: Iterable[Occurrence] | None) -> list[Occurrence]:
    """What a rule returned, as a list. `None` is a rule that returned early."""
    return [] if result is None else list(result)


def prefixes(result: Iterable[Occurrence] | None) -> list[str]:
    """Just the prefixes, in order, which is what most assertions are about."""
    return [found.prefix for found in occurrences(result)]


def minimal(**rows: Sequence[Mapping[str, str]]) -> dict[str, list[dict[str, str]]]:
    """`minimal_tables()` with rows appended, named by table without `.txt`.

    `minimal(stops=stop_rows({"A": 0}))` reads better at a call site than three
    lines of dictionary surgery, and every cohort needs the same three lines.
    """
    tables: dict[str, Any] = minimal_tables()
    for name, added in rows.items():
        tables[f"{name}.txt"] += [dict(row) for row in added]
    return tables
