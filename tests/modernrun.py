"""One small run, shared by the modern writer's tests.

Two rules and a capped one: W002 twice, E002 fourteen times against an export
cap of two, so every assertion about the gap between `totalNotices` and
`sampleNotices` has something real to look at.
"""

from __future__ import annotations

from gtfs_rt_validator.report.occurrence import (
    ENTITY_PATH_KEY,
    SOURCE_FILE_KEY,
    NoticeContainer,
    Occurrence,
)
from gtfs_rt_validator.report.summary import RunSummary

MESSAGE = "archive/TripUpdates-2026-08-14T09:00:00Z.pb"

# upstream/rules-7041fa3.json, E002. Written down here so the assertion that it
# never reaches a report has something to look for.
E002_SUFFIX = "is not strictly sorted by increasing stop_sequence"


def occurrence(rule_id: str, index: int) -> Occurrence:
    return Occurrence(
        rule_id=rule_id,
        prefix=f"trip_id 2777{index} stop_sequence {index}",
        context={
            SOURCE_FILE_KEY: MESSAGE,
            ENTITY_PATH_KEY: f"entity[{index}].trip_update",
            "tripId": f"2777{index}",
            "stopSequence": index,
        },
    )


def a_run() -> NoticeContainer:
    container = NoticeContainer(max_exports_per_rule=2)
    container.add(Occurrence("W002", "vehicle_id  trip_id 277716", {"tripId": "277716"}))
    for index in range(14):
        container.add(occurrence("E002", index))
    container.add(Occurrence("W002", "vehicle_id  trip_id 277717", {"tripId": "277717"}))
    return container


def a_summary() -> RunSummary:
    return RunSummary(
        validated_at="2026-08-14T09:00:00Z",
        mode="modern",
        gtfs_input="feed.zip",
        gtfs_realtime_inputs=(MESSAGE,),
        output_directory="out",
        messages_validated=1,
        #: The registry this small run walked, so the writer's tests see the
        #: field a real run fills. What proves it is *derived* rather than
        #: written down is `tests/test_rules_run_inventory.py`, which drives
        #: real runs against deliberately short registries.
        rules_run=("E002", "W002"),
    )
