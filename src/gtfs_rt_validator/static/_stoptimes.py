"""`stop_times.txt`: the row this project keeps, and the three maps built from it.

Split off `_tables.py` at the file cap, by table rather than by kind, because
this one table is unlike the other six. It is the only one whose row count runs
into the millions, and the representation of a single row is therefore a memory
decision rather than a style one: on the 92,360-trip archive the figures here
come from, its 2,255,520 rows were 1,414 MB of the 1,684 MB a prepared feed held,
84% of the whole.

Two facts shape `StopTime` below, and both were measured rather than reasoned.

**Four of the twelve columns are read.** Every row was wrapped in a
key-recording dict and the entire suite run; the union across all of it is
`arrival_time`, `departure_time`, `stop_id`, `stop_sequence` and `trip_id`, the
last being the grouping key and so the dict key here rather than a field.

**No two rows shared a cell object.** The sibling builds one dict per row out of
`sqlite3.Row`, so 2,255,520 `stop_id` references arrived as 2,246,680 distinct
strings for 7,629 distinct values, and `arrival_time` as 2,254,712 distinct
integers for 1,998 values. `group_stop_times` pools them as it goes.

Nothing here decides anything, in `context.py`'s sense: it groups, sorts and
counts, and a feed that will not load has already failed in `adapter.py`.
"""

from __future__ import annotations

from typing import Any, NamedTuple

from gtfs_rt_validator.static._tables import Row


class StopTime(NamedTuple):
    """One `stop_times.txt` row, reduced to the columns anything actually reads.

    A `NamedTuple` rather than a slotted class because the groups it lives in
    are indexed and measured as well as read: `_position_of` in S006 wants an
    index, E023 wants element zero, and `walk_stop_time_updates` wants a length.
    Widening the field list is the change that would quietly undo the saving,
    which is why `tests/test_static_context_stop_times.py` pins it exactly.
    """

    stop_sequence: int
    stop_id: str
    arrival_time: int | None
    departure_time: int | None


def group_stop_times(rows: list[Row]) -> dict[str, tuple[StopTime, ...]]:
    """`mTripStopTimes`, sorted by `stop_sequence`.

    Upstream sorts inside its trips loop, so a trip_id present in
    `stop_times.txt` and absent from `trips.txt` would go unsorted. It cannot
    reach that state, because its reader aborts the entire read on an
    unresolvable foreign key. The sibling at `35fac77` does not abort (measured
    in `tests/test_static_context.py`), so sorting every group here is both
    simpler and the only version that stays right on a feed upstream would have
    refused outright. `sorted` is stable, so rows sharing a `stop_sequence` keep
    file order exactly as the in-place sort it replaced left them.

    **Cell values are pooled while grouping**, which is half the saving: 422 MB
    of records without it, 202 MB with. The pool is local to this call and dies
    with it, unlike `sys.intern`, which would hold one feed's stop ids for the
    life of a process that goes on to prepare another.

    One pool serves all four columns rather than one per column, so a departure
    equal to an arrival is also one object. That is safe only because every one
    of them is an `int`, a `str` or `None`; a `float` column could not join them,
    `1.0` and `1` being equal and so interchangeable here.
    """
    pool: dict[Any, Any] = {}
    grouped: dict[str, list[StopTime]] = {}
    for row in rows:
        grouped.setdefault(row["trip_id"], []).append(
            StopTime(
                pool.setdefault(row["stop_sequence"], row["stop_sequence"]),
                pool.setdefault(row["stop_id"], row["stop_id"]),
                pool.setdefault(row["arrival_time"], row["arrival_time"]),
                pool.setdefault(row["departure_time"], row["departure_time"]),
            )
        )
    return {
        trip_id: tuple(sorted(group, key=lambda stop: stop.stop_sequence))
        for trip_id, group in grouped.items()
    }


def build_route_stop_ids(
    trips: dict[str, Row], trip_stop_times: dict[str, tuple[StopTime, ...]]
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
    frozenset, which is `repeated_stops`'s convention below and is load bearing
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
        out.setdefault(row["route_id"], set()).update(stop.stop_id for stop in stop_times)
    return {route_id: frozenset(stop_ids) for route_id, stop_ids in out.items()}


def repeated_stops(trip_stop_times: dict[str, tuple[StopTime, ...]]) -> dict[str, list[str]]:
    """`GtfsMetadata.java:196-213`: every *repeat* visit, in stop_sequence order.

    A stop visited three times contributes two entries. The key is inserted only
    when the list is non-empty, so a trip that visits nothing twice is absent
    from the map rather than mapped to `[]`, and `containsKey` and `get` answer
    consistently.
    """
    out: dict[str, list[str]] = {}
    for trip_id, stop_times in trip_stop_times.items():
        seen: set[str] = set()
        duplicates: list[str] = []
        for stop in stop_times:
            if stop.stop_id in seen:
                duplicates.append(stop.stop_id)
            seen.add(stop.stop_id)
        if duplicates:
            out[trip_id] = duplicates
    return out
