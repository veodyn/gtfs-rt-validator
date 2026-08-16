"""Build a GTFS zip from dicts, so a test can state the feed it needs inline.

A module of plain functions rather than a pytest fixture, for two reasons. Every
test here needs a *different* feed, so a fixture would have to be a
factory-fixture anyway, and the extra indirection buys nothing. And the static
context tests (`tests/test_static_context.py`, the shapes gate in
`tests/test_static_context_geometry.py`) build their own odd shapes from another
test module, which is an import here and a `conftest.py` dance otherwise.

The feeds are deliberately tiny. The sibling's own zips are 1-2 row hand-built
feeds and no real feed is committed anywhere in this project, so anything that
has to hold a specific shape (four shape points, no `agency_id`, no
coordinates) gets built by the test that cares.
"""

from __future__ import annotations

import csv
import io
import struct
import zipfile
from collections.abc import Mapping, Sequence
from pathlib import Path

Row = Mapping[str, object]
Tables = Mapping[str, Sequence[Row]]

# Fixed fields of a zip local file header, from APPNOTE 4.3.7: the signature and
# the two length fields that say where the entry's payload begins.
_LOCAL_HEADER_FIXED = 30
_NAME_AND_EXTRA_LENGTHS = 26


def _header(rows: Sequence[Row], columns: Sequence[str] | None) -> list[str]:
    """Column order: the caller's if given, else first-seen across the rows."""
    if columns is not None:
        return list(columns)
    seen: dict[str, None] = {}
    for row in rows:
        for key in row:
            seen[key] = None
    return list(seen)


def as_csv(rows: Sequence[Row], columns: Sequence[str] | None = None) -> str:
    """One GTFS table as CSV text. `None` writes an empty cell, which is absent."""
    header = _header(rows, columns)
    if not header:
        raise ValueError("a table needs at least one column: pass columns= for a header-only file")
    out = io.StringIO(newline="")
    writer = csv.DictWriter(out, fieldnames=header, lineterminator="\n", extrasaction="raise")
    writer.writeheader()
    for row in rows:
        writer.writerow({name: "" if row.get(name) is None else str(row[name]) for name in header})
    return out.getvalue()


def build_feed(
    directory: Path,
    tables: Tables,
    *,
    name: str = "feed.zip",
    columns: Mapping[str, Sequence[str]] | None = None,
) -> Path:
    """Write `tables` as a GTFS zip under `directory` and return its path.

    Keys are canonical lowercase filenames (`stops.txt`). A table the caller
    omits is absent from the archive, which is not the same as present and
    empty; pass `columns={"shapes.txt": [...]}` with an empty row list for the
    header-only case.
    """
    path = directory / name
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
        for filename, rows in tables.items():
            per_file = None if columns is None else columns.get(filename)
            archive.writestr(filename, as_csv(rows, per_file))
    return path


def corrupt_entry_payload(path: Path, filename: str) -> Path:
    """Flip one byte inside `filename`'s compressed payload, leaving its CRC stale.

    The archive still lists the entry and still opens, so the sibling counts the
    file as present and hands it to `_load_table`; the damage only surfaces when
    the deflate stream is read to its end and Python's `zipfile` compares the
    recorded CRC-32 against what came out. Measured against `gtfs-validator` at
    `35fac77`: that raises `zipfile.BadZipFile` from inside the loader, which
    `load_tables` catches, and which therefore drops the table back out of
    `LoadedFeed.tables`. See `test_adapter.py` for the four states it produces.

    Byte 5 of the payload is inside the deflate stream's compressed data for
    every table these fixtures build (the smallest is well over a hundred bytes),
    so the read fails on the checksum rather than on a malformed block header.
    """
    raw = bytearray(path.read_bytes())
    with zipfile.ZipFile(path) as archive:
        start = archive.getinfo(filename).header_offset
    name_length, extra_length = struct.unpack_from("<HH", raw, start + _NAME_AND_EXTRA_LENGTHS)
    payload = start + _LOCAL_HEADER_FIXED + name_length + extra_length
    raw[payload + 5] ^= 0xFF
    path.write_bytes(bytes(raw))
    return path


def minimal_tables() -> dict[str, list[dict[str, object]]]:
    """A small feed that loads clean, as a fresh mutable copy each call.

    One agency, two stops, one route, one trip over four shape points, and a
    frequency. `arrival_time` is past midnight on purpose: `25:05:00` is the
    measured TIME case and every caller of this helper gets it for free.
    """
    return {
        "agency.txt": [
            {
                "agency_id": "A1",
                "agency_name": "Test Transit",
                "agency_url": "https://example.com",
                "agency_timezone": "America/New_York",
            }
        ],
        "stops.txt": [
            {
                "stop_id": "S1",
                "stop_name": "First",
                "stop_lat": "27.95",
                "stop_lon": "-82.45",
                "location_type": "0",
            },
            {
                "stop_id": "S2",
                "stop_name": "Second",
                "stop_lat": "28.05",
                "stop_lon": "-82.35",
                "location_type": "0",
            },
        ],
        "routes.txt": [
            {
                "route_id": "R1",
                "agency_id": "A1",
                "route_short_name": "1",
                "route_long_name": "The One",
                "route_type": "3",
            }
        ],
        "trips.txt": [
            {
                "trip_id": "T1",
                "route_id": "R1",
                "service_id": "SVC1",
                "direction_id": "0",
                "shape_id": "SH1",
            }
        ],
        "stop_times.txt": [
            {
                "trip_id": "T1",
                "arrival_time": "25:05:00",
                "departure_time": "25:05:00",
                "stop_id": "S1",
                "stop_sequence": "1",
                "pickup_type": "0",
            },
            {
                "trip_id": "T1",
                "arrival_time": "25:20:00",
                "departure_time": "25:20:00",
                "stop_id": "S2",
                "stop_sequence": "2",
                "pickup_type": "0",
            },
        ],
        "shapes.txt": [
            {
                "shape_id": "SH1",
                "shape_pt_lat": lat,
                "shape_pt_lon": lon,
                "shape_pt_sequence": str(sequence),
            }
            for sequence, (lat, lon) in enumerate(
                [
                    ("27.95", "-82.45"),
                    ("27.98", "-82.42"),
                    ("28.01", "-82.39"),
                    ("28.05", "-82.35"),
                ],
                start=1,
            )
        ],
        "frequencies.txt": [
            {
                "trip_id": "T1",
                "start_time": "06:00:00",
                "end_time": "10:00:00",
                "headway_secs": "600",
                "exact_times": "1",
            }
        ],
    }
