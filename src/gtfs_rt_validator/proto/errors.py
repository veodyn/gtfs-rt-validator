"""The one exception a malformed realtime feed produces.

`BatchProcessor` catches `InvalidProtocolBufferException` around `parseFrom`,
logs, and continues to the next file without writing a results file for it. Our
callers need the same single catch, so every malformed-input path here raises
this and nothing else. Genuine runtime failures (an unreadable file, a full
disk) are not this: they are the caller's problem and keep their own type.
"""

from __future__ import annotations


class DecodeError(Exception):
    """Bytes that protobuf-java would refuse to parse."""

    def __init__(self, reason: str, at: int | None = None) -> None:
        self.reason = reason
        self.at = at
        super().__init__(reason if at is None else f"{reason} (at byte {at})")
