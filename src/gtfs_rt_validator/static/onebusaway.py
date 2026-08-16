"""Type raw GTFS cells the way `org.onebusaway.gtfs`'s reader does.

`BatchProcessor.java:36` and `:71` load the static feed with
`org.onebusaway.gtfs.serialization.GtfsReader`, not with anything MobilityData
wrote, and that reader is lenient and thinly typed. Reproducing the jar means
reproducing *its* loader, so this module takes the sibling's raw string cells
and applies onebusaway's own types, which is a different and much shorter list
than the canonical GTFS schema's.

Every type below was read off `onebusaway-gtfs-1.3.87.jar`, the version the
pinned pom resolves, with `javap -p` on the model classes rather than from
memory or from the GTFS reference:

    Trip.directionId        java.lang.String   <- the one that matters most
    Stop.lat, Stop.lon      double
    Stop.locationType       int
    StopTime.arrivalTime    int   (seconds, via StopTimeFieldMappingFactory)
    StopTime.stopSequence   int
    ShapePoint.lat, .lon    double
    ShapePoint.sequence     int
    Frequency.startTime     int   (seconds)
    Frequency.headwaySecs   int   (no positivity constraint anywhere)
    Frequency.exactTimes    int

`direction_id` is the whole reason this file exists. `TripDescriptorValidator`
compares `gtfsTrip.getDirectionId()` against `String.valueOf(directionId)`, so
`00`, `01`, `+0` and `0.0` are all cells the jar reports E024 for and a typed
column cannot: the text is gone by the time the comparison runs.

**Only the columns this project reads are typed.** Anything else passes through
as text, because a type nothing consumes buys nothing and adds a way to refuse
an archive the jar accepts. The list is `RawTables`' documented contract, and
`tests/test_onebusaway_types.py` pins each entry against the model field above.

A cell that will not convert is a `CellTypeError`. onebusaway throws
`CsvEntityIOException` there and `Main` catches only
`IOException | NoSuchAlgorithmException`, so the jar dies before validating
anything and writes no results for any file; `adapter.py` turns this into the
`StaticLoadError` that produces the same silence.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Iterator, Mapping

__all__ = ["ROW_NUMBER", "CellTypeError", "typed_row_stream", "typed_rows"]

Row = dict[str, object]

#: The synthetic column the sibling's parser puts on every row: the physical
#: line, 1-based including the header. Carried through untouched.
ROW_NUMBER = "_row_number"

#: `Integer.parseInt`'s grammar. Python's `int()` also accepts underscores and
#: non-ASCII digits, neither of which Java takes.
_JAVA_INT = re.compile(r"\A[+-]?[0-9]+\Z")

#: `Double.parseDouble`'s grammar minus the hex-float form no feed uses. The
#: specials are case sensitive in Java: `NaN` parses and `nan` throws.
_JAVA_DOUBLE = re.compile(
    r"\A[+-]?(?:NaN|Infinity|(?:[0-9]+\.?[0-9]*|\.[0-9]+)(?:[eE][+-]?[0-9]+)?[fFdD]?)\Z"
)

#: `StopTimeFieldMappingFactory._pattern`, verbatim: `^(-{0,1}\d+):(\d{2}):(\d{2})$`.
#: Read out of the class file's static initialiser, so it is the jar's own
#: grammar rather than a plausible one. Note what it does *not* do: no cap on
#: the hour, no upper bound on minutes or seconds, and a leading minus allowed.
_ONEBUSAWAY_TIME = re.compile(r"\A(-{0,1}[0-9]+):([0-9]{2}):([0-9]{2})\Z")

#: `Integer.parseInt` throws outside 32 bits where Python's `int` would not.
_INT32_MIN = -2147483648
_INT32_MAX = 2147483647

TEXT = "text"
INTEGER = "integer"
DOUBLE = "double"
SECONDS = "seconds"


class CellTypeError(ValueError):
    """A cell onebusaway's reader would have thrown on. See the module docstring."""


#: Per table, the columns this project reads and the onebusaway type of each.
#: A column absent from a table's map is text; a column absent from the file is
#: `None`, so a row always answers for every name here.
COLUMNS: dict[str, dict[str, str]] = {
    "agency.txt": {
        "agency_id": TEXT,
        "agency_name": TEXT,
        "agency_timezone": TEXT,
    },
    "stops.txt": {
        "stop_id": TEXT,
        "stop_lat": DOUBLE,
        "stop_lon": DOUBLE,
        "location_type": INTEGER,
    },
    "routes.txt": {
        "route_id": TEXT,
        "agency_id": TEXT,
    },
    "trips.txt": {
        "trip_id": TEXT,
        "route_id": TEXT,
        "shape_id": TEXT,
        # A String upstream, and the entire point of this module.
        "direction_id": TEXT,
    },
    "stop_times.txt": {
        "trip_id": TEXT,
        "stop_id": TEXT,
        "stop_sequence": INTEGER,
        "arrival_time": SECONDS,
        "departure_time": SECONDS,
    },
    "shapes.txt": {
        "shape_id": TEXT,
        "shape_pt_lat": DOUBLE,
        "shape_pt_lon": DOUBLE,
        "shape_pt_sequence": INTEGER,
    },
    "frequencies.txt": {
        "trip_id": TEXT,
        "start_time": SECONDS,
        "end_time": SECONDS,
        # Required and POSITIVE in the canonical schema, a plain `int` here.
        # That difference alone is an archive the jar validates and the strict
        # path refuses; `tests/test_jar_frequency_divergence.py` measured it.
        "headway_secs": INTEGER,
        "exact_times": INTEGER,
    },
}


#: Per table, the cells that may not be absent or blank.
#:
#: Short by design: it holds the four this project would *crash* on, not every
#: field onebusaway declares required. `_tables.py` sorts stop_times by
#: `stop_sequence` and shape points by `shape_pt_sequence`, and builds a
#: bounding box out of `shape_pt_lat` and `shape_pt_lon`, none of which is
#: defined for `None`.
#:
#: All four are required upstream as well, read off the class file rather than
#: guessed: `ShapePoint.sequence`, `.lat` and `.lon` carry a `@CsvField` with no
#: `optional = true`, and `StopTime.stopSequence` carries no annotation at all,
#: which is csv-entities' required default. `Stop.lat` and `Stop.lon` *are*
#: `optional = true`, which is why they are not here and why `build_stops`
#: checks both before using either.
REQUIRED: dict[str, frozenset[str]] = {
    "stop_times.txt": frozenset({"stop_sequence"}),
    "shapes.txt": frozenset({"shape_pt_sequence", "shape_pt_lat", "shape_pt_lon"}),
}


def _text(value: str) -> object:
    """A blank cell is absent, which is `null` on the Java side of every model.

    csv-entities never calls a setter for an empty value, so an object field
    keeps its `null` and a primitive keeps its zero. `None` here is the sibling
    typed loader's answer for the same cell, so nothing downstream has to know
    which reader produced the row.
    """
    return None if value == "" else value


def _integer(value: str) -> object:
    if value == "":
        return None
    if not _JAVA_INT.match(value):
        raise CellTypeError(f"{value!r} is not a Java integer literal")
    parsed = int(value)
    if not (_INT32_MIN <= parsed <= _INT32_MAX):
        raise CellTypeError(f"{value!r} is outside the signed 32-bit range")
    return parsed


def _double(value: str) -> object:
    if value == "":
        return None
    if not _JAVA_DOUBLE.match(value):
        raise CellTypeError(f"{value!r} is not a Java double literal")
    # Java allows a trailing type suffix that Python's float() does not.
    return float(value.rstrip("fFdD"))


def _seconds(value: str) -> object:
    """`StopTimeFieldMappingFactory.getStringAsSeconds`, arithmetic included.

    The Java is `ss + 60 * (mm + 60 * hh)` with no normalisation, so a negative
    hour carries the sign into the whole result and `10:99:99` is a perfectly
    good time worth 39,939 seconds. Both are reproduced rather than corrected:
    a stricter parser here would refuse a feed the jar reads.
    """
    if value == "":
        return None
    match = _ONEBUSAWAY_TIME.match(value)
    if match is None:
        raise CellTypeError(f"{value!r} is not HH:MM:SS")
    hours, minutes, seconds = (int(group) for group in match.groups())
    return seconds + 60 * (minutes + 60 * hours)


_CONVERT = {TEXT: _text, INTEGER: _integer, DOUBLE: _double, SECONDS: _seconds}


def typed_row_stream(table: str, rows: Iterable[Mapping[str, str]]) -> Iterator[Row]:
    """The same typing, one row at a time and nothing kept.

    The generator form exists for `stop_times.txt` alone, whose row count runs
    into the millions: `adapter.py` consumes it into the compact records
    `_stoptimes.py` defines, so the loaded dict for a row is garbage as soon as
    the next one is read. Materialising that table instead set a resident high
    water mark of about 2 GB on a real archive, which no later compaction can
    take back, the allocator not returning freed pages to the operating system.

    **It must be consumed inside the caller's `with`.** The archive closes with
    that block and this reads through it, which is exactly the hazard
    `typed_rows` below avoids by materialising. Every other table takes that
    safer form, being small enough that it costs nothing.
    """
    declared = COLUMNS[table]
    required = REQUIRED.get(table, frozenset())
    for raw in rows:
        row: Row = {}
        for name, value in raw.items():
            if name == ROW_NUMBER:
                row[name] = value
                continue
            try:
                row[name] = _CONVERT[declared.get(name, TEXT)](value)
            except CellTypeError as exc:
                raise CellTypeError(
                    f"{table} row {raw.get(ROW_NUMBER)}, column {name}: {exc}"
                ) from exc
        for name in declared:
            row.setdefault(name, None)
        for name in required:
            if row[name] is None:
                raise CellTypeError(
                    f"{table} row {raw.get(ROW_NUMBER)} has no {name}, which onebusaway "
                    f"requires and this project sorts or measures by"
                )
        yield row


def typed_rows(table: str, rows: Iterable[Mapping[str, str]]) -> list[Row]:
    """Every raw row of one table, with this project's columns typed.

    Materialised rather than yielded because the caller is copying the feed out
    of a context manager anyway, and a generator would let the archive close
    underneath it. `typed_row_stream` is the generator, for the one table where
    holding every row at once is the dominant cost.
    """
    return list(typed_row_stream(table, rows))
