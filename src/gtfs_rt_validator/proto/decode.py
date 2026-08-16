"""Turn wire bytes into a message graph, under whichever schema you hand it.

The schema argument is the whole of compat mode. Given `schema_2015` this
reproduces what the jar sees, including treating post-2015 enum values as
unknown fields; given `schema_current` it sees today's spec. Masking after the
fact cannot do this: by then a later occurrence of a singular field has already
overwritten the earlier one, and a required field inside a message the 2015
schema never had has already been enforced.
"""

from __future__ import annotations

from gtfs_rt_validator.proto import wire
from gtfs_rt_validator.proto.descriptor import (
    KIND_WIRE_TYPES,
    FieldDesc,
    MessageDesc,
    Schema,
    wire_type_matches,
)
from gtfs_rt_validator.proto.errors import DecodeError

_CONVERTERS = {
    "int32": wire.as_int32,
    "int64": wire.as_int64,
    "uint32": lambda v: v & 0xFFFFFFFF,
    "uint64": lambda v: v,
    "sint32": wire.as_sint32,
    "sint64": wire.as_sint64,
    "bool": wire.as_bool,
    "enum": wire.as_int32,
    "fixed32": lambda v: v & 0xFFFFFFFF,
    "fixed64": lambda v: v,
    "sfixed32": wire.as_int32,
    "sfixed64": wire.as_int64,
    "float": wire.as_float,
    "double": wire.as_double,
}


class Msg:
    """One decoded message. Presence is explicit because rules read `hasX()`."""

    __slots__ = ("_schema", "_values", "desc", "unknown")

    def __init__(self, desc: MessageDesc, schema: Schema) -> None:
        self.desc = desc
        self._schema = schema
        self._values: dict[str, object] = {}
        self.unknown: list[tuple[int, int, bytes]] = []

    def has(self, name: str) -> bool:
        """Whether the field was on the wire.

        For a singular field this is protobuf's `hasX()`, which is what the
        roughly twenty rules that branch on presence actually need.

        For a repeated field it answers "at least one occurrence was seen",
        which has no Java counterpart: generated code offers `getXCount()` and
        no `hasX()` at all. Prefer `len(msg.get(name))` there, so the intent
        reads the same as the Java it was ported from.
        """
        return name in self._values

    def get(self, name: str) -> object:
        """The value, or what protobuf-java would return for an absent field.

        The spec's rule is "a getter on an absent field returns the proto
        default while `hasX()` stays false", and for a message field that
        default is the submessage's *default instance*, not nothing. Measured
        against the pinned jars: an entity with no `trip_update` answers
        `hasTripUpdate() == false`, `getTripUpdate() != null`, and
        `getTripUpdate().getTrip().getTripId() == ""`. So a rule ported from
        Java can chain through an absent submessage without a guard and read
        defaults out the far end, exactly as the Java it came from does.

        Returning `None` here instead would turn every unguarded chain in the
        57 ported rules into an `AttributeError`.

        A fresh empty message is built per call rather than shared, so a caller
        cannot mutate a cached default and poison every later read. The cost is
        one small allocation on a path only reached when the field is absent.
        """
        if name in self._values:
            return self._values[name]
        desc = self.desc.by_name[name]
        if desc.label == "repeated":
            return []
        if desc.kind == "message" and desc.type_name is not None:
            return Msg(self._schema.message(desc.type_name), self._schema)
        return desc.default

    def __repr__(self) -> str:
        return f"<{self.desc.name} {self._values!r}>"


def decode(data: bytes, schema: Schema, message: str = "FeedMessage") -> Msg:
    reader = wire.Reader(data)
    msg = _read(reader, schema, schema.message(message), len(data))
    _require(msg, schema)
    return msg


def _read(reader: wire.Reader, schema: Schema, desc: MessageDesc, end: int) -> Msg:
    msg = Msg(desc, schema)
    while reader.pos < end:
        number, wire_type = reader.read_tag()
        field = desc.by_number.get(number)
        if field is None or not wire_type_matches(field, wire_type):
            # The field number goes with it so a group can be checked for the
            # matching end-group tag, which is what protobuf-java does.
            msg.unknown.append((number, wire_type, reader.skip(wire_type, number)))
            continue
        _set(msg, reader, schema, field)
    return msg


def _set(msg: Msg, reader: wire.Reader, schema: Schema, field: FieldDesc) -> None:
    if field.kind == "message":
        payload = reader.read_length_delimited()
        sub = _read(wire.Reader(payload), schema, schema.message(field.type_name), len(payload))
        if field.label == "repeated":
            msg._values.setdefault(field.name, []).append(sub)
        elif field.name in msg._values:
            # The one field kind protobuf merges rather than replaces.
            _merge(msg._values[field.name], sub)
        else:
            msg._values[field.name] = sub
        return

    if field.kind in ("string", "bytes"):
        raw = reader.read_length_delimited()
        # "replace" rather than "strict": proto2 generated code holds a string
        # as a `ByteString` and converts on the getter with `toStringUtf8()`,
        # which substitutes U+FFFD instead of throwing. Measured against a jar
        # built from the pinned SHA: a `trip_id` of b"\xff\xfeT1" validates and
        # its occurrence text carries the two replacement characters. Pinned by
        # tests/test_decode.py, which records the run.
        value = raw.decode("utf-8", "replace") if field.kind == "string" else raw
    else:
        wire_type = KIND_WIRE_TYPES[field.kind]
        if wire_type == 0:
            raw_value = reader.read_varint()
        elif wire_type == 1:
            raw_value = reader.read_fixed64()
        else:
            raw_value = reader.read_fixed32()
        if field.kind == "enum":
            value = wire.as_int32(raw_value)
            if value not in schema.enum_values(field.type_name):
                # Closed enum: retain the bytes and leave the field as it was,
                # so an earlier recognised value is not lost.
                msg.unknown.append((field.number, 0, _varint_bytes(raw_value)))
                return
        else:
            value = _CONVERTERS[field.kind](raw_value)

    if field.label == "repeated":
        msg._values.setdefault(field.name, []).append(value)
    else:
        msg._values[field.name] = value


def _merge(into: Msg, other: Msg) -> None:
    for name, value in other._values.items():
        if isinstance(value, Msg) and isinstance(into._values.get(name), Msg):
            _merge(into._values[name], value)
        elif isinstance(value, list):
            into._values.setdefault(name, []).extend(value)
        else:
            into._values[name] = value
    into.unknown.extend(other.unknown)


def _varint_bytes(value: int) -> bytes:
    out = bytearray()
    while True:
        byte = value & 0x7F
        value >>= 7
        if value:
            out.append(byte | 0x80)
        else:
            out.append(byte)
            return bytes(out)


def _require(msg: Msg, schema: Schema) -> None:
    """`isInitialized`, recursively. A missing required field anywhere sinks the
    whole parse, which is what makes upstream skip the file."""
    for field in msg.desc.fields:
        if field.label == "required" and field.name not in msg._values:
            raise DecodeError(f"required field {msg.desc.name}.{field.name} is not set")
        value = msg._values.get(field.name)
        if isinstance(value, Msg):
            _require(value, schema)
        elif isinstance(value, list):
            for item in value:
                if isinstance(item, Msg):
                    _require(item, schema)
