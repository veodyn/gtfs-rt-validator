"""Bytes to a decoded message, or to the reason there is no message.

`BatchProcessor` L206 to L240 in its own order: read, hash, compare with the
duplicate basis, take the clock, decode. Every arm that returns `None` is an arm
where upstream logs and writes **no results file at all** for that input, which
is the parity behaviour; recording why is the deliberate improvement, and the
compat writer simply never reads the container it is recorded in.

Only two exceptions are caught here, and both describe the input rather than
this project: `OSError` from a file that will not open, and `DecodeError` from
bytes protobuf-java would itself have refused. Nothing else is caught anywhere
in this package.
"""

from __future__ import annotations

from dataclasses import dataclass

from gtfs_rt_validator.proto.decode import Msg, decode
from gtfs_rt_validator.proto.errors import DecodeError
from gtfs_rt_validator.report.system_errors import (
    SystemErrorCode,
    code_for_decode_error,
    system_error,
)
from gtfs_rt_validator.runner.clock import (
    FileNameTimestampError,
    Reading,
    compat_reading,
    modern_reading,
    timestamp_from_file_name,
)
from gtfs_rt_validator.runner.config import RunConfig
from gtfs_rt_validator.runner.dedupe import DuplicateFilter, md5_digest
from gtfs_rt_validator.runner.mode import Mode
from gtfs_rt_validator.runner.sources import Source

__all__ = ["Decoded", "acquire"]


@dataclass(frozen=True, slots=True)
class Decoded:
    """One message that decoded, and the three facts the loop needs about it."""

    source: Source
    reading: Reading
    digest: bytes
    message: Msg


def acquire(source: Source, config: RunConfig, duplicates: DuplicateFilter) -> Decoded | None:
    """The message, or `None` where upstream would have written nothing."""
    try:
        data = source.read()
    except OSError as unreadable:
        system_error(config.system_errors, SystemErrorCode.UNREADABLE_FILE, source.name, unreadable)
        return None
    digest = md5_digest(data)
    if duplicates.is_duplicate(digest):
        return None
    reading = _reading(source, config)
    try:
        message = decode(data, config.schema)
    except DecodeError as undecodable:
        system_error(
            config.system_errors, code_for_decode_error(undecodable), source.name, undecodable
        )
        return None
    return Decoded(source, reading, digest, message)


def _reading(source: Source, config: RunConfig) -> Reading:
    """The clock, and the one place mode genuinely branches inside the loop.

    It branches because the two modes take the time from different places, which
    `clock.py` owns; no rule sees the difference, only a different number.
    """
    if config.mode is Mode.COMPAT:
        if source.path is None:
            raise ValueError(
                f"{source.name} has no path, and compat takes its clock from the file: upstream's "
                f"batch mode reads a directory and has no URL input at all"
            )
        reading = compat_reading(source.path, config.sort_by)
    else:
        reading = modern_reading(
            source.path,
            at=config.at,
            directory_replay=config.directory_replay,
            sort_by=config.sort_by,
        )
    if reading.fallback_reason is not None and source.path is not None:
        _record_unparsable_name(source, config)
    return reading


def _record_unparsable_name(source: Source, config: RunConfig) -> None:
    """Re-derive the failure the clock swallowed, so the record can name it.

    `Reading.fallback_reason` is upstream's log line; `system_errors.json` wants
    the exception behind it. Repeating the parse is cheaper than widening
    `clock.py`'s contract, which was measured against the jar as it stands, and
    this path is only reached on the fallback.
    """
    if source.path is None:  # pragma: no cover - the caller has already checked
        return
    try:
        timestamp_from_file_name(source.path.name)
    except FileNameTimestampError as failed:
        system_error(
            config.system_errors,
            SystemErrorCode.UNPARSABLE_FILE_NAME_TIMESTAMP,
            source.name,
            failed,
            context={"javaException": failed.java_exception},
        )
