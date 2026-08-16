"""Decode the same bytes with our reader and with the real protobuf library.

The library is the oracle for the *current* schema only. It cannot speak for the
2015 view or for protobuf-java, so it does not settle compat;
`tools/diff_compat_against_jar.py`, which runs a jar built from the pinned SHA,
does that. What this catches is our wire handling being wrong in a way that both
our encoder and our decoder agree on, which no round-trip test can see.

The comparison is over every field, recursively and presence-aware, not over
entity ids: each side is flattened to a `{dotted.path: value}` mapping keyed like
`entity[0].trip_update.trip.trip_id`, and the union of the two key sets is
compared. An id-only comparison would print MATCH for a feed in which every
header field, scalar, enum and presence bit disagreed.

Run: python tools/diff_decoder_against_bindings.py path/to/*.pb
"""

from __future__ import annotations

import math
import sys
from pathlib import Path
from typing import Any

from google.transit import gtfs_realtime_pb2  # dev-only oracle

from gtfs_rt_validator.proto.decode import Msg, decode
from gtfs_rt_validator.proto.schema_current import SCHEMA

# A present-but-empty submessage contributes no leaf paths, so without a marker
# it would be indistinguishable from an absent one on both sides at once.
EMPTY_MESSAGE = "<empty message>"
ABSENT = object()

# latitude/longitude/bearing/odometer are `float` on the wire, so a Python float
# round-trip is not bit-exact against the library's own 32-bit value.
FLOAT_REL_TOL = 1e-6


def _is_repeated(fd: Any) -> bool:
    """Whether a library field descriptor is repeated.

    protobuf 7.x removed `FieldDescriptor.label`, so reading it unguarded raises
    AttributeError against the version installed here; `is_repeated` is the
    replacement and LABEL_REPEATED == 3 is the fallback for older releases.
    """
    repeated = getattr(fd, "is_repeated", None)
    if repeated is not None:
        return bool(repeated)
    return fd.label == 3


def flatten_theirs(pb: Any, out: dict[str, Any], prefix: str = "") -> None:
    """Flatten a real protobuf message. `ListFields()` yields present fields only."""
    fields = pb.ListFields()
    if not fields and prefix:
        out[prefix.rstrip(".")] = EMPTY_MESSAGE
        return
    for fd, value in fields:
        path = f"{prefix}{fd.name}"
        is_message = fd.message_type is not None
        if _is_repeated(fd):
            for index, item in enumerate(value):
                key = f"{path}[{index}]"
                if is_message:
                    flatten_theirs(item, out, f"{key}.")
                else:
                    out[key] = item
        elif is_message:
            flatten_theirs(value, out, f"{path}.")
        else:
            out[path] = value


def flatten_ours(msg: Msg, out: dict[str, Any], prefix: str = "") -> None:
    """Flatten one of our decoded messages. `has()` is the presence bit."""
    present = [fd for fd in msg.desc.fields if msg.has(fd.name)]
    if not present and prefix:
        out[prefix.rstrip(".")] = EMPTY_MESSAGE
        return
    for fd in present:
        path = f"{prefix}{fd.name}"
        value = msg.get(fd.name)
        if fd.label == "repeated":
            for index, item in enumerate(value):  # type: ignore[union-attr]
                key = f"{path}[{index}]"
                if fd.kind == "message":
                    flatten_ours(item, out, f"{key}.")
                else:
                    out[key] = item
        elif fd.kind == "message":
            flatten_ours(value, out, f"{path}.")  # type: ignore[arg-type]
        else:
            out[path] = value


def same(theirs_value: Any, ours_value: Any) -> bool:
    if theirs_value is ABSENT or ours_value is ABSENT:
        return False
    both_numeric = isinstance(theirs_value, (int, float)) and isinstance(ours_value, (int, float))
    either_float = isinstance(theirs_value, float) or isinstance(ours_value, float)
    if both_numeric and either_float:
        return math.isclose(theirs_value, ours_value, rel_tol=FLOAT_REL_TOL, abs_tol=0.0)
    return bool(theirs_value == ours_value) and type(theirs_value) is type(ours_value)


def render(value: Any) -> str:
    return "<absent>" if value is ABSENT else repr(value)


def ours(path: Path) -> dict[str, Any]:
    out: dict[str, Any] = {}
    flatten_ours(decode(path.read_bytes(), SCHEMA), out)
    return out


def theirs(path: Path) -> dict[str, Any]:
    feed = gtfs_realtime_pb2.FeedMessage()
    feed.ParseFromString(path.read_bytes())
    out: dict[str, Any] = {}
    flatten_theirs(feed, out)
    return out


def compare(real: dict[str, Any], mine: dict[str, Any]) -> list[str]:
    diffs = []
    for key in sorted(set(real) | set(mine)):
        their_value = real.get(key, ABSENT)
        our_value = mine.get(key, ABSENT)
        if not same(their_value, our_value):
            diffs.append(f"{key}: theirs={render(their_value)} ours={render(our_value)}")
    return diffs


def main(paths: list[str]) -> int:
    failures = 0
    compared = 0
    for name in paths:
        path = Path(name)
        real, mine = theirs(path), ours(path)
        compared += len(set(real) | set(mine))
        diffs = compare(real, mine)
        if diffs:
            failures += 1
            print(f"DIFF {path}")
            for line in diffs:
                print(f"  {line}")
    print(f"{compared} field value(s) compared across {len(paths)} file(s)")
    print("MATCH" if not failures else f"{failures} file(s) differ")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
