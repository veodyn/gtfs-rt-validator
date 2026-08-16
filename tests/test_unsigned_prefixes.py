"""This project's whole output over the unsigned feeds, against the jar's.

The expectation is `unsignedpins.PINS`, measured off a running jar and
re-derived by `tests/test_jar_unsigned.py`. This module needs no jar: it stages
the same eleven feeds and runs this project's own compat pipeline over them, so
a checkout with nothing built still catches a rendering that drifts back to the
unsigned value, or a comparison that stops reading the signed one.

The run is a directory replay under `SortBy.DATE_MODIFIED`, which is what
`BatchProcessor` does and what makes each file's mtime its clock. `run_jar.stage`
stamps those mtimes, so the same helper that prepares a jar run prepares this one
and the two cannot disagree about the clock.

**One assertion per feed, over the complete output.** Not one per interesting
prefix: the divergence this closes was as much about which occurrences fire as
about what they say, and a per-prefix containment check would pass on a run that
also emitted three occurrences the jar never wrote.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from gtfs_rt_validator.api import Request, validate
from gtfs_rt_validator.inputs import resolve_walk
from gtfs_rt_validator.proto.decode import Msg, decode
from gtfs_rt_validator.proto.encode import encode
from gtfs_rt_validator.proto.schema_2015 import SCHEMA
from gtfs_rt_validator.report.occurrence import SOURCE_FILE_KEY
from gtfs_rt_validator.rules._shared.ids import stop_time_update_id_text
from gtfs_rt_validator.rules._shared.javafmt import int32
from gtfs_rt_validator.rules._shared.timestamp_text import stop_description
from gtfs_rt_validator.runner.clock import SortBy
from gtfs_rt_validator.runner.mode import Mode
from jarcorpus import import_tool
from unsignedfeeds import FEEDS, U32, static_feed
from unsignedpins import expected

# `stage` is upstream's staging protocol, not a jar call: it writes the bytes and
# stamps the mtimes a run reads as its clock. Importing it keeps this module from
# restating either.
run_jar = import_tool("run_jar")


@pytest.fixture(scope="module")
def found(tmp_path_factory) -> dict[str, list[tuple[str, str]]]:
    """Feed name to the sorted `(rule_id, prefix)` pairs this project reported."""
    root = tmp_path_factory.mktemp("unsigned")
    directory = root / "rt"
    directory.mkdir()
    run_jar.stage(FEEDS, directory)
    result = validate(
        Request(
            mode=Mode.COMPAT,
            gtfs=static_feed(root),
            inputs=resolve_walk(str(directory), SortBy.DATE_MODIFIED),
            sort_by=SortBy.DATE_MODIFIED,
        )
    )
    reported: dict[str, list[tuple[str, str]]] = {name: [] for name in FEEDS}
    for occurrence in result.run.notices.in_order():
        source = Path(str(occurrence.context[SOURCE_FILE_KEY])).name
        reported[source].append((occurrence.rule_id, occurrence.prefix))
    return {name: sorted(pairs) for name, pairs in reported.items()}


@pytest.mark.parametrize("name", list(FEEDS))
def test_this_project_reports_exactly_what_the_jar_reported(name, found) -> None:
    """A red diff here is the deliverable. Never trim the pin to make it pass."""
    assert found[name] == expected(name)


def stop_time_update(**fields: object) -> Msg:
    """One decoded `StopTimeUpdate`, through the real encoder and decoder."""
    blob = encode(
        {
            "header": {"gtfs_realtime_version": "1.0"},
            "entity": [
                {
                    "id": "e1",
                    "trip_update": {"trip": {"trip_id": "t"}, "stop_time_update": [fields]},
                }
            ],
        },
        SCHEMA,
    )
    message = decode(blob, SCHEMA)
    return message.get("entity")[0].get("trip_update").get("stop_time_update")[0]


def test_the_shared_stop_time_update_id_renders_the_signed_value() -> None:
    """`GtfsUtils.getStopTimeUpdateId`, the helper E042, E043, E044, E046 and
    W009 all reach.

    Asserted directly as well as end to end, because five ids share this one
    line and a test per rule would hide that they share it.
    """
    assert stop_time_update_id_text(stop_time_update(stop_sequence=U32)) == "stop_sequence -1"


def test_the_timestamp_validators_own_stop_description_renders_the_signed_value() -> None:
    """`TimestampValidator.java:179`, which opens with a space and is **not**
    `getStopTimeUpdateId`. Two helpers, one field, and they have to agree."""
    assert stop_description(stop_time_update(stop_sequence=U32)) == " stop_sequence -1"


def test_a_stop_sequence_inside_the_signed_range_is_unchanged() -> None:
    """The narrowing is a no-op below 2^31, which is every feed a producer means
    to send. Nothing about ordinary output moves."""
    assert stop_time_update_id_text(stop_time_update(stop_sequence=7)) == "stop_sequence 7"
    assert stop_description(stop_time_update(stop_sequence=7)) == " stop_sequence 7"


def test_the_decoder_still_holds_the_true_unsigned_value() -> None:
    """The narrowing is the rule layer's, not the decoder's.

    `Msg.get` answers what the wire says, which is what modern mode wants and
    what `tests/test_decode.py` pins. `int32` is where compat's rules turn that
    into what protobuf-java's getter would have handed them.
    """
    update = stop_time_update(stop_sequence=U32)
    assert update.get("stop_sequence") == U32
    assert int32(update.get("stop_sequence")) == -1
