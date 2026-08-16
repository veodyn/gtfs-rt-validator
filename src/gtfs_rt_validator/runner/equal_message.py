"""`feedMessage.equals(previousFeedMessage)`, and the abort behind it.

`TimestampValidator.java:66-68` throws `IllegalArgumentException` when a message
equals the one before it. Nothing catches it: `BatchProcessor.java:263` calls the
validator bare, `Main.java:62` calls `processFeeds` bare, and `Main` declares
`IOException | NoSuchAlgorithmException` only. So the exception leaves `main` and
the run dies where it stands.

Measured against the pinned jar on this machine: staged as `1.pb`, `2.pb` (an
equal message with different bytes) and `3.pb`, the jar exits 1, writes
`1.pb.results.json`, and writes nothing for `2.pb` or for `3.pb`. Losing the
files *after* the offending one is the part worth stating twice, because a guard
that only skipped the offending file would look right and be wrong.

**This is not the MD5 skip.** `BatchProcessor.java:214-218` compares the digest
of the *bytes*; the guard above compares the *decoded fields*. Two files whose
wire field order differs and whose content does not pass the first and reach the
second, so the abort is reachable rather than theoretical. `runner/dedupe.py`
owns the byte half, and it runs first here exactly as it does upstream.

**Why a guard here and not a raise inside E017's walk.** Mode is descriptor,
registry and writer, never a branch inside a rule. Upstream throws from the third
of nine validators, before anything is written for that file, so checking before
the registry walk instead of partway through it is observationally identical: the
two validators that would have run first (`CrossFeedDescriptorValidator` and
`VehicleValidator`) have their findings discarded either way, because
`writeResults` at `:284` is never reached.

**Equality is protobuf-java's, not Python's.** Generated `equals` compares
presence then value for a singular field, elementwise for a repeated one, and
`getUnknownFields()` last. Two details are worth the code they cost:

- floats go through `Float.floatToIntBits`, which folds every NaN onto one bit
  pattern and keeps `-0.0` apart from `0.0`. Python's `==` does the opposite on
  both counts, so this module compares bit patterns.
- `UnknownFieldSet` is a map from field number to per-wire-type *lists*, so the
  order unknown fields arrived in does not matter but their order within one
  number and type does. Varint and length-delimited payloads are re-read here so
  that a non-canonical length prefix cannot make two equal sets compare apart.

A group retained as an unknown field is compared by its raw bytes, where
`UnknownFieldSet` would parse it into a nested set. That is stricter than
upstream, so it can only decline an abort upstream would take, and no shipped
encoder writes a group into a GTFS-Realtime feed. Recorded rather than fixed.
"""

from __future__ import annotations

import math
import struct

from gtfs_rt_validator.proto import wire
from gtfs_rt_validator.proto.decode import Msg
from gtfs_rt_validator.proto.descriptor import FieldDesc
from gtfs_rt_validator.runner.gate import CompatAbort

__all__ = ["EQUAL_MESSAGE", "EqualMessageAbort", "equal_messages", "guard_equal_message"]

#: `TimestampValidator.java:67`, verbatim. A wrapper script grepping the jar's
#: stack trace finds the same sentence here.
EQUAL_MESSAGE = "feedMessage and previousFeedMessage must not be the same"

#: `Float.floatToIntBits` and `Double.doubleToLongBits` collapse every NaN onto
#: one value. These are those two canonical patterns, big-endian.
_CANONICAL_NAN = {"float": b"\x7f\xc0\x00\x00", "double": b"\x7f\xf8\x00\x00\x00\x00\x00\x00"}
_PACK = {"float": ">f", "double": ">d"}


class EqualMessageAbort(CompatAbort):
    """Upstream's `IllegalArgumentException`, reached and not caught.

    A `CompatAbort` because the observable outcome is the same one: no results
    file for this input and none for any input after it. Unlike the gate's three,
    this one is raised mid-run, so files validated *before* it keep the results
    upstream had already written for them.
    """


def guard_equal_message(message: Msg, previous: Msg, source: str) -> None:
    """Throw where `TimestampValidator` throws, or return and let the run go on."""
    if equal_messages(message, previous):
        raise EqualMessageAbort(f"{source}: {EQUAL_MESSAGE}")


def equal_messages(left: Msg, right: Msg) -> bool:
    """protobuf-java's generated `equals` over two messages of the same type."""
    if left.desc.name != right.desc.name:
        return False
    return all(_equal_field(field, left, right) for field in left.desc.fields) and _equal_unknown(
        left, right
    )


def _equal_field(field: FieldDesc, left: Msg, right: Msg) -> bool:
    if field.label == "repeated":
        mine, theirs = left.get(field.name), right.get(field.name)
        return len(mine) == len(theirs) and all(
            _equal_value(field, one, other) for one, other in zip(mine, theirs, strict=True)
        )
    if left.has(field.name) != right.has(field.name):
        return False
    if not left.has(field.name):
        return True
    return _equal_value(field, left.get(field.name), right.get(field.name))


def _equal_value(field: FieldDesc, left: object, right: object) -> bool:
    if field.kind == "message":
        return equal_messages(left, right)
    if field.kind in _PACK:
        return _bits(field.kind, left) == _bits(field.kind, right)
    return left == right


def _bits(kind: str, value: float) -> bytes:
    """`floatToIntBits`, which is why `-0.0` and `0.0` differ and NaNs do not."""
    if math.isnan(value):
        return _CANONICAL_NAN[kind]
    return struct.pack(_PACK[kind], value)


def _equal_unknown(left: Msg, right: Msg) -> bool:
    return _unknown_set(left) == _unknown_set(right)


def _unknown_set(msg: Msg) -> dict[tuple[int, int], list[object]]:
    """`UnknownFieldSet`: number and wire type to the values seen, in order."""
    grouped: dict[tuple[int, int], list[object]] = {}
    for number, wire_type, raw in msg.unknown:
        grouped.setdefault((number, wire_type), []).append(_payload(wire_type, raw))
    return grouped


def _payload(wire_type: int, raw: bytes) -> object:
    """The value `UnknownFieldSet` would have stored, rather than its encoding."""
    if wire_type == wire.WIRE_VARINT:
        return wire.Reader(raw).read_varint()
    if wire_type == wire.WIRE_LENGTH:
        return wire.Reader(raw).read_length_delimited()
    return raw
