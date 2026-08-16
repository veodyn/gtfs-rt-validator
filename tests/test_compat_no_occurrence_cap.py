"""Compat retains every occurrence; upstream has no cap and neither may we.

`RuleUtils.addOccurrence` (`util/RuleUtils.java:37-41`) is an unconditional
`list.add(om)`, and `BatchProcessor.writeResults` serialises whatever that list
holds. The caps this project carries elsewhere are the **sibling's**, for the
modern report, where a bounded file is the whole point.

Left in place under compat they are a silent divergence: the run reports a
plausible file, one occurrence short of upstream's, with nothing anywhere saying
so. A byte comparison would eventually catch it, but only on a results file far
too large to read the diff of, which is the worst way to learn about a cap.

Found by a codex audit of the writer, not by the goldens: every committed golden
holds a handful of occurrences, so no fixture comes within four orders of
magnitude of the cap.

The counts here are the real ones rather than a scaled-down proxy. 100,001
occurrences take 0.06 s to add, measured, so there is no reason to test a
stand-in for the number that actually matters.
"""

from __future__ import annotations

import sys

from gtfs_rt_validator.report.occurrence import (
    MAX_OCCURRENCES_PER_RULE,
    MAX_TOTAL_OCCURRENCES,
    NoticeContainer,
    Occurrence,
)
from gtfs_rt_validator.runner.mode import Mode
from gtfs_rt_validator.runner.run import _message_container

#: One past the per-rule cap: the smallest feed that can tell the two modes
#: apart. Upstream would write all of these.
OVER_THE_CAP = MAX_OCCURRENCES_PER_RULE + 1


def fill(container: NoticeContainer, count: int, rule_id: str = "W002") -> None:
    """`count` occurrences of one rule, the way a feed of TripUpdates missing a
    `vehicle_id` would produce W002."""
    for index in range(count):
        container.add(Occurrence(rule_id, f"trip_id {index}"))


def test_compat_keeps_every_occurrence_past_the_per_rule_cap():
    container = _message_container(Mode.COMPAT)
    fill(container, OVER_THE_CAP)
    assert container.count_for("W002") == OVER_THE_CAP
    assert container.retained_for("W002") == OVER_THE_CAP
    assert container.dropped_for("W002") == 0


def test_modern_still_caps_because_that_cap_is_the_siblings_contract():
    """The other half, so a future "just remove the caps" cannot pass unnoticed.

    Modern output is this project's own and a bounded report is deliberate. The
    count stays true even where the retention does not, which is what lets the
    modern writer say how many it dropped.
    """
    container = _message_container(Mode.MODERN)
    fill(container, OVER_THE_CAP)
    assert container.count_for("W002") == OVER_THE_CAP
    assert container.retained_for("W002") == MAX_OCCURRENCES_PER_RULE
    assert container.dropped_for("W002") == 1


def test_the_compat_container_declares_caps_above_the_siblings():
    """Cheap and direct, so a regression names the cap rather than a count."""
    container = _message_container(Mode.COMPAT)
    assert container.max_per_rule > MAX_OCCURRENCES_PER_RULE
    assert container.max_total > MAX_TOTAL_OCCURRENCES
    assert container.max_per_rule == sys.maxsize
    assert container.max_total == sys.maxsize


def test_the_two_modes_disagree_only_about_retention():
    """A guard on the guard: if the caps were equal, the first two tests would
    both pass while proving nothing about mode."""
    assert _message_container(Mode.COMPAT).max_per_rule != (
        _message_container(Mode.MODERN).max_per_rule
    )
