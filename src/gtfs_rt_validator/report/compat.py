"""The compat writer: one `.results.json` beside each input, as upstream's.

**The unit of work is the message, not the run.** `BatchProcessor` writes a file
per input inside the loop (`writeResults` at `BatchProcessor.java:284`), so this
writer hangs off `validate`'s `sink` rather than off `Result.write`. There is no
output directory: upstream writes `path.toAbsolutePath() + ".results.json"`,
beside the file it was handed and whatever that file's extension was. A file
upstream skips gets no output file at all, which this writer reproduces by never
being called for one: the runner calls the sink only for a message that decoded
and passed the duplicate gate.

A validated message with nothing to report still gets a file holding `[ ]`,
three bytes and no newline. `writeResults` (`BatchProcessor.java:284`) is
unconditional and serialises `allErrorLists`, which is empty because each
validator adds a group only for a non-empty list.

**Measured, not reasoned.** No committed golden has a clean feed, so this was
first derived from the Java and then checked against the jar: a 15-byte feed
carrying only a v2.0 header, `FULL_DATASET` and a timestamp at the file's pinned
mtime produces `clean.pb.results.json` of exactly `b"[ ]"`. See
`tests/test_compat_empty_results.py`, which re-runs that against the jar when one
is built and skips when it is not.

**What one file holds.** A JSON list of `ErrorListHelperModel`, one entry per
rule that fired, each carrying the five strings of upstream's `ValidationRule`
inline and the occurrences behind it. The five come from `report/manifest.py`,
which is severity's only home and the packed form of the same commit the jar was
built from; none of them is spelled here.

**The ordering contract**, which is as much a part of the bytes as the layout:

1. Rule groups in `BatchProcessor` registration order, across validators.
2. Within one validator, its rules in the order its `validate()` tail calls
   `errors.add(...)`. That is `manifest.group_order()`, and every batch-reachable
   rule appears in exactly one group, so the two together are one flat order over
   the 56.
3. Occurrences within a rule in the order the walk produced them. Nothing is
   sorted and nothing is de-duplicated, because upstream's `addOccurrence` does
   neither, and `CrossFeedDescriptorValidator`'s two rules are ordered by Java
   hash iteration, which `rules/_shared/javahash.py` reproduces upstream of here.
   A writer that sorted would destroy exactly that.

The occurrences an entry carries are the ones the container retained. That is
the only place this writer can differ from upstream, which has no retention cap
at all, and it is the container's cap rather than the writer's choice.

Stdlib only, and no import of the runner at run time: the sink is duck-typed on
`source` and `notices`, and the type-only import below is what names it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from functools import cache
from pathlib import Path
from typing import TYPE_CHECKING

from gtfs_rt_validator.report import jackson, manifest
from gtfs_rt_validator.report.occurrence import NoticeContainer, Occurrence

if TYPE_CHECKING:  # Type-only: nothing under `report/` imports the runner.
    from gtfs_rt_validator.runner import MessageResult
    from gtfs_rt_validator.runner.sources import Source

__all__ = [
    "RESULTS_SUFFIX",
    "ResultsWriter",
    "dumps",
    "entries",
    "output_order",
    "results_path",
    "validation_rule",
    "write_results",
]

#: `BatchProcessor.RESULTS_FILE_EXTENSION`, appended to the input path whole.
RESULTS_SUFFIX = ".results.json"


@cache
def output_order() -> tuple[str, ...]:
    """The 56 batch-reachable ids in the order a results file reports them.

    Registration order across validators, `errors.add` order within one. Both
    halves are generated from upstream's Java into `data/rules.json`; neither is
    written down here, so a change upstream arrives through the manifest.
    """
    groups = manifest.group_order()
    return tuple(
        rule_id for validator in manifest.registration_order() for rule_id in groups[validator]
    )


def _ordered_groups(container: NoticeContainer) -> dict[str, list[Occurrence]]:
    """The container's occurrences grouped by rule, in output order.

    An id outside the 56 raises rather than being dropped. Under `--compat` the
    registry cannot produce one, so a container holding an `S` or `P` rule, or
    E010, came from a modern run: writing it as compat output would silently
    lose findings and silently claim to be upstream.
    """
    grouped = container.grouped()
    unknown = sorted(set(grouped) - set(output_order()))
    if unknown:
        raise ValueError(
            f"{', '.join(unknown)} is not a rule BatchProcessor can reach, so it has no place "
            "in compat output; this container did not come from a compat run"
        )
    return {rule_id: grouped[rule_id] for rule_id in output_order() if rule_id in grouped}


def validation_rule(rule_id: str) -> dict[str, object]:
    """Upstream's `ValidationRule` bean, in its declaration order.

    Public because it is the only way to build that bean. `manifest.rule()` is
    exported and carries all five values, but as a snake_case dataclass, so a
    caller assembling MobilityData's webapp-shaped body (`report` beside an
    `enabledRules` list of these) would otherwise have to re-implement the
    five-key rename here and let it drift from the writer it mirrors.
    `entries()` and `output_order()` are the rest of that surface.
    """
    rule = manifest.rule(rule_id)
    return {
        "errorId": rule.error_id,
        "severity": rule.severity,
        "title": rule.title,
        "errorDescription": rule.error_description,
        "occurrenceSuffix": rule.occurrence_suffix,
    }


#: The name this was reachable under before it was public. Kept because a
#: consumer was told the export would be additive, and removing the old spelling
#: in the same breath would have made that untrue. Nothing here reads it and it
#: can go once no caller does.
_validation_rule = validation_rule


def _occurrence(occurrence: Occurrence) -> dict[str, object]:
    """One `OccurrenceModel`. `occurrenceId` is an unboxed `int` nothing sets,
    so it serialises as zero, and `messageLogModel` is the webapp's."""
    return {"occurrenceId": 0, "messageLogModel": None, "prefix": occurrence.prefix}


def _entry(rule_id: str, occurrences: list[Occurrence]) -> dict[str, object]:
    """One `ErrorListHelperModel`: a `MessageLogModel` and its occurrences.

    `messageId` is a boxed `Integer` nothing sets, so it is null rather than the
    zero upstream's README shows; `gtfsRtFeedIterationModel` and `errorDetails`
    are the monitoring webapp's and are null in a batch run.
    """
    return {
        "errorMessage": {
            "messageId": None,
            "gtfsRtFeedIterationModel": None,
            "validationRule": validation_rule(rule_id),
            "errorDetails": None,
        },
        "occurrenceList": [_occurrence(one) for one in occurrences],
    }


def entries(container: NoticeContainer) -> list[dict[str, object]]:
    """One message's findings as the list upstream serialises, in output order."""
    return [_entry(rule_id, found) for rule_id, found in _ordered_groups(container).items()]


def dumps(container: NoticeContainer) -> str:
    """One results file as text: Jackson's layout, and no trailing newline."""
    return jackson.dumps(entries(container))


def results_path(source: Source) -> Path:
    """Where upstream would have written this input's results.

    The input path with the suffix appended, extension included, because that is
    what `path.toAbsolutePath() + RESULTS_FILE_EXTENSION` produces. A source with
    no path cannot be written beside: upstream's batch surface takes a directory
    of files and has no URL input, so this is a bug here rather than anything a
    feed did.
    """
    if source.path is None:
        raise ValueError(
            f"{source.name} has no path to write beside; upstream's batch processor reads a "
            f"directory of files and writes each result next to its input"
        )
    return source.path.parent / f"{source.path.name}{RESULTS_SUFFIX}"


def write_results(message: MessageResult) -> Path:
    """Write one validated message's results file and say where it went."""
    path = results_path(message.source)
    path.write_bytes(dumps(message.notices).encode("utf-8"))
    return path


@dataclass
class ResultsWriter:
    """`validate`'s sink for a compat run, remembering what it wrote.

    Stateful only in that it records the paths, which is what a caller needs to
    report a run; the writing itself is `write_results` and takes nothing but
    the message.
    """

    written: list[Path] = field(default_factory=list)

    def __call__(self, message: MessageResult) -> None:
        self.written.append(write_results(message))
