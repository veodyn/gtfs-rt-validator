"""Write wire bytes from a plain dict, for building fixtures.

Not a general encoder and not on the validation path. Fields are written in
ascending field-number order, which protobuf does not require but which makes a
fixture's bytes stable and therefore diffable when a test fails.
"""

from __future__ import annotations

import struct

from gtfs_rt_validator.proto.descriptor import KIND_WIRE_TYPES, FieldDesc, Schema


def encode(value: dict, schema: Schema, message: str = "FeedMessage") -> bytes:
    desc = schema.message(message)
    out = bytearray()
    for field in sorted(desc.fields, key=lambda f: f.number):
        if field.name not in value:
            continue
        given = value[field.name]
        items = given if field.label == "repeated" else [given]
        for item in items:
            out += _one(field, item, schema)
    return bytes(out)


def _one(field: FieldDesc, item: object, schema: Schema) -> bytes:
    tag = _varint((field.number << 3) | KIND_WIRE_TYPES[field.kind])
    if field.kind == "message":
        # A nested message arrives as a nested dict and goes back through the
        # public entry point, so arbitrary depth costs nothing extra here.
        payload = encode(item, schema, field.type_name)
        return tag + _varint(len(payload)) + payload
    if field.kind == "string":
        payload = item.encode("utf-8")
        return tag + _varint(len(payload)) + payload
    if field.kind == "bytes":
        return tag + _varint(len(item)) + item
    if field.kind == "float":
        return tag + struct.pack("<f", item)
    if field.kind == "double":
        return tag + struct.pack("<d", item)
    if field.kind in ("fixed32", "sfixed32"):
        return tag + struct.pack("<I", item & 0xFFFFFFFF)
    if field.kind in ("fixed64", "sfixed64"):
        return tag + struct.pack("<Q", item & 0xFFFFFFFFFFFFFFFF)
    if field.kind == "bool":
        return tag + _varint(1 if item else 0)
    if field.kind in ("sint32", "sint64"):
        # Zigzag. Python's `>>` sign-extends without bound, so `item >> 63` is
        # -1 (all ones) for every negative int and 0 for every non-negative one:
        # the 64-bit spelling therefore gives the right answer at 32 bits too,
        # zigzag(-1) == 1 either way. Unexercised outside tests, because
        # GTFS-Realtime declares no sint field at either pin - `grep sint`
        # over the pinned .proto and over schema_current.py finds nothing.
        return tag + _varint((item << 1) ^ (item >> 63))
    # int32/int64/uint32/uint64/enum: negatives are sign-extended to 64 bits,
    # which is why -1 costs ten bytes on the wire.
    return tag + _varint(item & 0xFFFFFFFFFFFFFFFF if item < 0 else item)


def _varint(value: int) -> bytes:
    out = bytearray()
    while True:
        byte = value & 0x7F
        value >>= 7
        if value:
            out.append(byte | 0x80)
        else:
            out.append(byte)
            return bytes(out)
