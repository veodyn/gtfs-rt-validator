"""What the sibling actually does, pinned before anything is built on top of it.

Every behaviour asserted here was measured against `gtfs-validator` at commit
`35fac77`, and this module is the only record of that measurement. The three
that surprise are: a typo in `tables=` is silent, `LoadedFeed.tables` includes
tables that still raise on read, and `DependencyFailed` fires only when the
archive actually shipped the file.

This module imports `gtfs_validator` directly in a few places, on purpose. The
one-importer rule is about `src/`; a test that pins the sibling's own behaviour
has to be able to see it, and if it could not, the adapter's guards would be
asserted only against themselves.
"""

import sqlite3

import pytest

from gtfs_rt_validator.static.adapter import (
    OPTIONAL_TABLES,
    SEVEN_TABLES,
    RawTables,
    StaticLoadError,
    _load_tables,
    load_static,
)
from gtfsfixtures import build_feed, corrupt_entry_payload, minimal_tables


def test_the_seven_tables_are_the_canonical_lowercase_names():
    assert SEVEN_TABLES == (
        "agency.txt",
        "stops.txt",
        "routes.txt",
        "trips.txt",
        "stop_times.txt",
        "shapes.txt",
        "frequencies.txt",
    )
    assert frozenset({"shapes.txt", "frequencies.txt"}) == OPTIONAL_TABLES


def test_load_static_returns_every_table_as_a_list_of_plain_dicts(tmp_path):
    raw = load_static(build_feed(tmp_path, minimal_tables()))

    assert isinstance(raw, RawTables)
    assert [len(rows) for rows in (raw.agency, raw.stops, raw.routes, raw.trips)] == [1, 2, 1, 1]
    assert [len(raw.stop_times), len(raw.shapes), len(raw.frequencies)] == [2, 4, 1]
    for row in raw.stops:
        assert type(row) is dict


def test_a_mis_cased_table_name_is_silent_in_the_sibling(tmp_path):
    """The trap the adapter exists to close, asserted against the sibling itself.

    `tables=` is matched case-sensitively against the archive's filenames with
    no validation of the argument, so a typo loads nothing, reports no system
    error, and leaves `dependency_failed` answering False because the name is
    not one of the sibling's four REQUIRED_FILES.
    """
    from gtfs_validator import open_feed_view

    path = build_feed(tmp_path, minimal_tables())
    with open_feed_view(path, tables=["agency.txt", "Stops.txt"]) as loaded:
        assert "Stops.txt" not in loaded.tables
        assert loaded.system_errors.in_order() == ()
        assert loaded.view.dependency_failed("Stops.txt") is False
        assert list(loaded.view.rows("Stops.txt")) == []


def test_the_adapter_refuses_a_table_name_that_came_back_empty(tmp_path):
    path = build_feed(tmp_path, minimal_tables())

    with pytest.raises(StaticLoadError) as caught:
        _load_tables(path, ("agency.txt", "Stops.txt"))

    assert "Stops.txt" in str(caught.value)


def test_an_absent_optional_file_is_empty_rather_than_a_failure(tmp_path):
    """`DependencyFailed` never fires for a file the archive did not ship.

    A feed with no `shapes.txt` reads as zero rows, so absence and breakage are
    different states and only breakage is a load failure.
    """
    tables = minimal_tables()
    del tables["shapes.txt"]
    del tables["frequencies.txt"]

    raw = load_static(build_feed(tmp_path, tables))

    assert raw.shapes == []
    assert raw.frequencies == []
    assert len(raw.stop_times) == 2


def test_an_absent_required_file_is_a_load_failure(tmp_path):
    tables = minimal_tables()
    del tables["agency.txt"]

    with pytest.raises(StaticLoadError) as caught:
        load_static(build_feed(tmp_path, tables))

    assert "agency.txt" in str(caught.value)


def test_an_unparsable_table_is_in_tables_and_still_raises_on_read(tmp_path):
    """`LoadedFeed.tables` is not a usable-set, so the adapter cannot trust it.

    One row with a non-numeric `stop_lat` marks the whole table
    UNPARSABLE_ROWS. It stays in `LoadedFeed.tables` because the loader
    attempted it, and `rows()` raises anyway.
    """
    from gtfs_validator import open_feed_view

    tables = minimal_tables()
    tables["stops.txt"][0]["stop_lat"] = "not-a-latitude"
    path = build_feed(tmp_path, tables)

    with open_feed_view(path, tables=list(SEVEN_TABLES)) as loaded:
        assert "stops.txt" in loaded.tables
        assert loaded.view.dependency_failed("stops.txt") is True

    with pytest.raises(StaticLoadError) as caught:
        load_static(path)

    assert "stops.txt" in str(caught.value)


def test_a_table_the_loader_dropped_is_neither_in_tables_nor_missing(tmp_path):
    """The fourth state, and the only one the adapter's last guard answers.

    `load_tables` wraps `_load_table` in `except Exception`, and on a raise it
    drops the store's partial table and pops the name back out of `loads`
    (`gtfs-validator` at `35fac77`, `reading.py:86-94`). So the name is in the
    archive, `is_missing` is False because that reads `feed.entry_of`, and
    `LoadedFeed.tables` does not carry it. No real input reached that state in
    the suite before this one: a mis-cased name is missing from the archive, and
    an UNPARSABLE_ROWS table stays *in* `tables`.

    A corrupted deflate payload is a genuine archive, not a monkeypatch: the
    entry lists and opens, and `zipfile` only notices when the stream's CRC-32
    fails at the end of the read, well inside the loader.
    """
    from gtfs_validator import open_feed_view

    path = corrupt_entry_payload(build_feed(tmp_path, minimal_tables()), "stops.txt")

    with open_feed_view(path, tables=list(SEVEN_TABLES)) as loaded:
        assert "stops.txt" not in loaded.tables, "the loader raised and popped it back out"
        assert loaded.view.is_missing("stops.txt") is False, "the archive does carry the entry"
        assert "agency.txt" in loaded.tables, "only the corrupted table is lost"
        errors = loaded.system_errors.in_order()
        assert [error.context["filename"] for error in errors] == ["stops.txt"]
        assert errors[0].context["exception"] == "BadZipFile"

    with pytest.raises(StaticLoadError) as caught:
        load_static(path)

    # The guard's own wording, not the DependencyFailed catch further down
    # `_load_tables`. Asserting the message is what makes deleting the guard a
    # test failure rather than a silent change of which line reports the fault.
    assert str(caught.value) == "stops.txt was requested but the loader did not return it"


def test_row_shape_is_a_plain_dict_with_a_header_counting_row_number(tmp_path):
    raw = load_static(build_feed(tmp_path, minimal_tables()))

    first = raw.stops[0]
    assert first["_row_number"] == 2, "_row_number is 1-based including the header"
    assert raw.stops[1]["_row_number"] == 3
    assert first["stop_id"] == "S1"
    # Every column in the schema is present, absent ones as None.
    assert "platform_code" in first
    assert first["platform_code"] is None


def test_loaded_field_types_are_what_every_later_rule_will_assume(tmp_path):
    raw = load_static(build_feed(tmp_path, minimal_tables()))

    stop = raw.stops[0]
    assert type(stop["stop_lat"]) is float
    assert type(stop["stop_lon"]) is float
    assert type(stop["location_type"]) is int, "an enum is a plain int, not a Python enum"
    assert type(stop["stop_name"]) is str

    stop_time = raw.stop_times[0]
    assert stop_time["arrival_time"] == 90300, "TIME is seconds since midnight, past midnight kept"
    assert type(stop_time["arrival_time"]) is int
    assert type(stop_time["stop_sequence"]) is int
    assert stop_time["shape_dist_traveled"] is None


def test_date_and_decimal_types_measured_outside_the_seven(tmp_path):
    """DATE and DECIMAL are pinned here even though no table in the seven has one.

    Checked against the sibling's schema at `35fac77`: of the seven tables, none
    declares a DATE or a DECIMAL field, so the two type facts can only be
    asserted by asking the private loader for two other tables. They are pinned
    because the rules under `rules/upstream/` read the same loader.
    """
    tables = minimal_tables()
    tables["calendar.txt"] = [
        {
            "service_id": "SVC1",
            "monday": "1",
            "tuesday": "1",
            "wednesday": "1",
            "thursday": "1",
            "friday": "1",
            "saturday": "0",
            "sunday": "0",
            "start_date": "20260101",
            "end_date": "20261231",
        }
    ]
    tables["fare_attributes.txt"] = [
        {
            "fare_id": "F1",
            "price": "2.50",
            "currency_type": "USD",
            "payment_method": "0",
            "transfers": "0",
        }
    ]
    path = build_feed(tmp_path, tables)

    loaded = _load_tables(path, ("calendar.txt", "fare_attributes.txt"))

    assert loaded["calendar.txt"][0]["start_date"] == 20260101
    assert type(loaded["calendar.txt"][0]["start_date"]) is int
    assert loaded["fare_attributes.txt"][0]["price"] == "2.50", "DECIMAL stays str for scale"
    assert type(loaded["fare_attributes.txt"][0]["price"]) is str


def test_the_returned_tables_still_read_after_the_view_is_gone(tmp_path):
    """The copy-out is the contract: nothing returned may hold the view alive."""
    raw = load_static(build_feed(tmp_path, minimal_tables()))

    # Every read below happens well outside the `with` inside load_static.
    assert sorted(row["stop_id"] for row in raw.stops) == ["S1", "S2"]
    assert [row["shape_pt_sequence"] for row in raw.shapes] == [1, 2, 3, 4]
    assert raw.agency[0]["agency_timezone"] == "America/New_York"


def test_a_retained_view_raises_programming_error(tmp_path):
    """The failure mode the copy-out is designed against, asserted rather than assumed."""
    from gtfs_validator import open_feed_view

    path = build_feed(tmp_path, minimal_tables())
    with open_feed_view(path, tables=["agency.txt"]) as loaded:
        escaped = loaded.view

    with pytest.raises(sqlite3.ProgrammingError):
        list(escaped.rows("agency.txt"))


def test_ignore_shapes_skips_the_table_entirely(tmp_path):
    path = build_feed(tmp_path, minimal_tables())

    raw = load_static(path, ignore_shapes=True)

    assert raw.shapes == []
    assert len(raw.stop_times) == 2
    assert len(raw.frequencies) == 1


def test_ignore_shapes_does_not_hide_a_broken_shapes_file(tmp_path):
    """The flag skips the load, so a broken `shapes.txt` is simply not read."""
    tables = minimal_tables()
    tables["shapes.txt"][2]["shape_pt_lat"] = "not-a-latitude"
    path = build_feed(tmp_path, tables)

    with pytest.raises(StaticLoadError):
        load_static(path)

    assert load_static(path, ignore_shapes=True).shapes == []
