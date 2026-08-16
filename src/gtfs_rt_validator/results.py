"""What one run found, and the two ways it reaches disk.

Split out of `api.py`, which stayed the entry points and the prose. The contract
is unchanged and `api` re-exports every name here, so a caller still writes
`api.Result` and `api.FAILING_SEVERITY`.

`Result` is the whole run: the mode it ran in, the static feed it ran against,
the `RunResult` the runner produced, and the two wall-clock facts a report needs.
It carries no static context and no decoded messages: `api.py` says why the
first, `runner.RunResult` why the second.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from gtfs_rt_validator.errors import UsageError
from gtfs_rt_validator.report import manifest
from gtfs_rt_validator.report.modern import REPORT_NAME, SYSTEM_ERRORS_NAME, write_reports
from gtfs_rt_validator.report.summary import RunSummary
from gtfs_rt_validator.rules.registry import severity_for
from gtfs_rt_validator.runner import Mode, RunResult

__all__ = [
    "COMPAT_WRITES_PER_MESSAGE",
    "FAILING_SEVERITY",
    "Result",
    "WrittenReports",
]


#: What `Result.write` says when the mode it was handed does not write that way.
#:
#: Compat's unit of work is the message: upstream writes one file per input from
#: inside its loop, so by the time a `Result` exists there is nothing left to
#: write and no directory upstream has a counterpart for. Naming the sink is the
#: whole of the fix, so the message names it.
COMPAT_WRITES_PER_MESSAGE = (
    "a compat run writes one .results.json beside each input as it goes, so pass "
    "api.ResultsWriter() as validate's sink. There is no directory-shaped compat report."
)


#: The severity `--fail-on-error` fails on.
#:
#: Severity has exactly one home, `report/manifest.py`, and this module may not
#: spell one out: `tests/test_packed_manifest.py` fails the build on a severity
#: literal anywhere under `src/`. So the failing severity is named by reference,
#: through the one constant the manifest exports that means "this is a failure
#: rather than an observation".
#:
#: Open for review: the honest home for this is the manifest itself, as an
#: `is_error(rule_id)` or a severity ordering. It cannot be added here because
#: `data/rules.json` is generated from upstream's Java and `report/` was out of
#: scope for the task that wrote this file. `tests/test_api.py` pins the
#: coupling from outside, where a test may spell a severity.
FAILING_SEVERITY = manifest.SYSTEM_ERROR_SEVERITY


@dataclass(frozen=True, slots=True)
class WrittenReports:
    """Where the two files went."""

    report: Path
    system_errors: Path


@dataclass(frozen=True, slots=True)
class Result:
    """What one run found, and the two wall-clock facts a report needs.

    No static context and no decoded messages: see `api.py`'s docstring for why
    the first, and `runner.RunResult` for why the second.
    """

    mode: Mode
    gtfs_input: str
    run: RunResult
    validated_at: str
    validation_time_seconds: float

    def error_ids(self) -> tuple[str, ...]:
        """The ids that fired at the failing severity, sorted.

        The join `--fail-on-error` needs, resolved through
        `registry.severity_for`, which answers for all three tiers: the manifest
        for an upstream id, the registration for a `spec` or `practice` one.

        An earlier version asked the manifest directly. That was wrong for the
        same reason the modern writer was, and it was a live crash rather than a
        latent one: the manifest holds only upstream's 61 ids, so the first `S`
        or `P` rule to fire raised `KeyError` here the moment anyone passed
        `--fail-on-error`.
        """
        return tuple(
            rule_id
            for rule_id in sorted(self.run.notices.rule_ids())
            if severity_for(rule_id) == FAILING_SEVERITY
        )

    def has_errors(self) -> bool:
        return bool(self.error_ids())

    def summary(self, out_dir: Path | None = None) -> RunSummary:
        """The `summary` block of `report.json`, ready to serialise.

        `rules_run` comes off the `RunResult`, which read it off the registry
        the run was configured with. Nothing here rebuilds a registry to ask it
        what it holds: the point of the field is to report the rules that ran,
        so a second `Registry.modern()` call would answer a different question
        and answer it right even when the run was wrong.
        """
        return RunSummary(
            validated_at=self.validated_at,
            mode=self.mode.value,
            gtfs_input=self.gtfs_input,
            gtfs_realtime_inputs=self.run.inputs,
            feed_roles=self.run.roles,
            output_directory=None if out_dir is None else str(out_dir),
            validation_report_name=REPORT_NAME,
            system_errors_report_name=SYSTEM_ERRORS_NAME,
            messages_validated=self.run.messages_validated,
            files_skipped=self.run.files_skipped,
            validation_time_seconds=self.validation_time_seconds,
            rules_run=self.run.rules_run,
        )

    def write(self, out_dir: Path) -> WrittenReports:
        """Write both reports under `out_dir`, creating it if it is not there.

        Modern only. Compat's writer is a sink, for the reason
        `COMPAT_WRITES_PER_MESSAGE` gives.
        """
        if self.mode is Mode.COMPAT:
            raise UsageError(COMPAT_WRITES_PER_MESSAGE)
        report, system_errors = write_reports(
            out_dir, self.run.notices, self.run.system_errors, self.summary(out_dir)
        )
        return WrittenReports(report, system_errors)
