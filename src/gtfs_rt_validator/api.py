"""The library API. The CLI is a front end over this, not the other way round.

The library is part of the deliverable rather than a side effect of having a
command line, so it is written down here in full: the entry points, the result
types, the exception model, and the ownership and lifetime rules for the static
context. Two of those four outgrew one file and moved next door, to
`results.py` and `errors.py`. Every name is re-exported here, so this module
stays the one a caller imports and the split is an implementation detail.

## Entry points

- `resolve`, `resolve_roles`, `resolve_walk` turn what a user typed into
  `Inputs`. They touch the filesystem and may open a socket later, through the
  `fetch` callable they are given; they never validate anything.
- `validate(request, *, sink=None) -> Result` is the run. One call reads the
  static feed once, walks every cycle, and returns what was found.
- `prepare_feed(path, *, mode, ignore_shapes=False) -> PreparedFeed` does the
  reading and no validating, so a caller that runs repeatedly against one
  archive can pay for it once. Point 5 below is what it costs.
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

`results.py`. `Result` is the whole run and carries no decoded messages: an
archive replay is thousands of files, and anything that needs one takes the
`sink`, which is called once per validated message as the run goes.

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

1. **One load per `validate` call.** `runner.prepare_feed` is the only code that
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
5. **Sharing one across calls is possible, opt-in, and the caller's problem.**
   `Request.gtfs` takes a `Path`, which is read on every call, or a
   `PreparedFeed`, which was read when the caller built it and is not read
   again. There is no cache here and no invalidation rule, because this layer
   has no honest one: a `PreparedFeed` describes an archive as it was, and the
   caller decides when that stops being true. Two runs against a `Path` load it
   twice, deliberately, and that is still the default.
"""

from __future__ import annotations

import datetime as dt
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from gtfs_rt_validator.errors import UsageError, ValidatorError
from gtfs_rt_validator.inputs import (
    Inputs,
    fetch_once,
    is_url,
    resolve,
    resolve_roles,
    resolve_walk,
)
from gtfs_rt_validator.proto.errors import DecodeError
from gtfs_rt_validator.report.compat import RESULTS_SUFFIX, ResultsWriter
from gtfs_rt_validator.results import (
    COMPAT_WRITES_PER_MESSAGE,
    FAILING_SEVERITY,
    Result,
    WrittenReports,
)
from gtfs_rt_validator.runner import (
    CompatAbort,
    MessageResult,
    Mode,
    PreparedFeed,
    SortBy,
    prepare_feed,
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
    "PreparedFeed",
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
    "prepare_feed",
    "resolve",
    "resolve_roles",
    "resolve_walk",
    "validate",
]


@dataclass(frozen=True, slots=True)
class Request:
    """One run: which validator to be, what to read, and how to read it.

    `sort_by` is on the request as well as inside `Inputs` because it does two
    jobs: it ordered the walk when the inputs were resolved, and it decides
    where each file's clock comes from once the run starts.

    `gtfs` is a `Path` or a `PreparedFeed`. A path is read on every call, which
    is the default and the safe answer. A prepared feed was read once by
    `prepare_feed` and is reused as it stands, which is the fast answer for a
    caller validating many times against one archive: point 5 of this module's
    docstring says what the caller takes on by choosing it. `mode` and
    `ignore_shapes` must be the ones it was prepared for, since both change what
    was read; `validate` refuses the mismatch rather than answering wrongly.
    """

    mode: Mode
    gtfs: Path | PreparedFeed
    inputs: Inputs
    sort_by: SortBy = SortBy.DATE_MODIFIED
    at: dt.datetime | None = None
    ignore_shapes: bool = False
    #: Compat only and opt-in: reproduce upstream's equal-message abort, which
    #: `runner/equal_message.py` reads out of the Java and measures against it.
    abort_on_equal_message: bool = False


def _now() -> str:
    """`validatedAt`, to the second, in the shape the sibling's reports use."""
    return dt.datetime.now(tz=dt.UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _feed_for(request: Request) -> PreparedFeed:
    """The request's static feed: the caller's if it brought one, else read now.

    The refusal is here rather than in `PreparedFeed`, which returns the reason
    as a string: `UsageError` is this module's vocabulary, and `runner/config.py`
    would have to import from `api` to raise it.
    """
    if isinstance(request.gtfs, PreparedFeed):
        mismatch = request.gtfs.mismatch(mode=request.mode, ignore_shapes=request.ignore_shapes)
        if mismatch is not None:
            raise UsageError(mismatch)
        return request.gtfs
    return prepare_feed(request.gtfs, mode=request.mode, ignore_shapes=request.ignore_shapes)


def validate(request: Request, *, sink: Callable[[MessageResult], None] | None = None) -> Result:
    """Run the request and return what it found.

    `sink` is handed to the runner unchanged: it is called once per validated
    message, before the duplicate basis moves, which is the hook a per-message
    writer hangs off. It is never called for a run that aborts before the first
    realtime file is opened, which is what makes `CompatAbort` produce nothing.

    A `Path` on the request is read here, so `CompatAbort` and `StaticLoadError`
    are raised from this call. A `PreparedFeed` was read when it was built, so
    they were raised there instead, and what remains here is the mismatch check.
    Either way the system errors the read recorded are in this run's report:
    they belong to the archive, not to the first run that noticed them.
    """
    started = time.monotonic()
    validated_at = _now()
    feed = _feed_for(request)
    config = feed.config(
        sort_by=request.sort_by,
        at=request.at,
        directory_replay=request.inputs.directory_replay,
        abort_on_equal_message=request.abort_on_equal_message,
    )
    outcome = run(config, request.inputs.cycles, sink=sink)
    return Result(
        mode=request.mode,
        gtfs_input=feed.gtfs_input,
        run=outcome,
        validated_at=validated_at,
        validation_time_seconds=round(time.monotonic() - started, 3),
    )
