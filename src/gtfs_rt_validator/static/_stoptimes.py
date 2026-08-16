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
integers for 1,998 values. `read_stop_times` pools them as it goes.

Nothing here decides anything, in `context.py`'s sense: it groups, sorts and
counts, and a feed that will not load has already failed in `adapter.py`.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any, NamedTuple

from gtfs_rt_validator.static._tables import Row
from gtfs_rt_validator.static.onebusaway import ROW_NUMBER


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


@dataclass(frozen=True, slots=True)
class StopTimeTable:
    """`stop_times.txt` as everything downstream needs it, from a single pass.

    Two consumers read this table and both read it once in file order, so both
    are served here rather than each walking a materialised list: `by_trip` is
    the structure the rules get, and the two `first_unknown_*` fields are what
    `runner/gate.py` needs to answer whether onebusaway's reader would have
    aborted the read on an unresolvable foreign key.

    The gate's question cannot be answered later, because answering it needs the
    row and the row is gone: only the offending one is kept, as
    `(_row_number, value)`, which is exactly what its message renders. `None`
    means the reference resolved for every row.

    Keeping the gate's half here is what allows the table never to be
    materialised. `tests/test_runner_gate.py` owns the precedence between this
    reference and the three the gate still scans for itself.
    """

    by_trip: dict[str, tuple[StopTime, ...]]
    first_unknown_trip_id: tuple[object, object] | None
    first_unknown_stop_id: tuple[object, object] | None

    def __len__(self) -> int:
        """Rows, not trips: this stands in for a list and is counted like one."""
        return sum(len(stop_times) for stop_times in self.by_trip.values())


#: What a run gets when `stop_times.txt` was not among the tables asked for.
#: Only `_load_tables` can reach that state, and only a test calls it with a set
#: that leaves the table out; the seven always include it.
EMPTY_STOP_TIMES = StopTimeTable(by_trip={}, first_unknown_trip_id=None, first_unknown_stop_id=None)


def _keys(rows: Iterable[Row], column: str) -> frozenset[str]:
    """One table's key column as a set, skipping blanks.

    Blanks are skipped because `gate.dangling_reference` skips them on the other
    side too: a row whose reference is absent is not a row whose reference is
    unresolvable, and onebusaway's reader only aborts on the second.
    """
    return frozenset(row[column] for row in rows if row.get(column) is not None)


def read_stop_times(
    rows: Iterable[Row], *, trips: Iterable[Row], stops: Iterable[Row]
) -> StopTimeTable:
    """One pass over `stop_times.txt`: the grouped records, and the gate's answer.

    `rows` is consumed lazily and never held, which is the point. The loaded
    dict for a row becomes garbage as soon as the next is read, where
    materialising the table first set a resident high water mark of about 2 GB
    on a real archive that no later compaction could take back.

    `trips` and `stops` are those two tables, already read, because the
    references this resolves point into them. That is why `adapter.py` reads
    this table last. A row whose own reference is absent is not dangling:
    `gate.dangling_reference` skips a `None` value and this reproduces that
    rather than reinventing it.

    Sorting every group is `mTripStopTimes`. Upstream sorts inside its trips
    loop, so a trip_id present here and absent from `trips.txt` would go
    unsorted; it cannot reach that state, its reader aborting the whole read on
    exactly the reference this records. The sibling does not abort (measured in
    `tests/test_static_context.py`), so sorting everything is both simpler and
    the only version that stays right on a feed upstream would have refused.
    `sorted` is stable, so rows sharing a `stop_sequence` keep file order.

    One pool serves all four columns rather than one per column, so a departure
    equal to an arrival is also one object. That is safe only because every one
    of them is an `int`, a `str` or `None`; a `float` column could not join
    them, `1.0` and `1` being equal and so interchangeable here.
    """
    trip_ids = _keys(trips, "trip_id")
    stop_ids = _keys(stops, "stop_id")
    first_trip: tuple[object, object] | None = None
    first_stop: tuple[object, object] | None = None
    grouped: dict[str, list[StopTime]] = {}
    pool: dict[Any, Any] = {}
    for row in rows:
        trip_id = row["trip_id"]
        if first_trip is None and trip_id is not None and trip_id not in trip_ids:
            first_trip = (row.get(ROW_NUMBER), trip_id)
        stop_id = row["stop_id"]
        if first_stop is None and stop_id is not None and stop_id not in stop_ids:
            first_stop = (row.get(ROW_NUMBER), stop_id)
        grouped.setdefault(trip_id, []).append(
            StopTime(
                pool.setdefault(row["stop_sequence"], row["stop_sequence"]),
                pool.setdefault(stop_id, stop_id),
                pool.setdefault(row["arrival_time"], row["arrival_time"]),
                pool.setdefault(row["departure_time"], row["departure_time"]),
            )
        )
    return StopTimeTable(
        by_trip={
            trip_id: tuple(sorted(group, key=lambda stop: stop.stop_sequence))
            for trip_id, group in grouped.items()
        },
        first_unknown_trip_id=first_trip,
        first_unknown_stop_id=first_stop,
    )


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
    `trips.txt` row declares reaches no route. `read_stop_times` keeps it,
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
