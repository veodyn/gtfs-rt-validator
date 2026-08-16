"""The directory walk and duplicate suppression.

Pinned to upstream at 7041fa3: `BatchProcessor.processFeeds` L168-185 (the walk
and its two comparators), L214-218 (the MD5 skip) and L295 (where `prevHash` is
finally updated), plus `SortUtils` L52-54 and L76-78.
"""

from __future__ import annotations

import hashlib
import os
from pathlib import Path

import pytest

from gtfs_rt_validator.runner.clock import SortBy
from gtfs_rt_validator.runner.dedupe import DuplicateFilter, md5_digest, walk

A = b"feed-a"
B = b"feed-b"


def _touch(path: Path, data: bytes = b"\x00", millis: int = 1_000) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    os.utime(path, ns=(millis * 1_000_000, millis * 1_000_000))
    return path


class TestWalk:
    def test_no_extension_filter(self, tmp_path: Path) -> None:
        """A second run over a directory ingests the first run's output."""
        _touch(tmp_path / "TripUpdates.pb")
        _touch(tmp_path / "TripUpdates.pb.results.json")
        _touch(tmp_path / "notes.txt")
        assert [p.name for p in walk(tmp_path, SortBy.NAME)] == [
            "TripUpdates.pb",
            "TripUpdates.pb.results.json",
            "notes.txt",
        ]

    def test_recurses_and_skips_directories(self, tmp_path: Path) -> None:
        _touch(tmp_path / "b" / "inner.pb")
        _touch(tmp_path / "a.pb")
        (tmp_path / "empty").mkdir()
        assert [p.name for p in walk(tmp_path, SortBy.NAME)] == ["a.pb", "inner.pb"]

    def test_symlinks(self, tmp_path: Path) -> None:
        """Files.walk does not descend symlinked directories; isRegularFile resolves.

        Measured on JDK 17 against this exact layout: the walk yields
        realdir/deep.pb once, sub/linkfile.pb as a file, and nothing through
        sub/linkdir.
        """
        _touch(tmp_path / "a.pb")
        _touch(tmp_path / "realdir" / "deep.pb")
        (tmp_path / "sub").mkdir()
        (tmp_path / "sub" / "linkdir").symlink_to(tmp_path / "realdir")
        (tmp_path / "sub" / "linkfile.pb").symlink_to(tmp_path / "a.pb")
        walked = walk(tmp_path, SortBy.NAME)
        assert sorted(str(p.relative_to(tmp_path)) for p in walked) == [
            "a.pb",
            "realdir/deep.pb",
            "sub/linkfile.pb",
        ]

    def test_name_sort_compares_the_base_name_only(self, tmp_path: Path) -> None:
        """SortUtils.compareByFileName L77 calls getFileName() first."""
        _touch(tmp_path / "zzz" / "a.pb")
        _touch(tmp_path / "aaa" / "z.pb")
        assert [p.parent.name for p in walk(tmp_path, SortBy.NAME)] == ["zzz", "aaa"]

    def test_name_sort_uses_utf16_code_unit_order(self, tmp_path: Path) -> None:
        """Java's String.compareTo orders by UTF-16 code unit, not code point.

        U+FF21 is one code unit; U+10000 is a surrogate pair whose leading unit
        (U+D800) sorts below it. Python's native str comparison disagrees.
        """
        _touch(tmp_path / "\uff21.pb")
        _touch(tmp_path / "\U00010000.pb")
        walked = [p.name for p in walk(tmp_path, SortBy.NAME)]
        assert walked == ["\U00010000.pb", "\uff21.pb"]
        assert sorted(walked) == ["\uff21.pb", "\U00010000.pb"]

    def test_date_modified_sort_is_ascending(self, tmp_path: Path) -> None:
        _touch(tmp_path / "c.pb", millis=3_000)
        _touch(tmp_path / "a.pb", millis=9_000)
        _touch(tmp_path / "b.pb", millis=1_000)
        assert [p.name for p in walk(tmp_path, SortBy.DATE_MODIFIED)] == [
            "b.pb",
            "c.pb",
            "a.pb",
        ]

    def test_date_modified_is_the_default(self, tmp_path: Path) -> None:
        _touch(tmp_path / "a.pb", millis=9_000)
        _touch(tmp_path / "b.pb", millis=1_000)
        assert walk(tmp_path, SortBy.from_cli(None)) == walk(tmp_path, SortBy.DATE_MODIFIED)

    def test_a_regular_file_root_walks_to_itself(self, tmp_path: Path) -> None:
        """Files.walk on a regular file yields that one file."""
        path = _touch(tmp_path / "only.pb")
        assert walk(path, SortBy.NAME) == [path]

    def test_a_missing_root_raises(self, tmp_path: Path) -> None:
        with pytest.raises(OSError, match="nope"):
            walk(tmp_path / "nope", SortBy.NAME)


class TestMd5Digest:
    def test_is_md5_of_the_raw_bytes(self) -> None:
        assert md5_digest(A) == hashlib.md5(A).digest()  # noqa: S324
        assert len(md5_digest(A)) == 16


class TestDuplicateFilter:
    def test_the_first_file_is_never_a_duplicate(self) -> None:
        """MessageDigest.isEqual returns false when either argument is null."""
        assert DuplicateFilter().is_duplicate(md5_digest(A)) is False

    def test_identical_bytes_after_a_write_are_a_duplicate(self) -> None:
        f = DuplicateFilter()
        f.mark_written(md5_digest(A))
        assert f.is_duplicate(md5_digest(A)) is True
        assert f.is_duplicate(md5_digest(B)) is False


def _batch(files: list[tuple[bytes, bool]]) -> list[str]:
    """Upstream's loop: hash, skip on match, then update `prevHash` after writing."""
    seen = DuplicateFilter()
    outcomes = []
    for data, decodes in files:
        digest = md5_digest(data)
        if seen.is_duplicate(digest):  # L215-218
            outcomes.append("skipped-duplicate")
            continue
        if not decodes:  # L238-241, a `continue` that never reaches L295
            outcomes.append("skipped-undecodable")
            continue
        outcomes.append("written")
        seen.mark_written(digest)  # L295
    return outcomes


def _batch_naive(files: list[tuple[bytes, bool]]) -> list[str]:
    """The wrong reading: compare against the immediately preceding file."""
    previous: bytes | None = None
    outcomes = []
    for data, decodes in files:
        digest = md5_digest(data)
        if previous is not None and digest == previous:
            outcomes.append("skipped-duplicate")
            previous = digest
            continue
        previous = digest
        outcomes.append("written" if decodes else "skipped-undecodable")
    return outcomes


#: The sequence that separates the two readings. Under upstream's semantics the
#: third file is a duplicate of the first, because the undecodable second file
#: never became the comparison basis.
SEQUENCE = [(A, True), (B, False), (A, True)]


class TestPrevHashSemantics:
    def test_a_skipped_file_does_not_become_the_comparison_basis(self) -> None:
        assert _batch(SEQUENCE) == [
            "written",
            "skipped-undecodable",
            "skipped-duplicate",
        ]

    def test_the_naive_reading_disagrees_on_exactly_this_sequence(self) -> None:
        assert _batch_naive(SEQUENCE) == [
            "written",
            "skipped-undecodable",
            "written",
        ]
        assert _batch_naive(SEQUENCE) != _batch(SEQUENCE)

    @pytest.mark.parametrize(
        "sequence",
        [
            [(A, True), (A, True), (B, True)],  # the naive A-A-B test
            [(A, True), (B, True), (A, True)],  # nothing skipped
            [(A, True), (A, True), (A, True)],
        ],
    )
    def test_both_readings_agree_when_nothing_is_skipped(
        self, sequence: list[tuple[bytes, bool]]
    ) -> None:
        assert _batch(sequence) == _batch_naive(sequence)
