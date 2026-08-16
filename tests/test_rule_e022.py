"""E022, stop_time_update times that do not increase between two stops.

`testE022` (`TimestampValidatorTest.java:677-956`) is upstream's, and its ten
stages are the sharpest test of the eight-way logic there is: a port that merges
the less-than and equal-to cases, or that carries `previousArrivalTime` forward
unconditionally, gets several of the counts wrong while passing every other test
in this cohort. They are ported row for row from the checkout at
`jar-build/upstream/` rather than from a second-hand table of them.

Upstream asserts counts and never a prefix, so everything below `UPSTREAM_ROWS`
is ours: the eight occurrence texts, the order they come out in, and the
reach-back that the conditional carry-forward produces.

Every stage builds two stop_time_updates carrying neither a stop_sequence nor a
stop_id, which is why the prefixes below read `"stop_id "` with a trailing
space. That is `TimestampValidator.java:179`'s unguarded `else` arm, not a
fixture oversight.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

import pytest

from gtfs_rt_validator.proto.decode import Msg
from gtfs_rt_validator.report.occurrence import ENTITY_PATH_KEY
from gtfs_rt_validator.rules._shared.times import MIN_POSIX_TIME, posix_to_clock
from gtfs_rt_validator.rules.upstream.e022 import RULE_ID, check
from gtfs_rt_validator.runner.clock import ClockSource, Reading
from rulefixtures import (
    ENTITY_ID,
    TESTAGENCY_TIMEZONE,
    context,
    entity,
    message,
    occurrences,
    prefixes,
)

NOW = Reading(MIN_POSIX_TIME * 1000, ClockSource.FIXED)

#: A stop_time_update, as upstream's own stages express one: offsets from
#: `MIN_POSIX_TIME`, with `None` for a field the stop does not carry.
Stop = tuple[int | None, int | None]


def a_feed(stops: Sequence[Stop], **fields: object) -> Msg:
    """`testE022`'s entity: one TripUpdate whose stops carry no stop identifier."""
    stop_time_updates: list[dict[str, object]] = []
    for arrival, departure in stops:
        built: dict[str, object] = dict(fields)
        if arrival is not None:
            built["arrival"] = {"time": MIN_POSIX_TIME + arrival}
        if departure is not None:
            built["departure"] = {"time": MIN_POSIX_TIME + departure}
        stop_time_updates.append(built)
    return message(
        entity(
            trip_update={
                "trip": {},
                "timestamp": MIN_POSIX_TIME,
                "stop_time_update": stop_time_updates,
            },
            vehicle={"timestamp": MIN_POSIX_TIME},
        ),
        timestamp=MIN_POSIX_TIME,
    )


#: `testE022`'s ten stages, in order: stop A, stop B, and the count upstream
#: asserts. Each stop is `(arrival, departure)` as an offset from
#: `MIN_POSIX_TIME`, `None` meaning the stop does not carry that field.
UPSTREAM_ROWS: tuple[tuple[Stop, Stop, int], ...] = (
    ((None, 0), (None, 1), 0),
    ((0, None), (1, None), 0),
    ((0, 0), (1, 1), 0),
    ((0, 1), (2, 3), 0),
    ((0, 0), (0, 0), 4),
    ((0, 1), (0, 3), 2),
    ((0, 0), (0, 3), 2),
    ((1, 1), (0, 3), 2),
    ((1, 3), (2, 2), 2),
    ((2, 3), (1, 1), 4),
)


@pytest.mark.parametrize(("first", "second", "expected"), UPSTREAM_ROWS)
def test_upstream_rows(tmp_path: Path, first: Stop, second: Stop, expected: int) -> None:
    found = occurrences(check(a_feed((first, second)), context(tmp_path, clock=NOW)))

    assert len(found) == expected


def moment(offset: int) -> str:
    """One value as the occurrence text renders it: clock, then raw seconds."""
    value = MIN_POSIX_TIME + offset
    return f"{posix_to_clock(value, TESTAGENCY_TIMEZONE)} ({value})"


def says(field: str, offset: int, relation: str, previous_field: str, previous: int) -> str:
    """One of the eight, as `TimestampValidator.java:195-245` concatenates it."""
    return (
        f"entity ID {ENTITY_ID} stop_id  {field} {moment(offset)} "
        f"{relation} previous stop {previous_field} {moment(previous)}"
    )


def test_all_four_arrival_cases_and_all_four_departure_cases_from_one_stop(
    tmp_path: Path,
) -> None:
    """Upstream's fifth row, `:805-828`, is the one stage where a single
    stop_time_update fires four of the eight. This pins which four and in what
    order: within each block the stop's own field is asked about first, and the
    arrival block runs before the departure block."""
    found = prefixes(check(a_feed(((0, 0), (0, 0))), context(tmp_path, clock=NOW)))

    assert found == [
        says("arrival_time", 0, "is equal to", "arrival_time", 0),
        says("arrival_time", 0, "is equal to", "departure_time", 0),
        says("departure_time", 0, "is equal to", "departure_time", 0),
        says("departure_time", 0, "is equal to", "arrival_time", 0),
    ]


def test_the_less_than_cases_read_the_same_way(tmp_path: Path) -> None:
    """Upstream's last row, `:930-953`. `<` and `Objects.equals` are separate
    tests producing separate sentences, which is why merging them into a `<=`
    would lose an occurrence rather than rename one."""
    found = prefixes(check(a_feed(((2, 3), (1, 1))), context(tmp_path, clock=NOW)))

    assert found == [
        says("arrival_time", 1, "is less than", "arrival_time", 2),
        says("arrival_time", 1, "is less than", "departure_time", 3),
        says("departure_time", 1, "is less than", "departure_time", 3),
        says("departure_time", 1, "is less than", "arrival_time", 2),
    ]


def test_a_stop_with_only_a_departure_does_not_advance_the_previous_arrival(
    tmp_path: Path,
) -> None:
    """The conditional carry-forward at `:256-263`, which upstream's own ten rows
    never isolate because none of them mixes a partial stop into a failing pair.

    Stop B carries a departure and no arrival, so `previousArrivalTime` is still
    stop A's when stop C is reached: the first occurrence below names A's
    arrival, reaching back past B. A port that carried both values forward
    unconditionally would name B's departure instead, and one that reset them
    would report nothing at all.
    """
    found = prefixes(check(a_feed(((2, 2), (None, 5), (1, None))), context(tmp_path, clock=NOW)))

    assert found == [
        says("arrival_time", 1, "is less than", "arrival_time", 2),
        says("arrival_time", 1, "is less than", "departure_time", 5),
    ]


def test_the_state_resets_between_two_trip_updates(tmp_path: Path) -> None:
    """`:174-177` declares the two values inside the TripUpdate branch, so the
    last stop of one trip is never the "previous stop" of the next trip's first."""
    trip = {
        "trip": {},
        "timestamp": MIN_POSIX_TIME,
        "stop_time_update": [{"arrival": {"time": MIN_POSIX_TIME + 9}}],
    }
    feed = message(
        entity(trip_update=trip, entity_id="A"),
        entity(trip_update=trip, entity_id="B"),
        timestamp=MIN_POSIX_TIME,
    )

    assert prefixes(check(feed, context(tmp_path, clock=NOW))) == []


def test_the_stop_sequence_wins_over_the_stop_id_in_the_description(tmp_path: Path) -> None:
    """`:179` is a ternary on `hasStopSequence()`, so a stop carrying both is
    described by its sequence and the stop_id never appears."""
    feed = a_feed(((0, 0), (0, 0)), stop_sequence=4, stop_id="S1")

    (first, *_) = prefixes(check(feed, context(tmp_path, clock=NOW)))

    assert first.startswith(f"entity ID {ENTITY_ID} stop_sequence 4 arrival_time ")


def test_the_agency_timezone_reaches_both_clocks_in_every_occurrence(tmp_path: Path) -> None:
    """Eight of the eight embed two clock strings, so a wrong zone corrupts all
    of them. `_shared/times.posix_to_clock` is the only path a zone takes into a
    report, and this is one of the rules that proves it."""
    in_tokyo = context(tmp_path, clock=NOW, timezone="Asia/Tokyo")

    (first, *_) = prefixes(check(a_feed(((0, 0), (0, 0))), in_tokyo))

    assert first == (
        f"entity ID {ENTITY_ID} stop_id  arrival_time 09:00:00 ({MIN_POSIX_TIME}) "
        f"is equal to previous stop arrival_time 09:00:00 ({MIN_POSIX_TIME})"
    )


def test_the_occurrences_locate_the_stop_they_came_from(tmp_path: Path) -> None:
    """Ours, and modern-mode only: `--compat` writes the prefix alone."""
    found = occurrences(check(a_feed(((0, 0), (0, 0))), context(tmp_path, clock=NOW)))

    assert {one.context[ENTITY_PATH_KEY] for one in found} == {
        "entity[0].trip_update.stop_time_update[1]"
    }
    assert {one.rule_id for one in found} == {RULE_ID}
