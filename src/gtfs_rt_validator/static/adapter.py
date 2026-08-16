"""Read the seven GTFS tables a realtime run needs, and copy every row out.

The only module in this project that imports the sibling `gtfs-validator`, and
the only one that has to know a feed is a zip full of CSV rather than a set of
Python dicts. `tests/test_only_adapter_touches_the_sibling.py` asserts the
first half of that.

**Two readers, one per mode, because upstream's is not the sibling's.**
`BatchProcessor.java:36` and `:71` load the static feed with
`org.onebusaway.gtfs.serialization.GtfsReader`, which types almost nothing,
validates nothing and cannot fail a table. The sibling reproduces MobilityData's
canonical *static* validator, which is strict and typed by design and whose
`dependency_failed` faithfully mirrors `ValidatorUtil.invokeSingleFileValidators`
skipping a validator when an injected container is non-parsable. Both are right
about their own job, and a realtime run in compat has to have onebusaway's.

So `load_static` reads through `open_feed_view` and `load_static_as_onebusaway`
reads through `open_raw_view` and types the cells itself in
`static/onebusaway.py`. This is mode as descriptor, not a branch in a rule:
which reader runs is decided once, in `runner/gate.py`, and no rule can tell.
What it bought, measured: the original `tests/fixtures/gtfs/testagency.zip`
loads, so the differential no longer has to patch the archive its own goldens
were measured against; E024 reports the five padded `direction_id` cells the jar
reports; and a `frequencies.txt` with `headway_secs = 0` is validated rather
than refused.

Three measured behaviours of the sibling shape the strict path below, and
`tests/test_adapter.py` drives the sibling itself to pin each of them:

- **A typo in `tables=` is silent.** Names are matched case-sensitively against
  the archive with no validation of the argument, so `tables=["Stops.txt"]`
  loads nothing, raises nothing and reports no system error. Everything
  downstream would then see a feed with no stops. `_check_every_table_arrived`
  is the answer: ask, then assert that what arrived is what was asked for.
- **`LoadedFeed.tables` is not a usable-set.** It is every table the loader
  attempted, including tables that ended UNPARSABLE_ROWS and still raise on
  read, so the usable test is `view.dependency_failed(name)` and never
  membership in `.tables`.
- **The view dies with its block.** Afterwards a read raises
  `sqlite3.ProgrammingError`, not a typed sibling error. So `RawTables` holds
  lists of plain dicts, materialised inside the `with`, and nothing that leaves
  this module refers to the view.

`country_code` is left at its default: it is the phone-number country used for
field typing, and a realtime caller has no phone numbers. `threads` is left at 1
because passing `tables=` forces the sequential loader anyway.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

# `DependencyFailed` is a promised export as of the sibling's 0.1.2, alongside
# `open_raw_view`. It used to be reachable only through `rules.feedview` under a
# comment saying this module was on its own for importing it.
from gtfs_validator import DependencyFailed, LoadedFeed, open_feed_view, open_raw_view

from gtfs_rt_validator.static._stoptimes import (
    EMPTY_STOP_TIMES,
    StopTimeTable,
    read_stop_times,
)
from gtfs_rt_validator.static.onebusaway import (
    CellTypeError,
    typed_row_stream,
    typed_rows,
)

Row = dict[str, object]

# Canonical lowercase GTFS filenames, and the exact set a realtime run reads.
# No calendar table is needed: nothing in GTFS-Realtime validation asks which
# days a trip runs. All four of the sibling's REQUIRED_FILES are inside these
# seven, so nothing required is accidentally excluded.
SEVEN_TABLES = (
    "agency.txt",
    "stops.txt",
    "routes.txt",
    "trips.txt",
    "stop_times.txt",
    "shapes.txt",
    "frequencies.txt",
)

# The two of the seven a valid archive may omit. An absent optional file is
# genuinely empty (the sibling never raises for a file the archive did not
# ship), which is a different state from a file that shipped and failed to load.
OPTIONAL_TABLES = frozenset({"shapes.txt", "frequencies.txt"})

SHAPES = "shapes.txt"
STOP_TIMES = "stop_times.txt"


class StaticLoadError(Exception):
    """The static archive cannot supply a table this run needs.

    Not a notice. A realtime run validates *against* the static feed, so a feed
    that will not load is a failure of the run's inputs rather than a finding
    about them. Malformed realtime bytes are the opposite case and stay
    `DecodeError`.
    """


@dataclass(frozen=True)
class RawTables:
    """The seven tables, already copied out of the sibling's view.

    Rows are plain dicts keyed by column name, in file order, each carrying the
    synthetic `_row_number` the sibling assigns: 1-based *including the header*,
    so the first data row is 2. Field types after loading are the sibling's, not
    the CSV's: TIME is an `int` of seconds since midnight with past-midnight
    preserved, DATE is an `int` `YYYYMMDD`, an enum is a plain `int`, latitude
    and longitude are `float`, DECIMAL stays `str` to preserve scale, and an
    absent value is `None`. `tests/test_adapter.py` pins each of those.

    `shapes` is empty when `ignore_shapes` was set, which is indistinguishable
    here from an archive with no `shapes.txt`. That is deliberate: upstream's
    `-ignoreShapes` has exactly the same effect on everything downstream.

    **`stop_times` is the one exception to "a list of rows", and the reason is
    size.** It is the only table whose row count runs into the millions, and
    holding its rows as loaded dicts even briefly sets a resident high water mark
    a later compaction cannot take back: about 2 GB on an 18 MB archive of
    2,255,520 rows, against 306 MB when the rows are consumed as they arrive. So
    it is read straight into `_stoptimes.StopTimeTable`, whose docstring says
    what that has to carry for the gate to still be able to ask its question.
    """

    agency: list[Row]
    stops: list[Row]
    routes: list[Row]
    trips: list[Row]
    stop_times: StopTimeTable
    shapes: list[Row]
    frequencies: list[Row]


def _check_every_table_arrived(loaded: LoadedFeed, requested: tuple[str, ...]) -> None:
    """Assert that what came back is what was asked for, and say so when it is not.

    Four states per requested name, and only two of them are acceptable:

    - loaded and readable: fine;
    - loaded but `dependency_failed`, meaning the file shipped and at least one
      row would not type: a load failure, because the sibling will raise on
      every read of it and the surviving rows are invisible anyway;
    - absent from the archive and optional: fine, it reads as zero rows;
    - absent from the archive and not optional: a load failure. A mis-cased or
      misspelled name lands here too, which is the point.
    """
    for name in requested:
        if name in loaded.tables:
            if loaded.view.dependency_failed(name):
                raise StaticLoadError(
                    f"{name} is in the archive but did not load; the static feed is unusable"
                )
            continue
        if name in OPTIONAL_TABLES and loaded.view.is_missing(name):
            continue
        if loaded.view.is_missing(name):
            raise StaticLoadError(f"{name} is not in the archive")
        raise StaticLoadError(f"{name} was requested but the loader did not return it")


def _load_tables(path: Path, tables: tuple[str, ...]) -> tuple[dict[str, list[Row]], StopTimeTable]:
    """Load exactly `tables` and return every row of each, copied out.

    Private, and takes the table names, so a test can hand it a deliberately
    mis-cased name and watch the guard fire. `load_static` is the only caller
    that matters and always passes the seven.

    `list(...)` inside the `with` is the whole copy-out: the sibling builds a
    fresh dict per row and every value is a `str`, `int`, `float` or `None`, so
    materialising the iterator leaves nothing pointing at the SQLite store.

    `stop_times.txt` is the exception and is read last, consumed as it arrives
    rather than listed. `RawTables` says why, and last is not incidental: the
    references its reader resolves are into `trips.txt` and `stops.txt`, so
    those two have to have been read already.
    """
    with open_feed_view(path, tables=list(tables)) as loaded:
        _check_every_table_arrived(loaded, tables)
        out: dict[str, list[Row]] = {}
        for name in tables:
            if name == STOP_TIMES:
                continue
            try:
                out[name] = list(loaded.view.rows(name))
            except DependencyFailed as exc:
                # Unreachable by construction: the guard above already rejected
                # every name that can raise here. Kept so that a future change
                # to either side surfaces as this project's error rather than as
                # the sibling's private one leaking to a caller.
                raise StaticLoadError(f"{name} could not be read: {exc}") from exc
        if STOP_TIMES not in tables:
            return out, EMPTY_STOP_TIMES
        try:
            stop_times = read_stop_times(
                loaded.view.rows(STOP_TIMES),
                trips=out.get("trips.txt", []),
                stops=out.get("stops.txt", []),
            )
        except DependencyFailed as exc:
            raise StaticLoadError(f"{STOP_TIMES} could not be read: {exc}") from exc
        return out, stop_times


def _raw_tables(path: Path, tables: tuple[str, ...]) -> tuple[dict[str, list[Row]], StopTimeTable]:
    """The same seven tables, read as onebusaway reads them.

    No `_check_every_table_arrived`: there is nothing for it to check. The raw
    view cannot fail a table, a mis-cased name raises `KeyError` from the view
    itself, and an absent file reads as no rows, which is what onebusaway's
    reader does with an optional file it was not handed.

    A *required* file the archive lacks is still a load failure, and it is
    upstream's failure too: `GtfsReader` throws on a missing required entry, so
    the jar dies before validating anything and writes no results at all. Four
    of the seven are required, and the raw view has no opinion about which, so
    the question is asked here.
    """
    out: dict[str, list[Row]] = {}
    with open_raw_view(path, tables=list(tables)) as raw:
        for name in tables:
            if name == STOP_TIMES:
                continue
            if raw.is_missing(name):
                if name in OPTIONAL_TABLES:
                    out[name] = []
                    continue
                raise StaticLoadError(f"{name} is not in the archive")
            try:
                out[name] = typed_rows(name, raw.rows(name))
            except CellTypeError as exc:
                # onebusaway throws CsvEntityIOException here and `Main` catches
                # only IOException | NoSuchAlgorithmException, so upstream dies
                # with a stack trace and writes nothing. So does this.
                raise StaticLoadError(f"{name} could not be read: {exc}") from exc
        if raw.is_missing(STOP_TIMES):
            raise StaticLoadError(f"{STOP_TIMES} is not in the archive")
        try:
            stop_times = read_stop_times(
                typed_row_stream(STOP_TIMES, raw.rows(STOP_TIMES)),
                trips=out.get("trips.txt", []),
                stops=out.get("stops.txt", []),
            )
        except CellTypeError as exc:
            raise StaticLoadError(f"{STOP_TIMES} could not be read: {exc}") from exc
    return out, stop_times


def _requested(ignore_shapes: bool) -> tuple[str, ...]:
    return tuple(name for name in SEVEN_TABLES if not (ignore_shapes and name == SHAPES))


def _assembled(loaded: tuple[dict[str, list[Row]], StopTimeTable]) -> RawTables:
    rows, stop_times = loaded
    return RawTables(
        agency=rows.get("agency.txt", []),
        stops=rows.get("stops.txt", []),
        routes=rows.get("routes.txt", []),
        trips=rows.get("trips.txt", []),
        stop_times=stop_times,
        shapes=rows.get(SHAPES, []),
        frequencies=rows.get("frequencies.txt", []),
    )


def load_static(path: Path, *, ignore_shapes: bool = False) -> RawTables:
    """Load a GTFS archive into plain dicts, or raise `StaticLoadError`.

    The strict, typed read, and what modern mode uses. Compat uses
    `load_static_as_onebusaway` instead; see this module's docstring for why the
    two exist.

    `ignore_shapes` skips `shapes.txt` entirely rather than loading and
    discarding it, which is where the flag's cost saving lives: on a synthetic
    33 MB feed, dropping `shapes.txt` saved about 31% of load time against about
    12% for dropping the other 25 tables combined.
    """
    return _assembled(_load_tables(path, _requested(ignore_shapes)))


def load_static_as_onebusaway(path: Path, *, ignore_shapes: bool = False) -> RawTables:
    """The same archive as `GtfsReader` would have read it, or `StaticLoadError`.

    Same `RawTables` shape and same cell types, with two differences that are
    the whole reason for the second path: `direction_id` is the CSV's own text
    rather than an enum, and no table can be lost to a cell that would not type.

    `ignore_shapes` means what it means above. It is cheaper here for a
    different reason: the raw view reads a table only when it is asked for, so
    the skipped file is never opened.
    """
    return _assembled(_raw_tables(path, _requested(ignore_shapes)))
