"""What a run needs before it reads a single message, and where it comes from.

`prepare_feed` is the only place the static feed is read, which is how "loaded
once per run" is enforced rather than merely intended: `run` takes a `RunConfig`
and has no path to load from. An archive replay is thousands of files against one
`StaticContext`.

It is also where mode picks two of its three: the descriptor the decoder is
parameterised by and the registry the loop walks. The third, the writer, belongs
to the caller, so `mode` stays on the config for it to switch on.

`PreparedFeed` is that read, held. `prepare` reads one and turns it into a config
in a single call, which is what every run did before this type existed and still
what a run does unless the caller says otherwise. A caller that wants a second
run against the same archive calls `prepare_feed` itself and hands the result to
as many runs as it likes; `api.Request.gtfs` is where that choice is expressed.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from pathlib import Path

from gtfs_rt_validator.proto.descriptor import Schema
from gtfs_rt_validator.report.occurrence import NoticeContainer
from gtfs_rt_validator.rules.registry import Registry
from gtfs_rt_validator.runner.clock import SortBy
from gtfs_rt_validator.runner.gate import prepare_static
from gtfs_rt_validator.runner.mode import Mode
from gtfs_rt_validator.static.context import StaticContext

__all__ = ["PreparedFeed", "RunConfig", "prepare", "prepare_feed"]


@dataclass(frozen=True, slots=True)
class RunConfig:
    """Everything a run needs that is not the messages themselves.

    `system_errors` is on the config rather than created inside `run` because
    the gate records into it before the first realtime file is opened, and one
    container per run is what the modern writer expects.
    """

    mode: Mode
    static: StaticContext
    timezone: str
    registry: Registry
    schema: Schema
    sort_by: SortBy = SortBy.DATE_MODIFIED
    at: dt.datetime | None = None
    directory_replay: bool = False
    system_errors: NoticeContainer = field(default_factory=NoticeContainer)
    #: Whether the loop reproduces upstream's equal-message abort. Decided here
    #: and never in the loop, so `run.py` reads a flag rather than asking which
    #: mode it is in: `prepare` drops the request under modern for the same
    #: reason mode picks the descriptor and the registry here.
    abort_on_equal_message: bool = False


@dataclass(frozen=True, slots=True)
class PreparedFeed:
    """One static archive, read once, for as many runs as the caller wants.

    **Opting in transfers ownership of staleness to the caller.** The archive is
    read when this is built and is not read again: a `PreparedFeed` handed to a
    hundred runs describes the bytes as they were at the first read, however long
    ago that was and whatever has happened to `feed.zip` since. Nothing here
    stats the file, compares an mtime or invalidates anything, because there is
    no invalidation rule this layer could get right. A caller that needs current
    data builds a new one; the default, a `Path` on the request, keeps the old
    behaviour of reading the feed on every call.

    It is worth holding only because reading is the expensive half. Measured on
    the MBTA's archive, 18 MB and 92,360 trips: 48.7 seconds per `validate` call,
    of which about 45 goes to `load_static` and 2.6 to `StaticContext.build`,
    against a sub-second rule pass. Holding one costs about **0.6 GB resident**,
    so it is a commitment in the other direction and not a free win.

    That memory figure is resident set size, taken as the delta across a
    `prepare_feed` call in an otherwise empty interpreter, with a peak of 618 MB
    barely above it. It was 3.55 GB three changes ago, and each of the three is
    worth knowing about because each is a way of accidentally putting it back:

    - `_tables.build_trips` converted a shape's points once per *trip*, so 1,157
      shapes became 25.7 million point tuples. Trips share the shape's polyline.
    - `stop_times.txt` was held as the loaded twelve-column dicts, 1,414 MB of
      it, when four columns are read; `static/_stoptimes.py` keeps those four
      and pools the values.
    - The loader materialised that table before the context could compact it,
      which set a **high water mark of about 2 GB that no later compaction could
      take back**, freed pages not being returned to the operating system. The
      adapter now consumes those rows as they arrive.

    That third one is the trap: after the second change the reachable object
    graph was already 328 MB and RSS was still 2 GB, so measuring the graph
    alone would have reported a win nobody could observe. Measure resident size,
    and measure the peak beside it.

    Re-measure rather than copy the number forward, and say which method
    produced it. An earlier draft said 1.9 GB, which reproduced under neither
    RSS nor `tracemalloc` and understated the cost of that day by nearly half;
    the two answer different questions, and `tracemalloc` roughly doubles the
    wall clock while it is running.

    **It carries the mode and `ignore_shapes` it was built for because both
    change what was read.** Mode picks the reader (`gate.prepare_static` says
    why), and `ignore_shapes` decides whether `shapes.txt` was loaded at all. A
    feed read one way and validated the other is silently wrong rather than
    noisily wrong, so `mismatch` exists and `api.validate` refuses on it.
    """

    #: What the summary calls the feed: `str(path)` at the time it was read.
    gtfs_input: str
    mode: Mode
    ignore_shapes: bool
    static: StaticContext
    #: The timezone every rule reads, already resolved. `str` rather than
    #: `StaticContext.timezone`'s `str | None`: the fallback decision is taken
    #: while reading, not while running.
    timezone: str
    #: What the gate recorded while reading: modern's missing-timezone
    #: substitution and its note about what compat would have refused. Held
    #: rather than spent, and merged into a fresh container for **every** run
    #: that uses this feed, so the hundredth report says as much about the
    #: archive as the first. See `config`.
    system_errors: NoticeContainer = field(default_factory=NoticeContainer)

    def mismatch(self, *, mode: Mode, ignore_shapes: bool) -> str | None:
        """Why this feed cannot answer for a run with those settings, or None.

        Returns the message rather than raising, like `gate.dangling_reference`
        above it: the caller decides what it means, and the caller here is
        `api.validate`, which owns `UsageError` and the vocabulary a library user
        sees. This module would have to import from `api` to raise it.
        """
        if mode is not self.mode:
            return (
                f"this feed was read for {self.mode} mode and the request runs in {mode} mode. "
                f"Mode picks the static reader, so the rows differ: compat reads the archive as "
                f"onebusaway does and keeps raw cell text, modern reads it through the sibling's "
                f"typed path. Prepare a second feed for {mode} rather than sharing this one"
            )
        if ignore_shapes != self.ignore_shapes:
            return (
                f"this feed was read with ignore_shapes={self.ignore_shapes} and the request asks "
                f"for ignore_shapes={ignore_shapes}. The flag decides whether shapes.txt was "
                f"loaded at all, so it cannot be changed after the read. Prepare a second feed"
            )
        return None

    def config(
        self,
        *,
        sort_by: SortBy = SortBy.DATE_MODIFIED,
        at: dt.datetime | None = None,
        directory_replay: bool = False,
        abort_on_equal_message: bool = False,
    ) -> RunConfig:
        """A config for one run against this feed.

        The system-error container is **fresh per config and seeded from this
        feed's**, so what the gate found belongs to every run and what a run
        finds belongs only to that run. `NoticeContainer.merge` sums counts into
        the new container and leaves the source alone, which is what makes
        calling this a hundred times safe.
        """
        system_errors = NoticeContainer()
        system_errors.merge(self.system_errors)
        return RunConfig(
            mode=self.mode,
            static=self.static,
            timezone=self.timezone,
            registry=self.mode.registry(),
            schema=self.mode.schema(),
            sort_by=sort_by,
            at=at,
            directory_replay=directory_replay,
            system_errors=system_errors,
            abort_on_equal_message=abort_on_equal_message and self.mode is Mode.COMPAT,
        )


def prepare_feed(gtfs_path: Path, *, mode: Mode, ignore_shapes: bool = False) -> PreparedFeed:
    """Read the static feed once, for one run or for many.

    This is where the reading happens, so this is where reading fails. Raises
    `CompatAbort` for a feed upstream's reader would have died on and
    `StaticLoadError` for an archive that will not load at all: a caller that
    prepares separately meets both at prepare time rather than at `validate`,
    which is the point of preparing separately.
    """
    system_errors = NoticeContainer()
    static, timezone = prepare_static(
        gtfs_path, mode=mode, system_errors=system_errors, ignore_shapes=ignore_shapes
    )
    return PreparedFeed(
        gtfs_input=str(gtfs_path),
        mode=mode,
        ignore_shapes=ignore_shapes,
        static=static,
        timezone=timezone,
        system_errors=system_errors,
    )


def prepare(
    mode: Mode,
    gtfs_path: Path,
    *,
    ignore_shapes: bool = False,
    sort_by: SortBy = SortBy.DATE_MODIFIED,
    at: dt.datetime | None = None,
    directory_replay: bool = False,
    abort_on_equal_message: bool = False,
) -> RunConfig:
    """Read the static feed once and choose the mode's schema and registry.

    The one-call form: read and configure, with nothing kept afterwards. Raises
    what `prepare_feed` raises, for the reasons given there, and before any
    realtime file is opened, so nothing can have been written by then.

    `abort_on_equal_message` asks for one more of upstream's deaths, the one
    `runner/equal_message.py` describes. It is honoured under compat and dropped
    under modern, where disagreeing with upstream is allowed and throwing away a
    complete report over a repetitive feed is not a trade worth making.
    """
    feed = prepare_feed(gtfs_path, mode=mode, ignore_shapes=ignore_shapes)
    return feed.config(
        sort_by=sort_by,
        at=at,
        directory_replay=directory_replay,
        abort_on_equal_message=abort_on_equal_message,
    )
