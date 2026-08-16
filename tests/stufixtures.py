"""The feeds and builders `StopTimeUpdateValidator`'s thirteen test files share.

Upstream's `StopTimeUpdateValidatorTest` runs against three static feeds, and a
port that rebuilt each one per rule file would be thirteen copies of the same
25 rows. All three are here, transcribed from the archives in
`jar-build/upstream/gtfs-realtime-validator-lib/src/test/resources/`:

- `bullrunner()`: `bullrunner-gtfs.zip` trip `1`, whose 25 `stop_times.txt` rows
  visit stop_id `222` at stop_sequence 1 **and** 25. That repeat is the whole
  reason E009 exists, and it is why every stop_id-only fixture below expects an
  E009 alongside whatever it was testing.
- `bullrunner(timepoints=True)`: `bullrunner-gtfs-timepoints-only-legacy-exact-times-1.zip`,
  the same 25 rows with `arrival_time` and `departure_time` blank everywhere
  except stop_sequences 1, 7, 13, 18, 22 and 25. E046 is about exactly those
  blanks.
- `testagency()`: `testagency.zip` trip `1.1`, stops A, B, C with no repeat.

Two facts about upstream's own fixtures are load-bearing and easy to lose.
`testagency.zip` has **no** trip `1` and no trip `1234`, so every upstream case
that names one of those is running with `gtfsStopTimes == null`: the whole
`while` loop at `StopTimeUpdateValidator.java:119-166` is skipped, and E045,
E046 and E051 are unreachable there. And upstream's nine-stop_time_update
fixtures use stop_sequences 1, 2, 3, 4, 5, 6, 10, 12, 25, not 1 through 9; the
gaps are what make the walk's never-rewinding index observable.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path

from gtfs_rt_validator.proto.decode import Msg
from gtfs_rt_validator.report.occurrence import Occurrence
from gtfs_rt_validator.rules._shared.walk_stop_time_updates import stop_time_updates
from gtfs_rt_validator.rules._shared.walks import Event, walk_events
from gtfs_rt_validator.runner.context import RuleContext
from rulefixtures import context, entity, message, minimal, stop_rows, trip_rows

__all__ = [
    "BULL_RUNNER_ROWS",
    "TIMEPOINTS",
    "bullrunner",
    "counts",
    "feed",
    "found",
    "ids",
    "nine",
    "rule_context",
    "run",
    "stu",
    "testagency",
    "trip_update",
    "walk",
]

#: `bullrunner-gtfs.zip` stop_times.txt for trip `1`, in file order.
#: `(stop_sequence, stop_id, time)`.
BULL_RUNNER_ROWS: tuple[tuple[int, str, str], ...] = (
    (1, "222", "07:00:00"),
    (2, "230", "07:01:04"),
    (3, "214", "07:01:38"),
    (4, "204", "07:02:15"),
    (5, "102", "07:02:56"),
    (6, "101", "07:03:38"),
    (7, "108", "07:04:04"),
    (8, "110", "07:04:32"),
    (9, "166", "07:05:38"),
    (10, "162", "07:06:44"),
    (11, "158", "07:07:48"),
    (12, "154", "07:08:30"),
    (13, "150", "07:09:20"),
    (14, "446", "07:09:52"),
    (15, "432", "07:11:01"),
    (16, "430", "07:11:49"),
    (17, "426", "07:12:34"),
    (18, "418", "07:13:41"),
    (19, "401", "07:14:34"),
    (20, "414", "07:16:07"),
    (21, "330", "07:16:53"),
    (22, "328", "07:17:21"),
    (23, "326", "07:17:59"),
    (24, "226", "07:18:43"),
    (25, "222", "07:19:43"),
)

#: The six stop_sequences that keep a time in the timepoints-only archive.
#: Every other row there has both cells blank, which is what `isArrivalTimeSet()`
#: answers `false` for.
TIMEPOINTS = frozenset({1, 7, 13, 18, 22, 25})


def _stop_time_rows(
    trip_id: str, rows: Iterable[tuple[int, str, str]], *, timepoints: bool
) -> list[dict[str, str]]:
    return [
        {
            "trip_id": trip_id,
            "arrival_time": "" if timepoints and sequence not in TIMEPOINTS else time,
            "departure_time": "" if timepoints and sequence not in TIMEPOINTS else time,
            "stop_id": stop_id,
            "stop_sequence": str(sequence),
        }
        for sequence, stop_id, time in rows
    ]


def bullrunner(*, timepoints: bool = False) -> dict[str, list[dict[str, str]]]:
    """`bullrunner-gtfs.zip`, or its timepoints-only sibling, as GTFS tables."""
    return minimal(
        stops=stop_rows({stop_id: 0 for _, stop_id, _ in BULL_RUNNER_ROWS}),
        trips=trip_rows({"1": "R1"}),
        stop_times=_stop_time_rows("1", BULL_RUNNER_ROWS, timepoints=timepoints),
    )


def testagency() -> dict[str, list[dict[str, str]]]:
    """`testagency.zip` trip `1.1`: stops A, B, C, no stop visited twice.

    Note what is *not* here: a trip `1` or a trip `1234`. Upstream's E036, E037,
    E040, E041, E042, E043 and E044 cases all run against this feed under one of
    those trip_ids, so the static half of the walk never engages for them.
    """
    return minimal(
        stops=stop_rows({"A": 0, "B": 0, "C": 0}),
        trips=trip_rows({"1.1": "R1"}),
        stop_times=_stop_time_rows(
            "1.1",
            ((1, "A", "00:00:00"), (2, "B", "00:10:00"), (3, "C", "00:20:00")),
            timepoints=False,
        ),
    )


def stu(
    stop_sequence: int | None = None,
    stop_id: str | None = None,
    *,
    arrival: Mapping[str, object] | None = None,
    departure: Mapping[str, object] | None = None,
    schedule_relationship: int | None = None,
) -> dict[str, object]:
    """One `stop_time_update`. Every field is absent unless named.

    `arrival={}` is upstream's `StopTimeEvent.newBuilder().build()`: the field is
    present and carries neither a delay nor a time, which is what E044 fires on.
    `arrival=None` is no arrival at all, which is what E043 fires on.
    """
    built: dict[str, object] = {}
    if stop_sequence is not None:
        built["stop_sequence"] = stop_sequence
    if stop_id is not None:
        built["stop_id"] = stop_id
    if arrival is not None:
        built["arrival"] = dict(arrival)
    if departure is not None:
        built["departure"] = dict(departure)
    if schedule_relationship is not None:
        built["schedule_relationship"] = schedule_relationship
    return built


def trip_update(
    *updates: Mapping[str, object],
    trip_id: str | None = None,
    schedule_relationship: int | None = None,
) -> dict[str, object]:
    """A TripUpdate over these stop_time_updates.

    `trip` is written even when empty, because it is `required` in both schemas
    and a TripUpdate without one does not decode.
    """
    trip: dict[str, object] = {}
    if trip_id is not None:
        trip["trip_id"] = trip_id
    if schedule_relationship is not None:
        trip["schedule_relationship"] = schedule_relationship
    return {"trip": trip, "stop_time_update": [dict(update) for update in updates]}


def nine(*sequences: int) -> list[dict[str, object]]:
    """Stop_time_updates carrying only a stop_sequence and an arrival delay.

    Upstream's own long fixtures, which set `setArrival(...setDelay(60))` on
    every one so that E043 and E044 stay quiet and the case is about the rule
    it names.
    """
    return [stu(sequence, arrival={"delay": 60}) for sequence in sequences]


def feed(*trip_updates: Mapping[str, object]) -> Msg:
    """One entity per TripUpdate, every one keeping `FeedMessageTest`'s id.

    Upstream reuses a single `feedEntityBuilder`, so a second entity would carry
    `TEST_ENTITY` too. Since that id reaches the prefix whenever a TripDescriptor
    has no trip_id, giving them distinct ids here would silently rewrite
    upstream's own occurrence text.
    """
    return message(*(entity(trip_update=dict(each)) for each in trip_updates))


def rule_context(
    tmp_path: Path, tables: Mapping[str, list[dict[str, str]]] | None = None
) -> RuleContext:
    """A context over `tables`, defaulting to the feed most of upstream's cases use."""
    return context(tmp_path, dict(tables) if tables is not None else testagency())


def run(
    check,
    tmp_path: Path,
    *trip_updates: Mapping[str, object],
    tables: Mapping[str, list[dict[str, str]]] | None = None,
) -> list[Occurrence]:
    """Call `check` over one entity per TripUpdate, against `tables`."""
    result = check(feed(*trip_updates), rule_context(tmp_path, tables))
    return [] if result is None else list(result)


def walk(
    tmp_path: Path,
    *trip_updates: Mapping[str, object],
    tables: Mapping[str, list[dict[str, str]]] | None = None,
) -> tuple[Event, ...]:
    """Everything the walk yields for one feed, through the memo like a rule."""
    return walk_events(stop_time_updates, feed(*trip_updates), rule_context(tmp_path, tables))


def found(items: Sequence[object]) -> list[str]:
    """Just the prefixes, which is what an assertion about text looks at.

    Takes occurrences or walk events; both carry the prefix and nothing else
    about them differs at an assertion site.
    """
    return [item.prefix for item in items]  # type: ignore[attr-defined]


def ids(items: Iterable[object]) -> list[str]:
    """The rule ids in the order they were produced, which is upstream's order."""
    return [item.rule_id for item in items]  # type: ignore[attr-defined]


def counts(items: Iterable[object]) -> dict[str, int]:
    """`{rule_id: how many}`, the shape of upstream's own `expected` map.

    Takes occurrences or walk events, both of which carry a `rule_id`, so an
    upstream case that names two rules can be ported as one assertion.
    """
    tally: dict[str, int] = {}
    for item in items:
        rule_id = item.rule_id  # type: ignore[attr-defined]
        tally[rule_id] = tally.get(rule_id, 0) + 1
    return tally
