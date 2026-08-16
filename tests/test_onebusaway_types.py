"""`static/onebusaway.py`, against the model classes it claims to reproduce.

Every assertion here is measured off `onebusaway-gtfs-1.3.87.jar`, the artefact
the pinned pom resolves, with `javap -p` on the model classes and `javap -c` on
`StopTimeFieldMappingFactory`'s static initialiser. The measurements are quoted
in the module under test; what is asserted here is that the Python agrees with
them, one behaviour at a time.

`tests/test_adapter.py` covers the strict path's typing and is deliberately left
alone: the two readers are supposed to disagree, and a test module that covered
both would have to keep saying which.
"""

from __future__ import annotations

import pytest

from gtfs_rt_validator.static.adapter import (
    StaticLoadError,
    load_static,
    load_static_as_onebusaway,
)
from gtfs_rt_validator.static.onebusaway import COLUMNS, CellTypeError, typed_rows
from gtfsfixtures import build_feed, minimal_tables


def rows(table: str, *cells: dict[str, str]) -> list[dict[str, object]]:
    """`typed_rows` over hand-written cells, with a row number attached."""
    return typed_rows(
        table, [{"_row_number": index, **cell} for index, cell in enumerate(cells, 2)]
    )


# --- direction_id, the one that made this module necessary -------------------


@pytest.mark.parametrize("cell", ["0", "00", "01", "+0", "-0", "0.0", "N", "north"])
def test_direction_id_is_the_text_the_file_holds(cell: str) -> None:
    """`Trip.directionId` is a `java.lang.String`, so nothing is parsed and
    nothing can be refused. `TripDescriptorValidator.java:334` compares it
    against `String.valueOf(directionId)`, which is why the text has to survive."""
    assert rows("trips.txt", {"trip_id": "T", "direction_id": cell})[0]["direction_id"] == cell


def test_a_blank_direction_id_is_none_and_prints_as_null() -> None:
    """csv-entities never calls the setter for an empty value, so the field keeps
    its `null`. E024 renders that as the literal `null`."""
    assert rows("trips.txt", {"trip_id": "T", "direction_id": ""})[0]["direction_id"] is None


def test_a_column_the_file_omits_still_answers() -> None:
    """A row always carries every column this project reads, so a rule asking for
    one gets `None` rather than a `KeyError` about a header."""
    assert rows("trips.txt", {"trip_id": "T"})[0]["direction_id"] is None


# --- the numbers ------------------------------------------------------------


def test_headway_secs_has_no_positivity_constraint() -> None:
    """`Frequency.headwaySecs` is a plain `int`. The canonical static schema
    types the same column REQUIRED POSITIVE INTEGER, which is the whole
    difference behind `tests/test_jar_frequency_divergence.py`."""
    built = rows("frequencies.txt", {"trip_id": "T", "headway_secs": "0"})
    assert built[0]["headway_secs"] == 0


def test_times_are_seconds_after_midnight_with_past_midnight_kept() -> None:
    assert rows("stop_times.txt", _stop_time("25:05:00"))[0]["arrival_time"] == 90300


def test_the_time_grammar_is_the_jars_own_and_is_looser_than_it_looks() -> None:
    """`^(-{0,1}\\d+):(\\d{2}):(\\d{2})$` with `ss + 60 * (mm + 60 * hh)`, and no
    normalisation anywhere. So `10:99:99` is 42,039 seconds and a leading minus
    carries into the whole result. Refusing either would refuse a feed the jar
    reads."""
    assert rows("stop_times.txt", _stop_time("10:99:99"))[0]["arrival_time"] == 42039
    assert rows("stop_times.txt", _stop_time("-1:00:00"))[0]["arrival_time"] == -3600


@pytest.mark.parametrize("cell", ["8:00", "08:00:00.5", "eight", "08:0:00"])
def test_a_time_the_pattern_rejects_fails_the_load(cell: str) -> None:
    with pytest.raises(CellTypeError):
        rows("stop_times.txt", _stop_time(cell))


def test_integers_follow_javas_grammar_rather_than_pythons() -> None:
    """Python's `int()` takes underscores and non-ASCII digits; `Integer.parseInt`
    takes neither, and throws outside 32 bits."""
    assert rows("stops.txt", {"stop_id": "S", "location_type": "01"})[0]["location_type"] == 1
    # "\uff12" is FULLWIDTH DIGIT TWO, escaped so this file stays ASCII.
    # `int()` accepts it and `Integer.parseInt` does not.
    for bad in ("1_0", "\uff12", "2147483648"):
        with pytest.raises(CellTypeError):
            rows("stops.txt", {"stop_id": "S", "location_type": bad})


def test_coordinates_are_doubles_and_an_absent_one_is_none() -> None:
    """`Stop.lat` and `Stop.lon` are `optional = true` upstream, so a stop with
    no coordinates loads and simply stays out of the bounding box."""
    built = rows("stops.txt", {"stop_id": "S", "stop_lat": "40.5", "stop_lon": ""})
    assert built[0]["stop_lat"] == 40.5
    assert built[0]["stop_lon"] is None


def test_the_four_cells_this_project_sorts_or_measures_by_may_not_be_absent() -> None:
    """`StopTime.stopSequence` carries no `@CsvField` at all, which is
    csv-entities' required default, and `ShapePoint`'s three carry one without
    `optional = true`. All four would be a `None` in a sort key or a bounding
    box here."""
    with pytest.raises(CellTypeError, match="stop_sequence"):
        rows("stop_times.txt", {"trip_id": "T", "stop_id": "S"})
    with pytest.raises(CellTypeError, match="shape_pt_lat"):
        rows("shapes.txt", {"shape_id": "P", "shape_pt_sequence": "1", "shape_pt_lon": "-73"})


# --- the two readers over one archive ---------------------------------------


def test_the_two_readers_agree_on_a_feed_that_types_cleanly(tmp_path) -> None:
    """The compat reader is a second implementation, so a feed both accept has to
    come out the same or every rule test that switched to it is measuring
    something else.

    Compared column by column over `COLUMNS`, because the two rows are not the
    same shape and are not meant to be: the strict path stores every column the
    canonical schema declares, and this one carries the file\'s own columns plus
    the ones named here. Nothing outside `COLUMNS` is read, which is what makes
    that difference invisible rather than latent.
    """
    feed = build_feed(tmp_path, minimal_tables())

    strict, lenient = load_static(feed), load_static_as_onebusaway(feed)

    for table in ("agency", "stops", "routes", "stop_times", "shapes", "frequencies"):
        columns = COLUMNS[f"{table}.txt"]
        for one, two in zip(getattr(strict, table), getattr(lenient, table), strict=True):
            assert {name: one[name] for name in columns} == {name: two[name] for name in columns}, (
                table
            )
    # trips is the exception, and the only one: direction_id is an int on the
    # strict side and the cell's own text on this one.
    assert [row["direction_id"] for row in strict.trips] == [0]
    assert [row["direction_id"] for row in lenient.trips] == ["0"]


def test_a_missing_required_file_is_still_a_load_failure(tmp_path) -> None:
    """`GtfsReader` throws on a missing required entry, so the jar dies before
    validating anything. Leniency is about cells, not about absent tables."""
    tables = minimal_tables()
    del tables["stops.txt"]

    with pytest.raises(StaticLoadError, match=r"stops\.txt"):
        load_static_as_onebusaway(build_feed(tmp_path, tables, name="nostops.zip"))


def test_an_absent_optional_file_reads_as_no_rows(tmp_path) -> None:
    tables = minimal_tables()
    del tables["frequencies.txt"]

    assert (
        load_static_as_onebusaway(build_feed(tmp_path, tables, name="nofreq.zip")).frequencies == []
    )


def _stop_time(time: str) -> dict[str, str]:
    return {"trip_id": "T", "stop_id": "S", "stop_sequence": "1", "arrival_time": time}
