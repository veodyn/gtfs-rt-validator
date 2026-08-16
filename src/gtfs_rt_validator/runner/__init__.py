"""The batch loop: what a run reads, in what order, and what time it happens at.

This package is upstream's `BatchProcessor` taken apart along its seams.

- `mode`: the descriptor and the registry, which is two of the three things mode
  chooses. The third is the writer, and it lives outside this package.
- `clock`: the per-file "current time", derived from the modification time or
  from the file name, never observed from the wall clock.
- `dedupe`: the directory walk and its ordering, and `prevHash` duplicate
  suppression.
- `sources`: one realtime input under one role, and how inputs group into the
  cycles a cross-feed rule sees.
- `gate`: the static feed, loaded once, and the two feeds upstream's reader dies
  on.
- `equal_message`: the fourth death, the one `TimestampValidator` throws mid-run,
  reproduced only when a compat run asks for it.
- `context`: what a rule is handed and what it hands back.
- `acquire`: bytes to a decoded message, or to the reason there is no message.
- `config` and `run`: the loop that drives all of the above.
"""

from __future__ import annotations

from gtfs_rt_validator.runner.clock import (
    ClockSource,
    FileNameTimestampError,
    Reading,
    SortBy,
    compat_reading,
    last_modified_millis,
    millis_from_datetime,
    modern_reading,
    remove_extension,
    timestamp_from_file_name,
)
from gtfs_rt_validator.runner.config import PreparedFeed, prepare_feed
from gtfs_rt_validator.runner.context import (
    DEFAULT_ROLE,
    ROLE_ALERTS,
    ROLE_ORDER,
    ROLE_TRIP_UPDATES,
    ROLE_VEHICLE_POSITIONS,
    CombinedFeed,
    RuleContext,
    RuleContractError,
    RuleResult,
)
from gtfs_rt_validator.runner.dedupe import DuplicateFilter, md5_digest, walk
from gtfs_rt_validator.runner.equal_message import EqualMessageAbort, equal_messages
from gtfs_rt_validator.runner.gate import CompatAbort
from gtfs_rt_validator.runner.mode import Mode
from gtfs_rt_validator.runner.run import (
    MessageResult,
    RunConfig,
    RunResult,
    Source,
    file_cycles,
    prepare,
    role_cycle,
    run,
    url_cycle,
)

__all__ = [
    "DEFAULT_ROLE",
    "ROLE_ALERTS",
    "ROLE_ORDER",
    "ROLE_TRIP_UPDATES",
    "ROLE_VEHICLE_POSITIONS",
    "ClockSource",
    "CombinedFeed",
    "CompatAbort",
    "DuplicateFilter",
    "EqualMessageAbort",
    "FileNameTimestampError",
    "MessageResult",
    "Mode",
    "PreparedFeed",
    "Reading",
    "RuleContext",
    "RuleContractError",
    "RuleResult",
    "RunConfig",
    "RunResult",
    "SortBy",
    "Source",
    "compat_reading",
    "equal_messages",
    "file_cycles",
    "last_modified_millis",
    "md5_digest",
    "millis_from_datetime",
    "modern_reading",
    "prepare",
    "prepare_feed",
    "remove_extension",
    "role_cycle",
    "run",
    "timestamp_from_file_name",
    "url_cycle",
    "walk",
]
