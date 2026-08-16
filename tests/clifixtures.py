"""A workspace on disk for the front-end tests: a static feed and some messages.

A module of plain functions rather than a `conftest.py`, matching
`gtfsfixtures.py` and `runnerfixtures.py`. The CLI tests all want the same small
tree (one archive, one loose message, a directory of two) and differ only in the
argv they hand it, so one builder covers them.

`run_cli` is here rather than in each test module because the front end's
contract is three values at once: the exit code, what it printed and what it
printed it to. A test that checked only the code would pass on a run that said
nothing about why.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from gtfs_rt_validator import cli
from gtfsfixtures import build_feed, minimal_tables
from runnerfixtures import AGENCY_COLUMNS, static_feed, written_feed


@dataclass(frozen=True)
class Workspace:
    """Everything a front-end test points argv at."""

    gtfs: Path
    rt: Path
    archive: Path
    out: Path


def workspace(tmp_path: Path) -> Workspace:
    """A loadable feed, one loose message and an archive of two."""
    archive = tmp_path / "archive"
    archive.mkdir()
    written_feed(archive, "one.pb", "x")
    written_feed(archive, "two.pb", "y")
    return Workspace(
        gtfs=static_feed(tmp_path),
        rt=written_feed(tmp_path, "TripUpdates.pb", "a"),
        archive=archive,
        out=tmp_path / "out",
    )


def agency_less(tmp_path: Path) -> Path:
    """The feed `TimeZone.getTimeZone(null)` dies on, under its own name.

    `static_feed` already owns `feed.zip` in the same directory, so this one is
    named apart rather than overwriting it.
    """
    tables = minimal_tables()
    tables["agency.txt"] = []
    return build_feed(
        tmp_path, tables, name="agencyless.zip", columns={"agency.txt": AGENCY_COLUMNS}
    )


def unloadable(tmp_path: Path) -> Path:
    """An archive with no `stops.txt`, which the sibling's loader refuses."""
    tables = minimal_tables()
    del tables["stops.txt"]
    return build_feed(tmp_path, tables, name="nostops.zip")


def run_cli(argv: list[str], capsys) -> tuple[int, str, str]:
    """The exit code, stdout and stderr of one invocation."""
    code = cli.main(argv)
    captured = capsys.readouterr()
    return code, captured.out, captured.err
