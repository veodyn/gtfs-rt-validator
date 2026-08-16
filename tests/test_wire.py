"""The wire format, byte by byte.

Every expectation here is protobuf's documented encoding, and the malformed
cases are the ones that decide whether upstream skips a file: `parseFrom` raises
`InvalidProtocolBufferException` for each of them.
"""

import pytest

from gtfs_rt_validator.proto.errors import DecodeError
from gtfs_rt_validator.proto.wire import (
    Reader,
    as_double,
    as_float,
    as_int32,
    as_sint32,
)


def test_single_byte_varint():
    assert Reader(b"\x01").read_varint() == 1


def test_multi_byte_varint_is_little_endian_base_128():
    # 300 = 0b100101100 -> groups of 7 from the bottom: 0101100, 10
    assert Reader(b"\xac\x02").read_varint() == 300


def test_maximum_varint_is_ten_bytes():
    assert Reader(b"\xff" * 9 + b"\x01").read_varint() == 2**64 - 1


def test_an_eleven_byte_varint_is_malformed():
    """protobuf caps a varint at 10 bytes; a longer one cannot fit uint64."""
    with pytest.raises(DecodeError):
        Reader(b"\x80" * 11).read_varint()


def test_a_truncated_varint_is_malformed():
    """Every byte has its continuation bit set and then the buffer ends."""
    with pytest.raises(DecodeError):
        Reader(b"\x80\x80").read_varint()


def test_tag_splits_into_field_number_and_wire_type():
    # field 1, wire type 2 -> (1 << 3) | 2 == 0x0a
    assert Reader(b"\x0a").read_tag() == (1, 2)


def test_field_number_zero_is_malformed():
    """Field numbers start at 1, so a zero tag cannot be produced by an encoder."""
    with pytest.raises(DecodeError):
        Reader(b"\x00").read_tag()


def test_length_delimited_returns_exactly_the_declared_bytes():
    reader = Reader(b"\x03abcdef")
    assert reader.read_length_delimited() == b"abc"
    assert reader.pos == 4


def test_a_length_running_past_the_buffer_is_malformed():
    with pytest.raises(DecodeError):
        Reader(b"\x09abc").read_length_delimited()


def test_negative_int32_is_sign_extended_to_ten_bytes():
    """protobuf encodes a negative int32 as its 64-bit two's complement, so -1
    is ten 0xff-ish bytes rather than a short varint. `occupancy_percentage`
    carries `[default = -1]`, so this is reachable on a real feed."""
    raw = Reader(b"\xff\xff\xff\xff\xff\xff\xff\xff\xff\x01").read_varint()
    assert as_int32(raw) == -1


def test_zigzag_maps_small_negatives_to_small_varints():
    assert as_sint32(0) == 0
    assert as_sint32(1) == -1
    assert as_sint32(2) == 1
    assert as_sint32(3) == -2


def test_float_and_double_come_off_the_fixed_widths():
    reader = Reader(b"\x00\x00\x80\x3f")
    assert as_float(reader.read_fixed32()) == 1.0
    reader = Reader(b"\x00\x00\x00\x00\x00\x00\xf0\x3f")
    assert as_double(reader.read_fixed64()) == 1.0


def test_skip_returns_the_raw_bytes_so_unknown_fields_can_be_retained():
    """An unrecognised enum value has to survive as an unknown field, which
    means keeping the bytes rather than only stepping over them."""
    reader = Reader(b"\x96\x01rest")
    assert reader.skip(0) == b"\x96\x01"
    assert reader.pos == 2


def test_skip_handles_a_length_delimited_field():
    reader = Reader(b"\x03abcrest")
    assert reader.skip(2) == b"\x03abc"


def test_an_unsupported_wire_type_is_malformed():
    """6 and 7 have never been assigned."""
    with pytest.raises(DecodeError):
        Reader(b"\x00").skip(6)


# ---------------------------------------------------------------------------
# Everything below was added after a code audit measured three divergences from
# protobuf-java 2.6.1. Each expectation was taken by running the same bytes
# through `GtfsRealtime.FeedMessage.parseFrom` from the pinned jars
# (gtfs-realtime-bindings 0.0.4 plus protobuf-java 2.6.1) under JDK 17, not from
# reading the source. The measured result is quoted in each test.
# ---------------------------------------------------------------------------


def test_a_tag_truncates_to_thirty_two_bits_the_way_java_does():
    """A tag written as the varint 2**32 + 10 is tag 10 to protobuf-java.

    `readRawVarint32` folds the fifth byte in with `<< 28` and lets the bits
    above 32 fall off the register, so the value is truncated rather than
    rejected. Measured: a FeedMessage whose header tag is written this way is
    ACCEPTed by the jar, and reads back with version "2.0".

    Reading it as a 64-bit varint would make us skip a file the jar validates.
    """
    reader = Reader(b"\x8a\x80\x80\x80\x10")
    assert reader.read_tag() == (1, 2)


def test_a_length_truncates_to_thirty_two_bits_the_way_java_does():
    """A length written as the varint 2**32 is zero to protobuf-java.

    Measured: an entity whose `id` length is written this way is ACCEPTed by
    the jar and `hasId()` is true with the value the empty string, where a
    64-bit read would call it a buffer overrun.
    """
    reader = Reader(b"\x80\x80\x80\x80\x10rest")
    assert reader.read_length_delimited() == b""
    assert reader.pos == 5


def test_a_length_whose_truncated_value_is_negative_is_malformed():
    """`readRawBytes` takes an int, and a negative size is rejected outright
    rather than read as an enormous one."""
    with pytest.raises(DecodeError, match="negative length"):
        Reader(b"\xff\xff\xff\xff\x0f").read_length_delimited()


def test_read_varint32_keeps_only_the_low_thirty_two_bits():
    assert Reader(b"\x8a\x80\x80\x80\x10").read_varint32() == 10
    assert Reader(b"\x01").read_varint32() == 1
    assert Reader(b"\xac\x02").read_varint32() == 300


def test_read_varint32_discards_up_to_five_trailing_bytes():
    """Java reads five more bytes past the fifth and throws them away, so a
    ten-byte encoding of a small number still reads as that number."""
    reader = Reader(b"\xff\xff\xff\xff\xff\xff\xff\xff\xff\x01")
    assert reader.read_varint32() == -1
    assert reader.pos == 10


def test_read_varint32_rejects_an_eleventh_byte():
    with pytest.raises(DecodeError, match="longer than 10 bytes"):
        Reader(b"\x80" * 11).read_varint32()


def test_a_group_must_close_on_the_field_number_that_opened_it():
    """Counting depth alone is not enough, and the jar proves it.

    Measured: the bytes `0a050a03322e30 53 5c`, a valid header followed by
    start-group field 10 closed by end-group field 11, are REJECTed by
    `parseFrom` with "Protocol message end-group tag did not match expected
    tag", while the same bytes ending `53 54` (closed on field 10) parse.
    """
    with pytest.raises(DecodeError, match="does not close the group"):
        Reader(b"\x5c").skip(3, 10)


def test_a_group_closing_on_its_own_field_number_is_skipped():
    reader = Reader(b"\x54rest")
    assert reader.skip(3, 10) == b"\x54"
    assert reader.pos == 1


def test_a_nested_group_closes_the_inner_one_first():
    """Measured against the jar: `... 53 5b 5c 54`, group 10 containing group
    11 which closes, then group 10 closing, is ACCEPTed."""
    reader = Reader(b"\x5b\x5c\x54")
    assert reader.skip(3, 10) == b"\x5b\x5c\x54"


def test_an_unterminated_group_is_malformed():
    with pytest.raises(DecodeError, match="group runs past the end"):
        Reader(b"\x08\x01").skip(3, 10)
