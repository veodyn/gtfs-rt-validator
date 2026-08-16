"""The `summary` object of modern `report.json`.

The sibling writes `{"summary": {...}, "notices": [...]}` and this project
writes the same two keys, so the field set starts from the sibling's
`summary/__init__.py` rather than from taste. Three rules are carried over
verbatim:

- **Declaration order is field order.** The dataclass below is the order the
  keys land in the file, as Gson serialises `JsonReportSummary`'s declaration
  order on the far side.
- **A null field is absent, not null.** A key never set disappears; a key set
  to `""` stays. Those are different states and the file shows the difference,
  so `_drop_nulls` is not a tidy-up.
- **Nothing here reads a clock.** Every run-dependent value arrives as an
  argument, which is what makes the writer's output reproducible.

Where this project differs from the sibling, and why:

- **`gtfsRealtimeInputs` and `feedRoles` are new.** A run here is a static feed
  plus one or more realtime messages, possibly under the named roles `-tu`,
  `-vp` and `-sa`. The sibling's run is a single archive and has no analogue.
- **`messagesValidated` and `filesSkipped` are new**, for the same reason: an
  archive replay is thousands of files and a summary that cannot say how many
  were read, or how many were skipped as duplicates or decode failures, does
  not describe the run.
- **`threads` is dropped.** Nothing here runs in parallel yet, so reporting a
  thread count would be a claim, not a fact.
- **`countryCode` and `dateForValidation` are dropped.** Both are static-feed
  concepts. The realtime analogue of the validation date is the per-file clock
  from `runner/clock.py`, which differs per message, so a single run-level date
  would be false for every file but one.
- **`feedInfo`, `agencies`, `files`, `counts`, `gtfsFeatures` and
  `memoryUsageRecords` are dropped.** The sibling reads them out of an open
  store during its own pipeline; this project holds the static feed through
  `static/adapter.py`, which exposes tables rather than those facts. Adding them
  means deciding what the realtime equivalent of a feature list is, and that
  decision has not been made.
- **`htmlReportName` is dropped.** There is no HTML report.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from gtfs_rt_validator.version import VERSION

__all__ = ["RUN_DEPENDENT", "RunSummary", "build_summary"]

#: Summary fields that legitimately differ between two runs over the same
#: inputs: a wall clock and an elapsed time. Both arrive as arguments, so the
#: writer itself stays deterministic; a byte comparison across runs has to know
#: this set, and there is one definition of it rather than one per harness.
RUN_DEPENDENT = ("validatedAt", "validationTimeSeconds")


@dataclass(frozen=True)
class RunSummary:
    """What the summary needs from the invocation rather than from the feeds.

    `validated_at` has no default on purpose: it is a wall clock, and a writer
    that reached for one would make its own output irreproducible.
    """

    validated_at: str
    validator_version: str = VERSION
    gtfs_input: str | None = None
    gtfs_realtime_inputs: tuple[str, ...] = ()
    feed_roles: dict[str, str] = field(default_factory=dict)
    output_directory: str | None = None
    validation_report_name: str | None = None
    system_errors_report_name: str | None = None
    messages_validated: int | None = None
    files_skipped: int | None = None
    validation_time_seconds: float | None = None


def _drop_nulls(payload: dict[str, object]) -> dict[str, object]:
    """The sibling's rule, which is Gson's default: a null field is absent."""
    return {key: value for key, value in payload.items() if value is not None}


def build_summary(summary: RunSummary) -> dict[str, object]:
    """The summary object, ready to serialise.

    An empty list or mapping is kept rather than dropped, matching the sibling's
    split between "never set" and "set to empty": a run with no realtime input
    is a different thing from a run whose inputs were not recorded.
    """
    return _drop_nulls(
        {
            "validatorVersion": summary.validator_version,
            "validatedAt": summary.validated_at,
            "gtfsInput": summary.gtfs_input,
            "gtfsRealtimeInputs": list(summary.gtfs_realtime_inputs),
            "feedRoles": dict(summary.feed_roles),
            "outputDirectory": summary.output_directory,
            "validationReportName": summary.validation_report_name,
            "systemErrorsReportName": summary.system_errors_report_name,
            "messagesValidated": summary.messages_validated,
            "filesSkipped": summary.files_skipped,
            "validationTimeSeconds": summary.validation_time_seconds,
        }
    )
