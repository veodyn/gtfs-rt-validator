"""The library API. The CLI is a front end over this, not the other way round.

The library is part of the deliverable rather than a side effect of having a
command line, so it is written down here in full: the entry points, the result
types, the exception model, and the ownership and lifetime rules for the static
context.

## Entry points

- `resolve`, `resolve_roles`, `resolve_walk` turn what a user typed into
  `Inputs`. They touch the filesystem and may open a socket later, through the
  `fetch` callable they are given; they never validate anything.
- `validate(request, *, sink=None) -> Result` is the run. One call reads the
  static feed once, walks every cycle, and returns what was found.
- `Result.write(out_dir) -> WrittenReports` turns a *modern* result into
  `report.json` and `system_errors.json`.
- `ResultsWriter()` is compat's writer, and it is a `sink` rather than a call at
  the end. Upstream writes one `.results.json` beside each input from inside its
  loop, so the unit of work is the message and there is no output directory to
  name; `report/compat.py` says the rest. `Result.write` on a compat result is
  therefore a `UsageError`, not a second output shape.

Validation and writing are separate calls because a library caller usually wants
the notices in memory, and because the two failure modes are different: a run
can fail on its inputs, a write can fail on its output directory.

## Result types

`Result` is the whole run: the mode it ran in, the static feed it ran against,
the `RunResult` the runner produced, and the two wall-clock facts a report needs
(`validated_at`, `validation_time_seconds`). It carries no decoded messages - an
archive replay is thousands of files, and anything that needs one takes the
`sink`, which is called once per validated message as the run goes.

`Result.error_ids()` and `Result.has_errors()` answer `--fail-on-error`. They
have to *join*: an `Occurrence` deliberately carries no severity, so the ids that
fired are looked up in the manifest, which is severity's only home.

## Exception model

Three kinds, and the difference between them is who has to fix it.

- **The feed is wrong.** Not an exception at all. A finding is an `Occurrence`
  appended to a container, and a file this project could not read or decode is a
  system error recorded in the same shape. Both are in the `Result`.
- **The run's inputs are wrong.** `UsageError` for a request that does not
  describe a run, `FileNotFoundError` for an input that is not there,
  `StaticLoadError` for an archive that will not load, `CompatAbort` for a feed
  upstream's own reader would have died on. All are `ValidatorError` or plain
  stdlib errors, all abort the call, and none of them writes anything.
- **This project is wrong.** Anything else. A rule that raises is a bug here,
  and the runner deliberately does not catch it.

## The static context: who owns it, and for how long

1. **One load per `validate` call.** `runner.prepare` is the only code that
   reads the static feed, and `run` takes a prepared config, so "loaded once per
   run" is a property of the types rather than a comment. An archive replay of
   thousands of files reads `feed.zip` once.
2. **`validate` owns the context for the length of the call**, and drops it on
   return. Nothing on `Result` refers to it, and a test asserts that: a report
   that held a context would keep a feed's shapes alive for as long as somebody
   held the report: 449 MB against 30 MB, measured in `tests/test_ignore_shapes.py`.
3. **A context outlives the archive, but the sibling's view does not.**
   `static/adapter.py` copies every row out inside the `with` block, so the
   `StaticContext` a run holds is plain Python data: valid after the zip is
   closed, and after it is deleted. Reading through a `FeedView` afterwards
   would raise `sqlite3.ProgrammingError`, which is why nothing does.
4. **It is never mutated after `StaticContext.build`.** Rules receive it
   read-only through `RuleContext`, and the memoised buffered-shape accessor is
   the only lazily computed part.
5. **There is no supported way to share one across calls.** Two runs against the
   same feed load it twice, deliberately: the alternative is a cache with no
   invalidation rule, on a file that can change between calls. A caller that
   wants one load puts every input in one `Request`.
"""

from __future__ import annotations

import datetime as dt
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from gtfs_rt_validator.inputs import (
    Inputs,
    fetch_once,
    is_url,
    resolve,
    resolve_roles,
    resolve_walk,
)
from gtfs_rt_validator.proto.errors import DecodeError
from gtfs_rt_validator.report import manifest
from gtfs_rt_validator.report.compat import RESULTS_SUFFIX, ResultsWriter
from gtfs_rt_validator.report.modern import REPORT_NAME, SYSTEM_ERRORS_NAME, write_reports
from gtfs_rt_validator.report.summary import RunSummary
from gtfs_rt_validator.rules.registry import severity_for
from gtfs_rt_validator.runner import (
    CompatAbort,
    MessageResult,
    Mode,
    RunResult,
    SortBy,
    prepare,
    run,
)
from gtfs_rt_validator.static.adapter import StaticLoadError
from gtfs_rt_validator.version import VERSION

__all__ = [
    "COMPAT_WRITES_PER_MESSAGE",
    "FAILING_SEVERITY",
    "RESULTS_SUFFIX",
    "VERSION",
    "CompatAbort",
    "DecodeError",
    "Inputs",
    "MessageResult",
    "Mode",
    "Request",
    "Result",
    "ResultsWriter",
    "SortBy",
    "StaticLoadError",
    "UsageError",
    "ValidatorError",
    "WrittenReports",
    "fetch_once",
    "is_url",
    "resolve",
    "resolve_roles",
    "resolve_walk",
    "validate",
]


class ValidatorError(Exception):
    """The base of everything this project raises on purpose."""


class UsageError(ValidatorError):
    """The request does not describe a run. The caller has to change it."""


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
class Request:
    """One run: which validator to be, what to read, and how to read it.

    `sort_by` is on the request as well as inside `Inputs` because it does two
    jobs: it ordered the walk when the inputs were resolved, and it decides
    where each file's clock comes from once the run starts.
    """

    mode: Mode
    gtfs: Path
    inputs: Inputs
    sort_by: SortBy = SortBy.DATE_MODIFIED
    at: dt.datetime | None = None
    ignore_shapes: bool = False
    #: Compat only and opt-in: reproduce upstream's equal-message abort, which
    #: `runner/equal_message.py` reads out of the Java and measures against it.
    abort_on_equal_message: bool = False


@dataclass(frozen=True, slots=True)
class WrittenReports:
    """Where the two files went."""

    report: Path
    system_errors: Path


@dataclass(frozen=True, slots=True)
class Result:
    """What one run found, and the two wall-clock facts a report needs.

    No static context and no decoded messages: see this module's docstring for
    why the first, and `runner.RunResult` for why the second.
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
        """The `summary` block of `report.json`, ready to serialise."""
        return RunSummary(
            validated_at=self.validated_at,
            gtfs_input=self.gtfs_input,
            gtfs_realtime_inputs=self.run.inputs,
            feed_roles=self.run.roles,
            output_directory=None if out_dir is None else str(out_dir),
            validation_report_name=REPORT_NAME,
            system_errors_report_name=SYSTEM_ERRORS_NAME,
            messages_validated=self.run.messages_validated,
            files_skipped=self.run.files_skipped,
            validation_time_seconds=self.validation_time_seconds,
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


def _now() -> str:
    """`validatedAt`, to the second, in the shape the sibling's reports use."""
    return dt.datetime.now(tz=dt.UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def validate(request: Request, *, sink: Callable[[MessageResult], None] | None = None) -> Result:
    """Run the request and return what it found.

    `sink` is handed to the runner unchanged: it is called once per validated
    message, before the duplicate basis moves, which is the hook a per-message
    writer hangs off. It is never called for a run that aborts before the first
    realtime file is opened, which is what makes `CompatAbort` produce nothing.
    """
    started = time.monotonic()
    validated_at = _now()
    config = prepare(
        request.mode,
        request.gtfs,
        ignore_shapes=request.ignore_shapes,
        sort_by=request.sort_by,
        at=request.at,
        directory_replay=request.inputs.directory_replay,
        abort_on_equal_message=request.abort_on_equal_message,
    )
    outcome = run(config, request.inputs.cycles, sink=sink)
    return Result(
        mode=request.mode,
        gtfs_input=str(request.gtfs),
        run=outcome,
        validated_at=validated_at,
        validation_time_seconds=round(time.monotonic() - started, 3),
    )
