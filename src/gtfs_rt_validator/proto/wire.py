"""Reading protobuf's wire format.

Deliberately knows nothing about GTFS-Realtime: it reads tags, varints, fixed
widths and length-delimited blocks, and `decode` supplies the meaning. The
malformed cases raise `DecodeError` because that is where upstream's file skip
comes from, and getting them wrong would make us validate a file the jar
discards.
"""

from __future__ import annotations

import struct

from gtfs_rt_validator.proto.errors import DecodeError

WIRE_VARINT = 0
WIRE_FIXED64 = 1
WIRE_LENGTH = 2
WIRE_START_GROUP = 3
WIRE_END_GROUP = 4
WIRE_FIXED32 = 5

_MAX_VARINT_BYTES = 10
_UINT64_MASK = (1 << 64) - 1


class Reader:
    """A cursor over a bytes buffer. Not reusable and not thread-safe."""

    __slots__ = ("_data", "pos")

    def __init__(self, data: bytes) -> None:
        self._data = data
        self.pos = 0

    def at_end(self) -> bool:
        return self.pos >= len(self._data)

    def read_varint(self) -> int:
        """An unsigned 64-bit varint. Interpretation is the field kind's job."""
        start = self.pos
        result = 0
        shift = 0
        for _ in range(_MAX_VARINT_BYTES):
            if self.pos >= len(self._data):
                raise DecodeError("varint runs past the end of the buffer", start)
            byte = self._data[self.pos]
            self.pos += 1
            result |= (byte & 0x7F) << shift
            if not byte & 0x80:
                return result & _UINT64_MASK
            shift += 7
        raise DecodeError("varint is longer than 10 bytes", start)

    def read_varint32(self) -> int:
        """protobuf-java's `readRawVarint32`, including its truncation.

        Not the same function as `read_varint` with a mask on the end, and the
        difference is observable. Java reads at most five bytes into a 32-bit
        `int`; the fifth contributes its *whole* signed byte shifted left 28, so
        the bits above 32 fall off the end of the register rather than being
        rejected. If that fifth byte still carries a continuation bit, up to
        five further bytes are read and discarded, for a ten-byte ceiling.

        Measured against the pinned jars rather than reasoned: a `FeedMessage`
        whose header tag is written as the varint `2**32 + 10` is accepted by
        `FeedMessage.parseFrom` and read as tag 10, and an entity whose `id`
        length is written as `2**32` is accepted and read as the empty string.
        Reading either as a 64-bit varint makes us reject a file the jar
        validates, which is a parity failure in the direction that matters.

        Returns the value Java would hold in an `int`, sign included, so a
        caller that needs a length can test it for negativity the way
        `readRawBytes` does.
        """
        start = self.pos
        byte = self._next_byte(start)
        if byte < 0x80:
            return byte
        result = byte & 0x7F
        for shift in (7, 14, 21):
            byte = self._next_byte(start)
            if byte < 0x80:
                return result | (byte << shift)
            result |= (byte & 0x7F) << shift
        # The fifth byte is not masked to seven bits in Java, so its top bit
        # lands on bit 35 and is discarded by the 32-bit register.
        byte = self._next_byte(start)
        signed = byte - 0x100 if byte & 0x80 else byte
        result = (result | (signed << 28)) & 0xFFFFFFFF
        if byte & 0x80:
            for _ in range(5):
                if self._next_byte(start) < 0x80:
                    return as_int32(result)
            raise DecodeError("varint is longer than 10 bytes", start)
        return as_int32(result)

    def _next_byte(self, start: int) -> int:
        if self.pos >= len(self._data):
            raise DecodeError("varint runs past the end of the buffer", start)
        byte = self._data[self.pos]
        self.pos += 1
        return byte

    def read_tag(self) -> tuple[int, int]:
        """A tag, read the way protobuf-java reads one: as a 32-bit varint.

        The field number comes off an *unsigned* shift, matching Java's
        `tag >>> 3`, so a tag whose truncated value has the sign bit set still
        yields a positive field number rather than a negative one.
        """
        start = self.pos
        tag = self.read_varint32() & 0xFFFFFFFF
        number = tag >> 3
        if number == 0:
            raise DecodeError("field number 0 is not a valid tag", start)
        return number, tag & 0x07

    def read_fixed32(self) -> int:
        return self._take(4, "fixed32")

    def read_fixed64(self) -> int:
        return self._take(8, "fixed64")

    def _take(self, width: int, what: str) -> int:
        if self.pos + width > len(self._data):
            raise DecodeError(f"{what} runs past the end of the buffer", self.pos)
        chunk = self._data[self.pos : self.pos + width]
        self.pos += width
        return int.from_bytes(chunk, "little")

    def read_length_delimited(self) -> bytes:
        """A length-prefixed block, with the length read as Java reads it.

        `readRawBytes` takes an `int`, so the length truncates to 32 bits and a
        result with the sign bit set is a negative size, which protobuf-java
        rejects outright rather than treating as huge.
        """
        start = self.pos
        length = self.read_varint32()
        if length < 0:
            raise DecodeError("length-delimited field declares a negative length", start)
        if self.pos + length > len(self._data):
            raise DecodeError("length-delimited field runs past the end", start)
        chunk = self._data[self.pos : self.pos + length]
        self.pos += length
        return chunk

    def skip(self, wire_type: int, field_number: int | None = None) -> bytes:
        """Step over one field's payload and return the bytes stepped over.

        The bytes are returned rather than discarded because an unrecognised
        enum value has to be retained as an unknown field, exactly as
        protobuf-java retains it, and a caller that only knew the length could
        not reproduce that.

        `field_number` matters only for a group: protobuf-java requires a group
        to close on the field number that opened it. It is optional so that the
        many callers skipping a scalar need not supply one.
        """
        start = self.pos
        if wire_type == WIRE_VARINT:
            self.read_varint()
        elif wire_type == WIRE_FIXED64:
            self._take(8, "fixed64")
        elif wire_type == WIRE_LENGTH:
            self.read_length_delimited()
        elif wire_type == WIRE_FIXED32:
            self._take(4, "fixed32")
        elif wire_type == WIRE_START_GROUP:
            self._skip_group(field_number)
        elif wire_type == WIRE_END_GROUP:
            raise DecodeError("end-group tag with no matching start", start)
        else:
            raise DecodeError(f"unsupported wire type {wire_type}", start)
        return self._data[start : self.pos]

    def _skip_group(self, field_number: int | None) -> None:
        """Step over a group, checking that it closes on its own field number.

        Groups are removed from proto3 and unused by GTFS-Realtime, but a third
        party can still put one in an extension range, and protobuf-java skips
        it rather than failing. It does not skip it blindly, though: it carries
        the opening field number down and requires the matching end-group tag,
        raising "end-group tag did not match expected tag" otherwise. Counting
        depth alone accepts a group opened on field 10 and closed on field 11,
        which the jar rejects.

        Measured against the pinned jars: the bytes `0a050a03322e30 53 5c`
        (a valid header, then start-group 10 closed by end-group 11) are
        rejected by `FeedMessage.parseFrom`, while `... 53 54` (closed on 10)
        parses. A caller that reaches here without a field number, which cannot
        happen through `skip`, gets the permissive depth-only behaviour.
        """
        while True:
            if self.at_end():
                raise DecodeError("group runs past the end of the buffer", self.pos)
            at = self.pos
            number, wire_type = self.read_tag()
            if wire_type == WIRE_END_GROUP:
                if field_number is not None and number != field_number:
                    raise DecodeError(
                        f"end-group tag for field {number} does not close the group "
                        f"opened by field {field_number}",
                        at,
                    )
                return
            self.skip(wire_type, number)


def as_int32(value: int) -> int:
    value &= 0xFFFFFFFF
    return value - (1 << 32) if value & 0x80000000 else value


def as_int64(value: int) -> int:
    value &= _UINT64_MASK
    return value - (1 << 64) if value & (1 << 63) else value


def as_sint32(value: int) -> int:
    value &= 0xFFFFFFFF
    return (value >> 1) ^ -(value & 1)


def as_sint64(value: int) -> int:
    value &= _UINT64_MASK
    return (value >> 1) ^ -(value & 1)


def as_bool(value: int) -> bool:
    return value != 0


def as_float(value: int) -> float:
    return struct.unpack("<f", value.to_bytes(4, "little"))[0]


def as_double(value: int) -> float:
    return struct.unpack("<d", value.to_bytes(8, "little"))[0]
