"""The archive the jar validates and this project refuses, measured on both sides.

A `frequencies.txt` row with `exact_times = 1` and `headway_secs = 0` hangs
`FrequencyTypeOneValidator` (`tests/test_shared_frequencies.py` and the output
contract record the `jstack` measurement). What that measurement did *not*
establish is that the archive alone is enough: upstream enters the loop only for
a trip a realtime TripUpdate or VehiclePosition names
(`FrequencyTypeOneValidator.java:53` and `:94`), so an archive whose spinning
trip nothing names is validated to completion.

This module is that differential, and it is deliberately a **red** one. Both
halves run against the same archive:

- the jar reads it and writes a full results file;
- compat reads it too, and `runner/gate.py` then refuses the run, because
  `spinning_frequency` decides on the archive alone and cannot know that no
  message names the spinning trip.

So this project writes nothing where upstream writes everything. That is a loss
of output, not parity, and it is pinned here rather than argued away.

**The blame moved and the diff did not.** It used to be the loader's: both modes
read the static feed through the sibling's strict path, which types
`headway_secs` as a required positive integer, so `frequencies.txt` came back
`dependency_failed` and the archive was refused before either mode was
consulted. Compat now reads it as onebusaway does, where `headwaySecs` is a
plain `int`, so the archive loads and the guard is what stops the run. Modern
still refuses at the loader, which is the strict reader's call to make. Closing
what is left means deciding per message, which the module docstring of
`static/_tables.py` argues the gate cannot do.

The referenced case, where a message does name the spinning trip, is not run
here for the reason the output contract gives: it is a live spin, so running it
would burn `run_jar.RUN_TIMEOUT` seconds of CPU before `invoke` killed the jar
and raised. The bound means a stray spinning input fails the differential
instead of hanging it, but paying it on purpose in every suite run buys nothing,
so this module still only ever feeds the jar the archive it completes on.

It skips cleanly with no jar, because `jar-build/` and `*.jar` are gitignored:

    .venv/bin/python tools/build_jar.py

The archive is built from `gtfsfixtures.minimal_tables` rather than from
`tests/fixtures/gtfs/testagency.zip` because the spinning row has to be written
into it, and testagency's own `frequencies.txt` carries a headway of 3600.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from gtfs_rt_validator.proto.encode import encode
from gtfs_rt_validator.proto.schema_2015 import SCHEMA
from gtfs_rt_validator.report.occurrence import NoticeContainer
from gtfs_rt_validator.runner.gate import CompatAbort, prepare_static
from gtfs_rt_validator.runner.mode import Mode
from gtfs_rt_validator.static.adapter import (
    StaticLoadError,
    load_static,
    load_static_as_onebusaway,
)
from gtfsfixtures import build_feed, minimal_tables
from jarcorpus import import_tool

jarenv = import_tool("jarenv")
run_jar = import_tool("run_jar")


def _unavailable() -> str:
    """Why the jar cannot be run here, or the empty string if it can."""
    if not jarenv.jar_present():
        return f"no jar at {jarenv.JAR}; run .venv/bin/python tools/build_jar.py"
    try:
        jarenv.java_home_17()
    except jarenv.NoJdk17Error as exc:
        return str(exc)
    return ""


REASON = _unavailable()
needs_jar = pytest.mark.skipif(bool(REASON), reason=REASON or "a jar is present")

#: `minimal_tables`' own frequency trip, the one that carries the spinning row.
SPINNING_TRIP = "T1"

#: A second trip added below, so the realtime feed can name a trip that exists
#: and still not be the one the frequency row belongs to. A trip absent from the
#: archive would show the same thing while also tripping E003, which would make
#: the pinned rule set below say less about why the run completed.
OTHER_TRIP = "T2"

#: 2017-07-14T02:40:00Z, well behind the mtimes `run_jar.plan` stamps, so W008
#: fires deterministically. The same constant `goldenfeeds` uses.
FEED_TS = 1_500_000_000

#: Every rule the jar reported for `unreferenced.pb`, measured. E019 is not among
#: them, and that is the point: the validator that would have spun ran, found no
#: exact_times = 1 period for `T2`, and returned.
JAR_REPORTED = ["E023", "E041", "W002", "W008", "W009"]


def tables(headway: str) -> dict[str, list[dict[str, object]]]:
    """`minimal_tables` with this headway on its one exact_times = 1 row."""
    built = minimal_tables()
    built["frequencies.txt"][0]["headway_secs"] = headway
    built["trips.txt"].append(
        {"trip_id": OTHER_TRIP, "route_id": "R1", "service_id": "SVC1", "direction_id": "0"}
    )
    built["stop_times.txt"] += [
        {
            "trip_id": OTHER_TRIP,
            "arrival_time": time,
            "departure_time": time,
            "stop_id": stop_id,
            "stop_sequence": str(sequence),
            "pickup_type": "0",
        }
        for sequence, (time, stop_id) in enumerate([("08:00:00", "S1"), ("08:20:00", "S2")], 1)
    ]
    return built


def archive(directory: Path, headway: str = "0", name: str = "spinning.zip") -> Path:
    return build_feed(directory, tables(headway), name=name)


def naming(trip_id: str) -> bytes:
    """One TripUpdate for `trip_id`, whose start_time matches no frequency."""
    return encode(
        {
            "header": {"gtfs_realtime_version": "1.0", "incrementality": 0, "timestamp": FEED_TS},
            "entity": [
                {
                    "id": "e1",
                    "trip_update": {
                        "trip": {"trip_id": trip_id, "start_time": "07:30:00"},
                        "timestamp": FEED_TS,
                    },
                }
            ],
        },
        SCHEMA,
    )


@pytest.fixture(scope="module")
def wrote(tmp_path_factory) -> run_jar.RunResult:
    """One jar run over the spinning archive, with the spinning trip unnamed."""
    root = tmp_path_factory.mktemp("jar-frequency")
    return run_jar.run({"unreferenced.pb": naming(OTHER_TRIP)}, archive(root))


@needs_jar
def test_the_jar_validates_an_archive_whose_spinning_trip_nothing_names(wrote) -> None:
    """Measured. Exit 0, nothing skipped, and a results file with real content.

    Never weaken this to make the halves agree: the jar completing here is the
    fact the divergence below is measured against.
    """
    assert wrote.skipped == []
    assert set(wrote.results) == {"unreferenced.pb"}
    reported = sorted(
        {
            row["errorMessage"]["validationRule"]["errorId"]
            for row in json.loads(wrote.results["unreferenced.pb"])
        }
    )
    assert reported == JAR_REPORTED


def test_compat_refuses_the_archive_the_jar_just_completed(tmp_path) -> None:
    """The red half, and it needs no jar.

    The archive loads: onebusaway's `Frequency.headwaySecs` is a plain `int`, so
    compat reads the row the strict path will not type. `spinning_frequency`
    then refuses the run, because it decides on the archive alone and the jar's
    spin depends on a trip a message names. No results are written for any file,
    where the jar wrote results for every one.
    """
    raw = load_static_as_onebusaway(archive(tmp_path))
    assert [row["headway_secs"] for row in raw.frequencies] == [0]

    with pytest.raises(CompatAbort, match="headway_secs"):
        prepare_static(archive(tmp_path), mode=Mode.COMPAT, system_errors=NoticeContainer())


def test_modern_refuses_it_one_step_earlier_at_the_loader(tmp_path) -> None:
    """The other half of the same archive, and the strict reader's call.

    `headway_secs` is REQUIRED and POSITIVE in the canonical static schema, so
    `frequencies.txt` comes back `dependency_failed` and the whole feed is
    unusable. Modern is where disagreeing with upstream is allowed.
    """
    with pytest.raises(StaticLoadError, match=r"frequencies\.txt"):
        load_static(archive(tmp_path))


def test_the_same_archive_with_a_positive_headway_loads_in_both_readers(tmp_path) -> None:
    """The control: the headway is the only reason the two tests above refuse.

    Without this, a broken fixture would satisfy either refusal for some
    unrelated reason and the divergence would be a claim about nothing.
    """
    for read in (load_static, load_static_as_onebusaway):
        raw = read(archive(tmp_path, headway="600", name="advancing.zip"))

        assert [row["headway_secs"] for row in raw.frequencies] == [600]
        assert {row["trip_id"] for row in raw.frequencies} == {SPINNING_TRIP}
