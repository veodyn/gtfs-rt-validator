"""Findings, and how they become a report.

`occurrence` holds what a rule appends and the container that collects it.
Severity, titles and the per-rule occurrence suffix live in `manifest`, which is
the single home for all three; the writers join the two at the end of a run.
"""

from __future__ import annotations

from gtfs_rt_validator.report.occurrence import (
    ENTITY_PATH_KEY,
    MAX_EXPORTS_PER_RULE,
    MAX_OCCURRENCES_PER_RULE,
    MAX_TOTAL_OCCURRENCES,
    SOURCE_FILE_KEY,
    NoticeContainer,
    Occurrence,
)

__all__ = [
    "ENTITY_PATH_KEY",
    "MAX_EXPORTS_PER_RULE",
    "MAX_OCCURRENCES_PER_RULE",
    "MAX_TOTAL_OCCURRENCES",
    "SOURCE_FILE_KEY",
    "NoticeContainer",
    "Occurrence",
]
