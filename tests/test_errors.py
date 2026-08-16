"""DecodeError is the only exception a malformed feed produces.

Upstream catches `InvalidProtocolBufferException` around `parseFrom` and skips
the file, writing no `.results.json` for it. One exception type here keeps that
mapping to one `except` clause rather than a growing tuple.
"""

from gtfs_rt_validator.proto.errors import DecodeError


def test_it_carries_the_reason_and_the_offset():
    err = DecodeError("varint is longer than 10 bytes", at=17)
    assert err.reason == "varint is longer than 10 bytes"
    assert err.at == 17
    assert "at byte 17" in str(err)


def test_the_offset_is_optional_because_some_failures_have_no_position():
    """A missing required field is a property of the whole message."""
    err = DecodeError("required field FeedEntity.id is not set")
    assert err.at is None
    assert "at byte" not in str(err)
