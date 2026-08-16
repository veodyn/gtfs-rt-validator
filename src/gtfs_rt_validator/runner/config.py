"""What a run needs before it reads a single message, and where it comes from.

`prepare` is the only place the static feed is read, which is how "loaded once
per run" is enforced rather than merely intended: `run` takes a `RunConfig` and
has no path to load from. An archive replay is thousands of files against one
`StaticContext`.

It is also where mode picks two of its three: the descriptor the decoder is
parameterised by and the registry the loop walks. The third, the writer, belongs
to the caller, so `mode` stays on the config for it to switch on.
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

__all__ = ["RunConfig", "prepare"]


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

    Raises `CompatAbort` for a feed upstream's reader would have died on, before
    any realtime file is opened, so nothing can have been written by then; and
    `StaticLoadError` for an archive that will not load at all, which is a
    failure of the run's inputs rather than a finding about them.

    `abort_on_equal_message` asks for one more of upstream's deaths, the one
    `runner/equal_message.py` describes. It is honoured under compat and dropped
    under modern, where disagreeing with upstream is allowed and throwing away a
    complete report over a repetitive feed is not a trade worth making.
    """
    system_errors = NoticeContainer()
    static, timezone = prepare_static(
        gtfs_path, mode=mode, system_errors=system_errors, ignore_shapes=ignore_shapes
    )
    return RunConfig(
        mode=mode,
        static=static,
        timezone=timezone,
        registry=mode.registry(),
        schema=mode.schema(),
        sort_by=sort_by,
        at=at,
        directory_replay=directory_replay,
        system_errors=system_errors,
        abort_on_equal_message=abort_on_equal_message and mode is Mode.COMPAT,
    )
