"""The modern writer: `out/report.json` and `out/system_errors.json`.

Modern output is this project's own, so it is the sibling's shape rather than
the jar's. What that buys is that one reader already knows how to read both:
`{"summary": {...}, "notices": [...]}`, an entry per code carrying the true
total and a bounded sample of the occurrences behind it.

**Severity has one home and it is not here.** An entry's severity is
`registry.severity_for(id)`, looked up by the whole id: the manifest for
upstream's, the registration for a `spec` or `practice` rule, whose id the
generated manifest cannot carry. The writer parses no id: `E`, `W`, `S` and `P`
sort and resolve as complete strings, so a rule whose first letter says nothing
about its severity is not a special case. `tests/test_packed_manifest.py` fails
the build on a severity literal anywhere under `src/`.

**Ordering: entry order is canonical, sample order is the run's.** Rule entries
are sorted by id, ascending, by Unicode code point, so which rule happened to
fire first cannot change the file. The sibling sorts its grouping key, which is
the code with the severity ordinal appended; here the key is the id alone,
because severity is not stored beside an occurrence, and appending it would
change nothing since a code resolves to exactly one severity. This is not
upstream's output order, which is validator registration order and belongs to
the compat writer.

Inside an entry the samples keep discovery order, as the sibling's do, and a
sample's keys keep the order the rule built its context in. Both are data: the
samples are the first N found, in the order the run walked its messages and
entities, and a context's key order is the rule's own field order, the way the
sibling's declared `Notice` fields are Gson's. Sorting either would destroy
information to buy an invariance the run does not need.

So the promise is exact and no larger: **the same sequence of occurrences
produces the same bytes**, and the entry order is invariant even when the
sequence is permuted. Two runs whose occurrences arrive in a different order
differ inside an entry, and that difference is a true report of the two runs
differing. `tests/test_modern_determinism.py` pins both halves, including the
negative: it fails if anyone sorts the samples or the context keys.

**There is no joined message field, in either file.** Upstream's JSON keeps the
occurrence prefix and the rule's occurrence suffix in separate fields and has no
concatenated one, which a run of the jar built from the pinned commit confirms
and `tests/test_jar_output_contract.py` asserts. The join exists only in
upstream's debug log, as `prefix + " " + suffix` at `util/RuleUtils.java:40`,
one space unconditionally, so W003's empty suffix logs a trailing space. It
reaches no output byte in either file. So a sample carries the prefix under
`PREFIX_KEY`, which is upstream's own field name, and the suffix stays in the
manifest under the code the entry already reports.

Three departures from the sibling's writer, each recorded rather than silent:

- **Samples carry `sourceFile` and `entityPath`**, because a run here spans many
  messages where the sibling's run is one feed. The keys come from
  `occurrence.py`, which owns their naming.
- **Entries are built from every rule that fired**, not from the retained
  occurrences. The sibling walks its groups, so a rule whose occurrences were
  all dropped would vanish from the file; here it reports its true total with an
  empty `sampleNotices`, which is the case the two-number shape exists for.
- **`system_errors.json` gets codes of its own.** The sibling has one code for
  the one thing that can fail inside its loader; the four things upstream logs
  and drops here are four different failures and say which. They live in
  `system_errors.py`, which owns everything about recording a failure of the
  run; this module owns turning either container into bytes.

The serialiser is indented and newline-terminated, unlike the sibling's compact
Gson-parity form: that form exists to match a jar byte for byte and no jar reads
this file. Two of its behaviours are kept because they are correctness, not
formatting. A non-finite float is rendered as its Java `toString`, since
`wire.py` unpacks floats straight out of a feed and bare `NaN` is not JSON, and
`allow_nan=False` then makes any missed case loud rather than silent. A lone
surrogate cannot arrive: `decode.py` decodes strings with `errors="replace"`.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path

from gtfs_rt_validator.report import system_errors
from gtfs_rt_validator.report.occurrence import NoticeContainer, Occurrence
from gtfs_rt_validator.report.summary import RunSummary, build_summary
from gtfs_rt_validator.rules import registry

__all__ = [
    "PREFIX_KEY",
    "REPORT_NAME",
    "SYSTEM_ERRORS_NAME",
    "RunSummary",
    "build_report",
    "build_system_errors",
    "dumps_json",
    "ordered_ids",
    "rule_severity",
    "write_reports",
]

REPORT_NAME = "report.json"
SYSTEM_ERRORS_NAME = "system_errors.json"

#: Upstream's own name for the per-occurrence half of the message. A rule that
#: also writes this key into its context shadows the occurrence's prefix.
PREFIX_KEY = "prefix"


def rule_severity(rule_id: str) -> str:
    """The only severity source for a rule, and it answers for every tier.

    `registry.severity_for` reads the manifest for an upstream id and the
    registration for a `spec` or `practice` one, so this writer neither parses
    an id nor knows that the tiers exist. A missing id raises, as it should:
    ids come from the registry, so an unknown one is a rule this project never
    declared rather than anything a feed did.
    """
    return registry.severity_for(rule_id)


def ordered_ids(container: NoticeContainer) -> tuple[str, ...]:
    """Every id that fired, sorted. The ordering contract, in one line."""
    return tuple(sorted(container.rule_ids()))


def _sample(occurrence: Occurrence) -> dict[str, object]:
    """One sample notice: the prefix if there is one, then the context.

    Null context values are dropped, which is what the sibling does and what
    upstream's Gson does before it: a notice field holding null is absent from
    the report rather than present as null.
    """
    sample: dict[str, object] = {PREFIX_KEY: occurrence.prefix} if occurrence.prefix else {}
    sample.update({key: value for key, value in occurrence.context.items() if value is not None})
    return sample


def _entries(
    container: NoticeContainer, severity_of: Callable[[str], str]
) -> list[dict[str, object]]:
    return [
        {
            "code": rule_id,
            "severity": severity_of(rule_id),
            "totalNotices": container.count_for(rule_id),
            "sampleNotices": [_sample(occ) for occ in container.samples_for(rule_id)],
        }
        for rule_id in ordered_ids(container)
    ]


def build_report(
    container: NoticeContainer,
    summary: RunSummary,
    *,
    severity_of: Callable[[str], str] = rule_severity,
) -> dict[str, object]:
    """The whole report, summary first.

    `severity_of` is the seam `build_system_errors` fills with its own source,
    since a system error is not a rule and has no registration to read. Shipped
    code has exactly two callers of it and both are in this module; the default
    answers for all three tiers, so a rule needs nothing here.
    """
    return {"summary": build_summary(summary), "notices": _entries(container, severity_of)}


def build_system_errors(container: NoticeContainer) -> dict[str, object]:
    """The same envelope and the same entry, one severity source lower down.

    A system error has no manifest entry, since it is not one of upstream's 61
    rules; `system_errors.severity` is where that lookup goes instead.
    """
    return {"notices": _entries(container, lambda _: system_errors.severity())}


def _json_safe(value: object) -> object:
    """Render a non-finite float as Java renders it, recursively."""
    if isinstance(value, float) and (value != value or value in (float("inf"), float("-inf"))):
        if value != value:
            return "NaN"
        return "Infinity" if value > 0 else "-Infinity"
    if isinstance(value, dict):
        return {key: _json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    return value


def dumps_json(payload: dict[str, object]) -> str:
    """Indented, UTF-8, no trailing newline: `write_reports` adds that.

    `ensure_ascii=False` leaves a stop name as itself rather than as escapes,
    so the encoding is stated at every write. `allow_nan=False` refuses to
    write bare `NaN`, which is not JSON; `_json_safe` has already replaced the
    values that would have hit it.
    """
    return json.dumps(_json_safe(payload), indent=2, ensure_ascii=False, allow_nan=False)


def _write(text: str, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def write_reports(
    out_dir: Path,
    notices: NoticeContainer,
    system_errors: NoticeContainer,
    summary: RunSummary,
) -> tuple[Path, Path]:
    """Write both files, creating the directory, and say where they went.

    `system_errors.json` is written even when nothing failed: an empty array is
    the run saying it looked, which is the difference between this and
    upstream's silence.
    """
    report_path = out_dir / REPORT_NAME
    system_errors_path = out_dir / SYSTEM_ERRORS_NAME
    _write(dumps_json(build_report(notices, summary)) + "\n", report_path)
    _write(dumps_json(build_system_errors(system_errors)) + "\n", system_errors_path)
    return (report_path, system_errors_path)
