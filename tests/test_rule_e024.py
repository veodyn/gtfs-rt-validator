"""E024, against upstream's own `testE024`.

Upstream asserts counts only; the prefixes are ours, read off
`TripDescriptorValidator.java:335`.

Upstream's feed here is `testagency2.zip`, where trip `1.1` has direction_id 0,
`2.1` has 1 and `3.1` has a blank cell. `tripfixtures.feed_tables` carries those
three trips with those three values, which is why its direction_ids are
testagency2's rather than testagency's all-blank ones.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from gtfs_rt_validator.rules.upstream.e024 import check
from gtfs_rt_validator.static.adapter import StaticLoadError, load_static
from gtfsfixtures import build_feed
from rulefixtures import context, entity, message, prefixes
from tripfixtures import SCHEDULED, both, feed_tables, run, td


def found(tmp_path: Path, *entities) -> list[str]:
    return prefixes(run(check, tmp_path, *entities))


def trip(trip_id: str, direction_id: int | None = None) -> dict[str, object]:
    fields: dict[str, object] = {"trip_id": trip_id, "schedule_relationship": SCHEDULED}
    if direction_id is not None:
        fields["direction_id"] = direction_id
    return td(**fields)


def test_no_realtime_direction_id_reports_nothing(tmp_path: Path) -> None:
    """Upstream, testE024's first stage. `hasDirectionId()` at `:330` is the
    whole gate; the call itself is unconditional."""
    assert found(tmp_path, both(trip("1.1"))) == []


def test_a_direction_id_that_matches_reports_nothing(tmp_path: Path) -> None:
    """Upstream, testE024: trip `1.1` with 0 and trip `2.1` with 1."""
    assert found(tmp_path, both(trip("1.1", 0))) == []
    assert found(tmp_path, both(trip("2.1", 1))) == []


def test_a_direction_id_that_does_not_match_reports_once_per_carrier(tmp_path: Path) -> None:
    """Upstream, testE024: trip `1.1` with 1 and trip `2.1` with 0, each
    `expected.put(E024, 2)`."""
    assert len(found(tmp_path, both(trip("1.1", 1)))) == 2
    assert len(found(tmp_path, both(trip("2.1", 0)))) == 2


def test_a_gtfs_trip_with_no_direction_id_always_reports(tmp_path: Path) -> None:
    """Upstream, testE024's last stage: trip `3.1`, whose GTFS cell is blank,
    with a realtime direction_id of 0, `expected.put(E024, 2)`. The Java
    comparison is `gtfsTrip.getDirectionId() == null || !equals(...)`, so null
    never matches anything."""
    assert len(found(tmp_path, both(trip("3.1", 0)))) == 2


# --- ours ----------------------------------------------------------------


def test_the_prefix_names_both_direction_ids(tmp_path: Path) -> None:
    """Ours, read off `:335`, and the two `getVehicleAndTripIdText` shapes."""
    named = entity(vehicle={"trip": trip("1.1", 1), "vehicle": {"id": "V1"}})

    assert found(tmp_path, both(trip("1.1", 1))) == [
        "GTFS-rt trip_id 1.1 trip.direction_id is 1 but GTFS trip.direction_id is 0",
        "GTFS-rt vehicle_id  trip_id 1.1 trip.direction_id is 1 but GTFS trip.direction_id is 0",
    ]
    assert found(tmp_path, named) == [
        "GTFS-rt vehicle_id V1 trip_id 1.1 trip.direction_id is 1 but GTFS trip.direction_id is 0"
    ]


def test_an_absent_gtfs_direction_id_prints_as_the_word_null(tmp_path: Path) -> None:
    """Ours. Java concatenates a null `String` as `"null"`, and that literal is
    part of the occurrence text rather than a rendering accident."""
    assert found(tmp_path, entity(trip_update={"trip": trip("3.1", 0)})) == [
        "GTFS-rt trip_id 3.1 trip.direction_id is 0 but GTFS trip.direction_id is null"
    ]


def test_a_trip_id_that_is_in_no_gtfs_row_reports_nothing(tmp_path: Path) -> None:
    """Ours. `gtfsTrip != null` is the first half of the condition, so an
    unknown trip_id is E003's finding and not this rule's."""
    assert found(tmp_path, both(trip("100", 1))) == []


def test_direction_id_zero_is_present_rather_than_defaulted(tmp_path: Path) -> None:
    """Ours. proto2 has explicit presence, so a direction_id of 0 on the wire is
    `hasDirectionId()` and reaches the comparison, where `3.1`'s blank GTFS cell
    then fails it. A port reading a truthiness test would report nothing here."""
    assert len(found(tmp_path, entity(trip_update={"trip": trip("3.1", 0)}))) == 1


# --- the lexical cases, measured against the jar one cell at a time ----------

#: The jar's answer for one `trips.txt` cell against one realtime direction_id,
#: on trip `L`. Measured, one jar invocation per row, JDK 17.0.19 at the pinned
#: SHA: a GTFS feed carrying that cell and a TripUpdate naming that
#: direction_id. `None` is no E024 at all.
JAR: dict[str, tuple[int, str | None]] = {
    "0": (0, None),
    "1": (1, None),
    " 0": (0, None),
    "0 ": (0, None),
    "00": (0, "GTFS-rt trip_id L trip.direction_id is 0 but GTFS trip.direction_id is 00"),
    "000": (0, "GTFS-rt trip_id L trip.direction_id is 0 but GTFS trip.direction_id is 000"),
    "+0": (0, "GTFS-rt trip_id L trip.direction_id is 0 but GTFS trip.direction_id is +0"),
    "-0": (0, "GTFS-rt trip_id L trip.direction_id is 0 but GTFS trip.direction_id is -0"),
    "01": (1, "GTFS-rt trip_id L trip.direction_id is 1 but GTFS trip.direction_id is 01"),
    "0.0": (0, "GTFS-rt trip_id L trip.direction_id is 0 but GTFS trip.direction_id is 0.0"),
    "": (0, "GTFS-rt trip_id L trip.direction_id is 0 but GTFS trip.direction_id is null"),
}

#: The cells the jar reads as equal to a realtime `0` or `1`, and this project
#: does too. Whitespace is in here because onebusaway's reader trims it.
AGREED = ("0", "1", " 0", "0 ")

#: The cells the jar reports, and so does this project as of the compat static
#: reader. Every one of them used to arrive here as the same `int` the realtime
#: side carries, because the strict sibling path types `direction_id` as an enum
#: and the text is gone before the comparison runs. `0.0` is not in this tuple
#: only because it has its own test below: it is the case where the difference
#: was a feed that would not load at all rather than an occurrence that went
#: missing.
PADDED = ("00", "000", "+0", "-0", "01")


def lexical(tmp_path: Path, cell: str) -> list[str]:
    """E024 over trip `L`, whose `trips.txt` `direction_id` cell is `cell`.

    A row appended to this cohort's feed rather than a feed of its own, so the
    only thing that differs from every other case in this file is the cell. The
    realtime direction_id is the one the jar was run with for that cell.
    """
    tables = feed_tables()
    tables["trips.txt"].append(
        {"trip_id": "L", "route_id": "1", "service_id": "alldays", "direction_id": cell}
    )
    direction_id = JAR[cell][0]
    return prefixes(
        check(
            message(entity(trip_update={"trip": trip("L", direction_id)})),
            context(tmp_path, tables),
        )
    )


@pytest.mark.parametrize("cell", AGREED)
def test_a_cell_the_jar_reads_as_equal_reports_nothing_here_either(
    tmp_path: Path, cell: str
) -> None:
    """The half of the lexical set the two agree on, measured rather than assumed.

    `" 0"` and `"0 "` are the interesting ones: onebusaway's reader trims the
    cell before `Trip.setDirectionId`, so the jar compares `"0"` against `"0"`
    and stays quiet, which is what the sibling's `int` does too. A port that
    "fixed" the divergence below by comparing raw strings would report here and
    be wrong.
    """
    assert lexical(tmp_path, cell) == []


@pytest.mark.parametrize("cell", PADDED)
def test_a_lexically_padded_gtfs_direction_id_reports_what_the_jar_reports(
    tmp_path: Path, cell: str
) -> None:
    """Both sides compare the raw cell, which is what makes these five report.

    `TripDescriptorValidator.java:329` reads `gtfsTrip.getDirectionId()`, an
    onebusaway `String` holding `trips.txt` verbatim (confirmed with `javap -p`
    on `onebusaway-gtfs-1.3.87.jar`: the field really is a `java.lang.String`),
    and tests it against `String.valueOf(directionId)`. So `00` is not `0`.

    This was a strict xfail until the compat static read stopped going through
    the sibling's typed path. The strict loader types the column as an ENUM into
    an INTEGER column and `typing_compiled._enum` drops the text before the
    insert, so all five used to arrive as the same `int` the realtime side
    carries and the comparison passed. `static/adapter.py`'s
    `load_static_as_onebusaway` reads the cell instead, and every prefix below is
    the one measured off a real jar, one run per cell.
    """
    assert lexical(tmp_path, cell) == [JAR[cell][1]]


def test_a_gtfs_direction_id_that_is_not_an_integer_reports_too(tmp_path: Path) -> None:
    """`0.0`, the case that used to cost the whole feed rather than one occurrence.

    The strict path's `parse_integer` refuses the cell, which marks the row
    unparsable, which marks `trips.txt` `dependency_failed`, which raises
    `StaticLoadError` before any rule runs: the same shape as `testagency.zip`'s
    `N` and `S` cells, and the reason the differential used to patch its own
    archive. onebusaway types the column as a `String` and has nothing to refuse,
    so compat now validates the feed and reports the prefix the jar reports.

    Modern still refuses it, and should: `0.0` is not a valid GTFS
    `direction_id` and the strict reader is the one that says so.
    """
    tables = feed_tables()
    tables["trips.txt"].append(
        {"trip_id": "L", "route_id": "1", "service_id": "alldays", "direction_id": "0.0"}
    )

    assert lexical(tmp_path, "0.0") == [JAR["0.0"][1]]
    with pytest.raises(StaticLoadError):
        load_static(build_feed(tmp_path, tables, name="modern.zip"))
