"""How `trip_stop_times` is represented, which is 1.2 GB of a real feed.

`tests/test_static_context.py` owns what the structure *means*: the sort by
`stop_sequence`, the orphan trip the sibling does not reject, the empty-list
convention. Nothing there depends on the rows being dicts, and this file is why
they are not.

`stop_times.txt` is the largest table in any real archive and the only one whose
row count runs into the millions: 2,255,520 rows on the 92,360-trip archive the
memory figures come from. Keeping each of those as the loaded dict cost 1,414 MB
of the 1,684 MB a prepared feed held, 84% of the whole, for a table of which
**four columns are ever read**. That claim is not a reading of the source; it was
measured, by wrapping every row in a key-recording dict and running the entire
suite, and the union across all of it is `arrival_time`, `departure_time`,
`stop_id`, `stop_sequence` and `trip_id`, the last of which is the grouping key
and so is the dict key here rather than a field.

The second half is that the values were not shared either. The sibling builds
one dict per row out of `sqlite3.Row`, so every cell is a fresh object: those
2,255,520 `stop_id` references were 2,246,680 distinct strings for 7,629 distinct
values, and `arrival_time` was 2,254,712 distinct integers for 1,998 values.
Pooling them while grouping takes the four-field records from 422 MB to 202 MB,
and the pool is local to the build so nothing it held outlives it.

The pool is deliberately not `sys.intern`: that would retain every feed's stop
ids for the life of the process, which is the opposite of the point when a
service prepares one feed after another.
"""

from __future__ import annotations

import weakref

from gtfs_rt_validator.static._stoptimes import read_stop_times
from gtfsfixtures import minimal_tables
from test_static_context import context_from, stop_time, trip


def a_feed_visiting(*stops: tuple[str, str, str]):
    """A feed whose `stop_times.txt` is exactly the given (trip, stop, seq)."""
    tables = minimal_tables()
    tables["trips.txt"] = [trip("T1"), trip("T2")]
    tables["stops.txt"] = [
        {"stop_id": stop_id, "stop_name": stop_id, "stop_lat": "27.9", "stop_lon": "-82.4"}
        for stop_id in sorted({stop for _, stop, _ in stops})
    ]
    tables["stop_times.txt"] = [stop_time(t, s, q) for t, s, q in stops]
    return tables


def test_a_stop_time_carries_the_four_columns_and_not_the_other_eight(tmp_path):
    """The representation, stated as what a rule can reach.

    A real `stop_times.txt` carries twelve columns; this asserts the four that
    survive rather than asserting a size, because the saving is a consequence of
    the field list and the field list is the thing a future reader would widen
    without noticing what it costs.
    """
    ctx = context_from(tmp_path, a_feed_visiting(("T1", "S1", "1")))

    (first,) = ctx.trip_stop_times["T1"]

    assert first.stop_sequence == 1
    assert first.stop_id == "S1"
    assert first.arrival_time == 25200, "07:00:00 as seconds after midnight"
    assert first.departure_time == 25200
    assert first._fields == ("stop_sequence", "stop_id", "arrival_time", "departure_time")


def test_equal_cell_values_are_one_object_across_the_whole_table(tmp_path):
    """Identity again, and for the same reason as the shape polylines.

    Two trips calling at the same stop at the same time hold one string and one
    integer between them, not four objects. `==` cannot see the difference,
    which is exactly why the old representation could carry 2.2 million
    duplicate strings without any test noticing.
    """
    tables = a_feed_visiting(("T1", "S1", "1"), ("T2", "S1", "1"))

    ctx = context_from(tmp_path, tables)

    one = ctx.trip_stop_times["T1"][0]
    two = ctx.trip_stop_times["T2"][0]
    assert one.stop_id is two.stop_id
    assert one.arrival_time is two.arrival_time
    assert one.arrival_time is one.departure_time, "one pool, so equal times share too"


def test_the_group_is_a_tuple_because_a_caller_can_reach_it(tmp_path):
    """`PreparedFeed.static` is public and may outlive hundreds of runs, so the
    same argument that made the shape polylines tuples applies here."""
    ctx = context_from(tmp_path, a_feed_visiting(("T1", "S1", "1"), ("T1", "S2", "2")))

    assert isinstance(ctx.trip_stop_times["T1"], tuple)


def a_row(trip_id: str, stop_id: str, sequence: int, row_number: int) -> dict[str, object]:
    return {
        "trip_id": trip_id,
        "stop_id": stop_id,
        "stop_sequence": sequence,
        "arrival_time": 25200,
        "departure_time": 25200,
        "_row_number": row_number,
    }


class WatchedRow(dict):
    """A row that can be weakly referenced, so a test can watch it be released."""

    __slots__ = ("__weakref__",)


def test_no_more_than_a_handful_of_loaded_rows_are_alive_at_once():
    """The property the whole streaming design rests on, and the hard half of it.

    Reading in one pass is necessary and is not sufficient: `list(rows)` at the
    top of the reader would satisfy a one-shot iterator perfectly well and put
    the entire table back in memory. What has to be true is that a row is
    released once its record exists, so this watches them go.

    The count matters because the cost is a high water mark and not a retention.
    Materialising `stop_times.txt` on a real archive left about 2 GB resident
    against 618 MB streamed, and no later compaction takes that back: the freed
    pages are reusable by the process and are not returned to the operating
    system, so a peak once reached is paid for the life of a long-lived service.

    Two rows are expected alive: the one the generator has just built and the one
    the reader is converting. The bound is loose because the exact number is an
    implementation detail; 200 against a bound of 5 is the distinction being
    drawn, and a reader that kept them all would report 200.
    """
    handed_out: list[weakref.ref] = []
    watched: list[int] = []

    def stream():
        for sequence in range(200):
            row = WatchedRow(a_row("T1", "S1", sequence, sequence + 2))
            handed_out.append(weakref.ref(row))
            watched.append(sum(1 for ref in handed_out if ref() is not None))
            yield row

    table = read_stop_times(stream(), trips=[{"trip_id": "T1"}], stops=[{"stop_id": "S1"}])

    assert len(table.by_trip["T1"]) == 200
    assert len(table) == 200, "counted in rows, standing in for the list it replaced"
    assert max(watched) <= 5, f"loaded rows alive at once peaked at {max(watched)} of 200"


def test_the_offending_row_is_kept_where_the_table_is_not():
    """The gate's question, answered while the rows still exist.

    `runner/gate.py` used to scan the loaded table for this. It cannot now, so
    the first offending row per reference is recorded during the read: the row
    number and the value, which is exactly what its message renders. Later rows
    breaking the same reference are not kept, upstream reporting only the first.
    """
    rows = [a_row("GHOST", "S1", 1, 2), a_row("T1", "NOWHERE", 1, 3), a_row("T1", "ALSO", 2, 4)]

    table = read_stop_times(iter(rows), trips=[{"trip_id": "T1"}], stops=[{"stop_id": "S1"}])

    assert table.first_unknown_trip_id == (2, "GHOST")
    assert table.first_unknown_stop_id == (3, "NOWHERE"), "the first, not the last"


def test_a_reference_that_resolves_for_every_row_records_nothing():
    """The control, so the two fields above cannot be passing by always firing."""
    rows = [a_row("T1", "S1", 1, 2)]

    table = read_stop_times(iter(rows), trips=[{"trip_id": "T1"}], stops=[{"stop_id": "S1"}])

    assert table.first_unknown_trip_id is None
    assert table.first_unknown_stop_id is None


def test_a_blank_reference_is_not_a_dangling_one():
    """`gate.dangling_reference` skips a `None` value, and this reproduces it
    rather than reinventing it: an absent reference is not an unresolvable one,
    and onebusaway's reader only aborts the read on the second."""
    rows = [a_row("T1", None, 1, 2)]

    table = read_stop_times(iter(rows), trips=[{"trip_id": "T1"}], stops=[])

    assert table.first_unknown_stop_id is None


def test_pooling_does_not_disturb_the_sort_or_lose_a_row(tmp_path):
    """The control. Sharing objects must not merge rows that happen to agree.

    Both of T1's calls at S1 are real visits, and a pool that deduplicated
    *records* rather than values would silently drop one and take E009's
    repeated-stop detection with it.
    """
    tables = a_feed_visiting(("T1", "S1", "2"), ("T1", "S2", "3"), ("T1", "S1", "1"))

    ctx = context_from(tmp_path, tables)

    assert [stop.stop_id for stop in ctx.trip_stop_times["T1"]] == ["S1", "S1", "S2"]
    assert [stop.stop_sequence for stop in ctx.trip_stop_times["T1"]] == [1, 2, 3]
    assert ctx.trips_with_multi_stops["T1"] == ["S1"]
