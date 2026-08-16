"""S026: an impact_period outside every communication_period.

`Alert.impact_period`'s comment, at `:636`:

    If communication_period is specified, every time interval in impact_period
    must be fully contained within at least one time interval of
    communication_period.

`communication_period` is when an alert is shown for information and
`impact_period` is when service is actually affected, so an impact the producer
never communicates is an alert nobody sees at the time it matters.

**An absent bound is an infinite one**, which `TimeRange` states outright at
`:745` and `:750`: "If missing, the interval starts at minus infinity" and "If
missing, the interval ends at plus infinity". So an impact interval with no
`end` is contained only by a communication interval with no `end` either.

**Containment is `start <= start` and `end <= end`**, shared endpoints included.
`TimeRange`'s own comment makes an interval active for `start <= t < end`, so
two intervals with the same bounds admit the same instants and one contains the
other. "At least one" is also the clause's own word: two adjacent communication
intervals do not merge into a window an impact may straddle, because the
sentence asks about one interval rather than about their union.
"""

from __future__ import annotations

import math
from collections.abc import Iterator, Sequence
from typing import TYPE_CHECKING

from gtfs_rt_validator.report import manifest
from gtfs_rt_validator.report.occurrence import ENTITY_PATH_KEY, Occurrence
from gtfs_rt_validator.rules._shared.walk_entities import entities
from gtfs_rt_validator.rules.registry import rule

if TYPE_CHECKING:  # `runner.context` reaches the static layer, and so the sibling.
    from gtfs_rt_validator.proto.decode import Msg
    from gtfs_rt_validator.runner.context import RuleContext

RULE_ID = "S026"

CLAUSE = (
    "spec: If communication_period is specified, every time interval in impact_period "
    "must be fully contained within at least one time interval of communication_period."
)

ALERT = "alert"
IMPACT = "impact_period"
COMMUNICATION = "communication_period"

Interval = tuple[float, float]


@rule(RULE_ID, source=CLAUSE, severity=manifest.Severity.ERROR)
def check(message: Msg, ctx: RuleContext) -> Sequence[Occurrence]:
    return [
        occurrence
        for record in entities(message, ctx).carrying(ALERT)
        for occurrence in _uncommunicated(record.entity.get(ALERT), record.entity_id, record.path)
    ]


def _uncommunicated(alert: Msg, entity_id: str, path: str) -> Iterator[Occurrence]:
    communication = [_interval(each) for each in alert.get(COMMUNICATION)]
    if not communication:
        return
    for index, each in enumerate(alert.get(IMPACT)):
        impact = _interval(each)
        if not any(_contains(window, impact) for window in communication):
            yield Occurrence(
                RULE_ID,
                f"alert ID {entity_id} {IMPACT}[{index}] ({_text(impact)}) "
                f"is not fully contained in any {COMMUNICATION}",
                {ENTITY_PATH_KEY: f"{path}.{ALERT}.{IMPACT}[{index}]"},
            )


def _interval(time_range: Msg) -> Interval:
    """The pair the proto describes, with the missing bounds made infinite.

    Presence rather than the value: `start` and `end` are `uint64` with a proto2
    default of 0, so an absent `start` read through `get` alone would be the
    epoch rather than minus infinity, and an absent `end` would put the interval
    before every impact instead of after all of them.
    """
    start = time_range.get("start") if time_range.has("start") else -math.inf
    end = time_range.get("end") if time_range.has("end") else math.inf
    return start, end


def _contains(window: Interval, inner: Interval) -> bool:
    return window[0] <= inner[0] and inner[1] <= window[1]


def _text(interval: Interval) -> str:
    return f"{_bound(interval[0], 'minus')} to {_bound(interval[1], 'plus')}"


def _bound(value: float, direction: str) -> str:
    return f"{direction} infinity" if math.isinf(value) else str(value)
