"""Upstream's equal-message abort, opt-in, and the three ways it is reachable.

`TimestampValidator.java:66-68` throws `IllegalArgumentException` when the
current and previous `FeedMessage` are equal. `BatchProcessor.java:263` does not
catch it and `Main.java:62` does not either, so the exception leaves `main` and
the whole run dies: no `.results.json` for the file that triggered it and none
for any file after it.

It is reachable, because the two guards compare different things. The MD5 skip
at `BatchProcessor.java:214-218` compares **bytes**; `feedMessage.equals` compares
**decoded fields**. Two files whose wire field order differs and whose decoded
content does not pass the first and hit the second. `EQUAL_A` and `EQUAL_B` below
are exactly that pair: same header version, same header timestamp, same single
entity, different MD5.

**Measured, not reasoned.** Every claim in this module was run against the pinned
jar on this machine (JDK 17, `jar-build/.../withAllDependencies.jar`). Staged as
`1.pb` = `EQUAL_A`, `2.pb` = `EQUAL_B`, `3.pb` = a plainly different feed, the jar
exits 1, writes `1.pb.results.json`, and writes nothing for `2.pb` or `3.pb`:

    Exception in thread "main" java.lang.IllegalArgumentException:
        feedMessage and previousFeedMessage must not be the same
        at ...TimestampValidator.validate(TimestampValidator.java:67)
        at ...BatchProcessor.processFeeds(BatchProcessor.java:263)
        at ...Main.main(Main.java:62)

Staged as `1.pb` = `EQUAL_A`, `2.pb` = `EQUAL_A`, `3.pb` = the different feed, the
MD5 skip fires first: the jar exits 0 and writes results for `1.pb` and `3.pb`
only. `test_the_jar_and_this_project_abort_on_the_same_file` re-runs the first
staging against a live jar when one is built and skips cleanly when it is not;
the surviving `1.pb.results.json` is byte-identical on both sides, 606 bytes.

The abort costs a complete report, so it is off unless asked for. See
`cliargs.EQUAL_MESSAGE_ABORT_FLAG` for why it is a flag at all.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
from pathlib import Path

import pytest

from clifixtures import run_cli
from gtfs_rt_validator import api, cli
from gtfs_rt_validator.cliargs import EQUAL_MESSAGE_ABORT_FLAG
from gtfs_rt_validator.proto.decode import decode
from gtfs_rt_validator.proto.schema_2015 import SCHEMA as V2015
from gtfs_rt_validator.runner import Mode, SortBy
from gtfs_rt_validator.runner.equal_message import equal_messages
from jarcorpus import import_tool
from runnerfixtures import feed, static_feed

jarenv = import_tool("jarenv")
run_jar = import_tool("run_jar")

#: Two encodings of one message: `gtfs_realtime_version` "1.0", header timestamp
#: 1104537600, one entity with id "X". They differ only in the order the two
#: header fields were written, which protobuf permits and MD5 does not forgive.
EQUAL_A = bytes.fromhex("0a0b0a03312e301880d0d78e0412030a0158")
EQUAL_B = bytes.fromhex("0a0b1880d0d78e040a03312e3012030a0158")

#: The third input, staged after the pair and different from both, whose results
#: file is the evidence for "and no file after it either".
THIRD = feed("z")

#: The first mtime stamped on a staged archive, and therefore the run's clock.
#: `run_jar.MTIME_BASE`, restated so this module does not need `tools/` on the
#: path to build an archive the jar never sees.
MTIME_BASE = 1_700_000_000

RESULTS = api.RESULTS_SUFFIX


def _unavailable() -> str:
    """Why the jar cannot be run here, or the empty string if it can."""
    if not jarenv.jar_present():
        return f"no jar at {jarenv.JAR}; run .venv/bin/python tools/build_jar.py"
    try:
        jarenv.java_home_17()
    except jarenv.NoJdk17Error as exc:
        return str(exc)
    return ""


REASON = _unavailable()
needs_jar = pytest.mark.skipif(bool(REASON), reason=REASON or "a jar is present")


def staged(tmp_path: Path, second: bytes) -> Path:
    """An archive of three inputs, mtimes stamped so replay order is fixed.

    `1.pb` is the pair's first encoding, `2.pb` is whatever the caller wants
    compared against it, and `3.pb` is a plainly different feed that exists only
    to prove whether the run reached it.
    """
    archive = tmp_path / "archive"
    archive.mkdir()
    (archive / "1.pb").write_bytes(EQUAL_A)
    (archive / "2.pb").write_bytes(second)
    (archive / "3.pb").write_bytes(THIRD)
    for index, name in enumerate(("1.pb", "2.pb", "3.pb")):
        stamp = MTIME_BASE + index
        os.utime(archive / name, (stamp, stamp))
    return archive


def compat(tmp_path: Path, archive: Path, *extra: str) -> list[str]:
    return [
        "--compat",
        "-gtfs",
        str(static_feed(tmp_path)),
        "-gtfsRealtimePath",
        str(archive),
        *extra,
    ]


def written(archive: Path) -> list[str]:
    return sorted(path.name for path in archive.glob(f"*{RESULTS}"))


def reported(archive: Path, name: str) -> set[str]:
    blob = (archive / (name + RESULTS)).read_bytes()
    return {row["errorMessage"]["validationRule"]["errorId"] for row in json.loads(blob)}


def test_the_pair_differs_in_bytes_and_agrees_once_decoded() -> None:
    """The premise the rest of the module rests on, asserted rather than assumed.

    If MD5 ever agreed here the abort would be unreachable and every test below
    would pass vacuously.
    """
    assert hashlib.md5(EQUAL_A).digest() != hashlib.md5(EQUAL_B).digest()  # noqa: S324
    assert EQUAL_A != EQUAL_B
    assert equal_messages(decode(EQUAL_A, V2015), decode(EQUAL_B, V2015))


def test_by_default_the_run_continues_and_e017_fires(tmp_path, capsys) -> None:
    """Off by default, so an equal pair is data: E017 is the finding it makes."""
    archive = staged(tmp_path, EQUAL_B)

    code, _, err = run_cli(compat(tmp_path, archive), capsys)

    assert code == cli.EXIT_OK
    assert err == ""
    assert written(archive) == ["1.pb.results.json", "2.pb.results.json", "3.pb.results.json"]
    assert "E017" in reported(archive, "2.pb")


def test_the_flag_aborts_the_run_and_no_later_file_is_written(tmp_path, capsys) -> None:
    """The whole point: `3.pb` is staged *after* the pair and still gets nothing.

    A guard that only skipped the offending file would leave
    `3.pb.results.json` behind, and the jar leaves no such file.
    """
    archive = staged(tmp_path, EQUAL_B)

    code, out, err = run_cli(compat(tmp_path, archive, EQUAL_MESSAGE_ABORT_FLAG), capsys)

    assert code == cli.EXIT_UPSTREAM_CRASH
    assert written(archive) == ["1.pb.results.json"]
    assert "feedMessage and previousFeedMessage must not be the same" in err
    assert out == ""


def test_a_byte_identical_duplicate_is_skipped_before_the_equality_check(tmp_path, capsys) -> None:
    """`prevHash` wins, so an ordinary repeated file never reaches the guard.

    With the flag on and `2.pb` byte-identical to `1.pb`, the MD5 skip
    short-circuits it and the run carries on to `3.pb`.
    """
    archive = staged(tmp_path, EQUAL_A)

    code, _, err = run_cli(compat(tmp_path, archive, EQUAL_MESSAGE_ABORT_FLAG), capsys)

    assert code == cli.EXIT_OK
    assert err == ""
    assert written(archive) == ["1.pb.results.json", "3.pb.results.json"]


def test_modern_mode_ignores_the_flag_even_when_a_caller_sets_it(tmp_path) -> None:
    """Mode is descriptor, registry and writer. `prepare` drops the request under
    modern, so the equal pair is validated and reported the way it always was."""
    archive = staged(tmp_path, EQUAL_B)

    result = api.validate(
        api.Request(
            mode=Mode.MODERN,
            gtfs=static_feed(tmp_path),
            inputs=api.resolve_walk(str(archive), SortBy.DATE_MODIFIED),
            abort_on_equal_message=True,
        )
    )

    assert result.run.messages_validated == 3
    assert "E017" in result.run.notices.rule_ids()


def test_the_flag_is_refused_on_the_modern_surface(tmp_path, capsys) -> None:
    """It reproduces an upstream behaviour, so it belongs to `--compat` alone."""
    code, _, err = run_cli([EQUAL_MESSAGE_ABORT_FLAG, "-gtfs", "feed.zip", "-rt", "x.pb"], capsys)

    assert code == cli.EXIT_USAGE
    assert EQUAL_MESSAGE_ABORT_FLAG in err
    assert "--compat" in err


@needs_jar
def test_the_jar_and_this_project_abort_on_the_same_file(tmp_path) -> None:
    """The differential, both halves over the same three inputs. Measured.

    `run_jar.run` cannot serve here for two reasons: `invoke` raises on a nonzero
    exit, and a nonzero exit is what is being measured, and it deletes the run
    directory, where the *absence* of two results files is half the evidence.

    Two directories rather than one, because upstream's walk has no extension
    filter (`runner/dedupe.py`): a second run over the jar's directory would read
    `1.pb.results.json` back in as a feed.

    Never weaken this to make the halves agree. If the surviving file's bytes
    ever differ, report the bytes.
    """
    theirs, ours = tmp_path / "jar", tmp_path / "ours"
    for directory in (theirs, ours):
        directory.mkdir()
        run_jar.stage({"1.pb": EQUAL_A, "2.pb": EQUAL_B, "3.pb": THIRD}, directory)
    outcome = subprocess.run(  # noqa: S603
        [
            str(jarenv.checked_java_17()[0]),
            "-jar",
            str(jarenv.JAR),
            "-gtfs",
            str(jarenv.GOLDEN_GTFS),
            "-gtfsRealtimePath",
            str(theirs),
        ],
        capture_output=True,
        text=True,
        check=False,
        timeout=run_jar.RUN_TIMEOUT,
    )
    code = cli.main(
        [
            "--compat",
            "-gtfs",
            str(jarenv.GOLDEN_GTFS),
            "-gtfsRealtimePath",
            str(ours),
            EQUAL_MESSAGE_ABORT_FLAG,
        ]
    )

    assert "feedMessage and previousFeedMessage must not be the same" in outcome.stderr
    assert "TimestampValidator.java:67" in outcome.stderr
    assert outcome.returncode == code == cli.EXIT_UPSTREAM_CRASH
    assert written(theirs) == written(ours) == ["1.pb.results.json"]
    assert (theirs / f"1.pb{RESULTS}").read_bytes() == (ours / f"1.pb{RESULTS}").read_bytes()
