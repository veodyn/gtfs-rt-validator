"""A validated message with no findings still gets a file, and it holds `[ ]`.

The one claim in `report/compat.py` that no committed golden covers. Every feed
in `tests/fixtures/jar/` was crafted to make some rule fire, so the empty case is
reachable only by building a feed that fires nothing, which is what this does.

It was derived from the Java first: `writeResults` at `BatchProcessor.java:284`
is unconditional and serialises `allErrorLists`, which stays empty because each
validator adds its group only for a non-empty occurrence list. Deriving is not
measuring, and this project's rule is that a number or a byte string in a
document has to come from running the thing. So the same feed goes through a real
jar here and the three bytes are read back off disk.

The jar-backed test skips when no jar is built, like every other oracle-backed
test. That is a real hole rather than a hidden one: `tests/test_compat_writer.py`
still pins our own writer's `[ ]` unconditionally, so a regression in this project
fails with or without a jar, and only the claim *about upstream* goes unchecked.
The fixture guard below needs no jar and never skips.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

TOOLS = Path(__file__).resolve().parent.parent / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

import jarenv  # noqa: E402
import run_jar  # noqa: E402
from goldenfeeds import FEED_TS, SCHEMA, encode  # noqa: E402

from gtfs_rt_validator.proto.decode import decode  # noqa: E402
from gtfs_rt_validator.report.compat import RESULTS_SUFFIX  # noqa: E402

#: Everything a feed needs to be valid and nothing that makes a rule fire: a
#: recognised version so E038 and E049 stay quiet, `FULL_DATASET` so E039 does,
#: a timestamp inside the POSIX window at the file's own pinned mtime so E001,
#: W001, W008 and E050 do, and no entities at all so no entity rule can reach.
CLEAN_FEED = {"header": {"gtfs_realtime_version": "2.0", "incrementality": 0, "timestamp": FEED_TS}}

#: Jackson's `FixedSpaceIndenter` on an empty array, and no trailing newline.
EMPTY_RESULTS = b"[ ]"


@pytest.mark.skipif(not jarenv.jar_present(), reason="no jar built; run tools/build_jar.py")
def test_the_jar_writes_an_empty_list_for_a_feed_that_fires_nothing(tmp_path: Path) -> None:
    blob = encode(CLEAN_FEED, SCHEMA)
    feed = tmp_path / "clean.pb"
    feed.write_bytes(blob)
    # The jar reads mtime as both the sort key and the validation clock, so
    # pinning it to the header timestamp is what keeps W008 and E050 quiet.
    os.utime(feed, (FEED_TS, FEED_TS))

    try:
        run_jar.invoke(tmp_path, jarenv.GOLDEN_GTFS)
    except (subprocess.SubprocessError, RuntimeError) as failure:  # pragma: no cover
        pytest.fail(f"the jar did not complete on a 15-byte clean feed: {failure}")

    results = tmp_path / f"clean.pb{RESULTS_SUFFIX}"
    assert results.exists(), (
        "the jar wrote no results file for a feed it validated; writeResults is "
        "unconditional, so an absence here would mean the message was skipped"
    )
    assert results.read_bytes() == EMPTY_RESULTS


def test_the_clean_feed_really_is_clean() -> None:
    """Guard the guard: a feed that fired something would make the test above vacuous.

    If a change to `CLEAN_FEED` made some rule fire, the first test would go red
    on content, but the failure would read as "Jackson changed" rather than "the
    fixture stopped being clean". This says which one it is.

    **An earlier version of this asserted only `len(blob) == 15`, which a codex
    audit showed proves nothing.** Changing `gtfs_realtime_version` from "2.0" to
    an invalid "9.0" keeps the encoded length at exactly 15 and fires E038, so the
    guard passed on a feed that was no longer clean. Length is not the property;
    the field values are, so those are what this reads back.

    Needs no jar, so the `skipif` is gone too: the assertion never used one, and a
    guard that vanishes on the machines least likely to have a jar is the wrong
    shape for a guard.
    """
    header = decode(encode(CLEAN_FEED, SCHEMA), SCHEMA).get("header")
    # E038 and E049 both read the version; only "1.0" and "2.0" are recognised.
    assert header.get("gtfs_realtime_version") == "2.0"
    # E039 fires on DIFFERENTIAL, which is 1.
    assert header.get("incrementality") == 0
    # E001, W001, W008 and E050 all read this; at the file's own pinned mtime and
    # inside the POSIX window, none of them has anything to say.
    assert header.get("timestamp") == FEED_TS
    # Every entity rule needs an entity. With none, none can reach.
    assert not decode(encode(CLEAN_FEED, SCHEMA), SCHEMA).get("entity")
