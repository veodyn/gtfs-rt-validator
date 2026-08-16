"""Turning what a user typed into cycles the runner can walk.

Three shapes plus named roles, and one rule that is easy to miss: under
`--compat` a URL is not an input at all. Upstream's batch mode takes a
`-gtfsRealtimePath` and hands it to `Files.walk`, so `https://...` there is a
path that does not exist, and reproducing that is the difference between a
compat run behaving like the jar and behaving like this project.
"""

from __future__ import annotations

import pytest

from clifixtures import workspace
from gtfs_rt_validator import inputs
from gtfs_rt_validator.runner import SortBy
from runnerfixtures import feed, written_feed

URL = "https://example.org/TripUpdates.pb"


def test_a_file_is_one_cycle_of_one_source_named_as_it_was_given(tmp_path):
    """`Source.name` is the path as typed: upstream writes its results file
    beside the file it was handed, not beside a resolved one."""
    space = workspace(tmp_path)

    resolved = inputs.resolve(str(space.rt))

    assert resolved.directory_replay is False
    assert len(resolved.cycles) == 1
    (source,) = resolved.cycles[0]
    assert source.name == str(space.rt)
    assert source.role == "rt"
    assert source.fetch is None


def test_a_directory_is_a_replay_in_the_walk_order_the_sort_chose(tmp_path):
    space = workspace(tmp_path)

    resolved = inputs.resolve(str(space.archive), sort_by=SortBy.NAME)

    assert resolved.directory_replay is True
    assert resolved.names() == (str(space.archive / "one.pb"), str(space.archive / "two.pb"))


def test_a_url_carries_a_fetch_callable_and_no_path():
    resolved = inputs.resolve(URL, fetch=lambda url: feed("a"))

    (source,) = resolved.cycles[0]
    assert source.path is None
    assert source.fetch is not None
    assert source.read() == feed("a")


def test_only_http_and_https_count_as_a_url(tmp_path):
    """Anything else is a path, which is what a user typing `./ftp.pb` means."""
    assert inputs.is_url("http://example.org/x.pb")
    assert inputs.is_url(URL)
    assert not inputs.is_url("ftp://example.org/x.pb")
    assert not inputs.is_url(str(tmp_path))


def test_compat_treats_a_url_as_a_path_that_does_not_exist():
    """Upstream would hand it to `Files.walk` and get `NoSuchFileException`."""
    with pytest.raises(FileNotFoundError):
        inputs.resolve_walk(URL, SortBy.DATE_MODIFIED)


def test_the_walk_takes_a_file_as_readily_as_a_directory(tmp_path):
    """`Files.walk` on a regular file yields that one file, so upstream accepts
    `-gtfsRealtimePath one.pb` without ever saying so."""
    space = workspace(tmp_path)

    resolved = inputs.resolve_walk(str(space.rt), SortBy.DATE_MODIFIED)

    assert resolved.names() == (str(space.rt),)


def test_a_target_that_is_neither_a_url_nor_a_path_is_a_file_not_found(tmp_path):
    with pytest.raises(FileNotFoundError):
        inputs.resolve(str(tmp_path / "nope.pb"))


def test_named_roles_are_ordered_and_keep_their_roles(tmp_path):
    paths = {role: str(written_feed(tmp_path, f"{role}.pb", role)) for role in ("sa", "vp", "tu")}

    resolved = inputs.resolve_roles(paths)

    assert resolved.directory_replay is False
    assert len(resolved.cycles) == 1
    assert [source.role for source in resolved.cycles[0]] == ["tu", "vp", "sa"]


def test_a_named_role_may_be_a_url(tmp_path):
    paths = {"tu": URL, "vp": str(written_feed(tmp_path, "vp.pb", "v"))}

    resolved = inputs.resolve_roles(paths, fetch=lambda url: feed("a"))

    kinds = [(source.role, source.fetch is None) for source in resolved.cycles[0]]
    assert kinds == [("tu", False), ("vp", True)]


def test_a_directory_under_a_named_role_is_refused(tmp_path):
    """A role is one snapshot per cycle. Two roles replaying two directories of
    different lengths has no defined alignment, and `runner/context.py` says
    alignment is positional, so there is nothing to guess at here."""
    space = workspace(tmp_path)

    with pytest.raises(ValueError, match="directory"):
        inputs.resolve_roles({"tu": str(space.archive)})


def test_fetch_once_refuses_a_scheme_that_is_not_http(tmp_path):
    """`urllib` will happily open `file://`, which turns a feed URL into a local
    file read. The fetcher names the two schemes it serves."""
    with pytest.raises(ValueError, match="http"):
        inputs.fetch_once(f"file://{tmp_path}/feed.zip")
