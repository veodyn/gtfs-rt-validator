"""E040, against upstream's own `testE40`.

Every assertion marked "upstream" is transcribed from the real
`StopTimeUpdateValidatorTest.java` (`testE40`, `:885-968`), not from the
reference's summary of it. Upstream asserts counts and nothing else, so every
assertion about occurrence text is ours.

Upstream's fixture names trip `1234` against `testagency.zip`, which does not
have it, and its stop_id `1.1` is a trip_id from that feed rather than a stop.
Both are transcribed as written: this rule reads neither the static feed nor the
stop_id's value.
"""

from __future__ import annotations

from gtfs_rt_validator.rules.upstream.e040 import check
from stufixtures import found, run, stu, trip_update

TRIP = "1234"


def delayed(stop_sequence: int | None = None, stop_id: str | None = None) -> dict[str, object]:
    return stu(stop_sequence, stop_id, arrival={"delay": 60})


# --- upstream's testE40 -----------------------------------------------------


def test_neither_stop_id_nor_stop_sequence_reports_once(tmp_path):
    """Upstream, testE40: `expected.put(E040, 1)`."""
    assert len(run(check, tmp_path, trip_update(delayed(), trip_id=TRIP))) == 1


def test_a_stop_id_alone_is_enough(tmp_path):
    """Upstream, testE40: stop_id `1.1` and no stop_sequence, `expected.clear()`."""
    assert run(check, tmp_path, trip_update(delayed(stop_id="1.1"), trip_id=TRIP)) == []


def test_a_stop_sequence_alone_is_enough(tmp_path):
    """Upstream, testE40: stop_sequence 1 and no stop_id, `expected.clear()`."""
    assert run(check, tmp_path, trip_update(delayed(1), trip_id=TRIP)) == []


def test_both_fields_report_nothing(tmp_path):
    """Upstream, testE40: stop_sequence 1 and stop_id `1.1`, `expected.clear()`."""
    assert run(check, tmp_path, trip_update(delayed(1, "1.1"), trip_id=TRIP)) == []


# --- the occurrence text, which upstream never looks at ---------------------


def test_the_prefix_names_the_trip_and_not_the_stop_time_update(tmp_path):
    """Ours, read off `:294`. There is nothing in a stop_time_update carrying
    neither field to name it by, and upstream does not reach for its index."""
    assert found(run(check, tmp_path, trip_update(delayed(), trip_id=TRIP))) == ["trip_id 1234"]


def test_several_bare_stop_time_updates_give_several_identical_occurrences(tmp_path):
    """Ours, and the consequence of the prefix above. Nothing de-duplicates
    these, so three bare stop_time_updates give three byte-identical strings."""
    updates = trip_update(delayed(), delayed(), delayed(), trip_id=TRIP)

    assert found(run(check, tmp_path, updates)) == ["trip_id 1234"] * 3


def test_a_trip_update_with_no_trip_id_falls_back_to_the_entity_id(tmp_path):
    """Ours. `GtfsUtils.getTripId` returns `"entity ID " + entity.getId()` when
    the TripDescriptor has no trip_id."""
    assert found(run(check, tmp_path, trip_update(delayed()))) == ["entity ID TEST_ENTITY"]


def test_an_explicitly_empty_stop_id_still_counts_as_present(tmp_path):
    """Ours. The test is `hasStopId()`, not "the stop_id says something", so a
    feed setting it to the empty string escapes this rule where E037's
    `isEmpty()` guard would not."""
    assert run(check, tmp_path, trip_update(delayed(stop_id=""), trip_id=TRIP)) == []
