"""Which files a directory replay reads, in what order, and which it skips.

Two behaviours from `BatchProcessor.processFeeds`, both easy to get subtly wrong.

**The walk** (L168-185) filters on `Files::isRegularFile` and nothing else. There
is no extension test anywhere in the class, so a second run over a directory
reads the first run's `.results.json` files as if they were feeds. That is
upstream behaviour and is reproduced here; keeping differential corpora isolated
is the harness's job, not this module's.

**Duplicate suppression** (L214-218) skips a file whose MD5 equals `prevHash`.
The subtlety is where `prevHash` is assigned: L295, *after* the results file has
been written. Every earlier `continue` in the loop, the unreadable file at L206
and the undecodable one at L240, leaves `prevHash` pointing at the last file that
was actually validated. So the comparison basis is "the last file written", not
"the previous path in the list", and the two readings differ on the sequence
A, B(skipped), A.
"""

from __future__ import annotations

import hashlib
from functools import cmp_to_key
from pathlib import Path

from gtfs_rt_validator.runner.clock import SortBy, last_modified_millis

__all__ = ["DuplicateFilter", "md5_digest", "walk"]


def md5_digest(data: bytes) -> bytes:
    """`MessageDigest.getInstance("MD5").digest(protobuf)` (L187, L214).

    MD5 is upstream's choice and this reproduces it. It is change detection over
    a local file, never an integrity or authentication check, and swapping it for
    a stronger hash would change which files a compat run skips.
    """
    return hashlib.md5(data).digest()  # noqa: S324 - mirrors upstream's prevHash


class DuplicateFilter:
    """`prevHash`, with the assignment point that gives it its meaning.

    Split into two calls on purpose. `is_duplicate` is the L215 test; the basis
    only moves when the caller reaches L295, which it does not do for a file it
    skipped for any other reason.
    """

    __slots__ = ("_previous",)

    def __init__(self) -> None:
        self._previous: bytes | None = None

    @property
    def previous(self) -> bytes | None:
        """The digest of the last file validated and written, or None."""
        return self._previous

    def is_duplicate(self, digest: bytes) -> bool:
        """`MessageDigest.isEqual(currentHash, prevHash)`.

        Returns false when `prevHash` is still null, which is why the first file
        of a run is never skipped as a duplicate.
        """
        return self._previous is not None and digest == self._previous

    def mark_written(self, digest: bytes) -> None:
        """L295. Call only once the file's results have actually been written."""
        self._previous = digest


def _name_sort_key(path: Path) -> bytes:
    """`SortUtils.compareByFileName` L76-78.

    Two departures from `sorted(paths)` that both change output order.
    `getFileName()` drops the directory, so equal base names in different
    subdirectories tie and fall back to walk order. And `String.compareTo`
    compares UTF-16 code units, which orders a supplementary character below
    U+E000..U+FFFF where Python's code-point comparison puts it above; encoding
    big-endian reproduces the Java ordering exactly.
    """
    return path.name.encode("utf-16-be", "surrogatepass")


def _compare_by_date_modified(left: Path, right: Path, cache: dict[Path, int]) -> int:
    """`SortUtils.compareByDateModified` L52-54, inside L172-179's try/catch.

    Upstream logs an IOException and returns 0, treating the pair as equal
    rather than failing the run. The stat cache is ours: upstream calls
    `getLastModifiedTime` on every comparison, which is O(n log n) syscalls for
    an answer that cannot change without the run already being racy.
    """
    try:
        for path in (left, right):
            if path not in cache:
                cache[path] = last_modified_millis(path)
    except OSError:
        return 0
    return (cache[left] > cache[right]) - (cache[left] < cache[right])


def walk(root: Path, sort_by: SortBy) -> list[Path]:
    """`Files.walk(root).filter(Files::isRegularFile).sorted(...)` (L168-185).

    Every regular file below `root`, recursively, with no extension filter.
    `Files.walk` does not follow symbolic links when descending but
    `Files.isRegularFile` does resolve them, so a symlink to a file is included
    while a symlink to a directory is not descended into; `Path.rglob` and
    `Path.is_file` draw the same two lines. A regular file as `root` walks to a
    one-element list, and a missing `root` throws `NoSuchFileException`. All
    three were measured on JDK 17 rather than inferred, and `test_symlinks`
    holds the layout they were measured on.

    Both sorts are stable, so files that compare equal keep the order the
    directory scan produced. That order is the platform's, in Java as much as
    here, which is why a corpus that needs a fixed order needs distinct sort
    keys rather than a fixed walk.
    """
    root.stat()  # NoSuchFileException, eagerly, the way Files.walk does
    if root.is_file():
        return [root]
    files = [path for path in root.rglob("*") if path.is_file()]
    if sort_by is SortBy.NAME:
        return sorted(files, key=_name_sort_key)
    cache: dict[Path, int] = {}
    return sorted(files, key=cmp_to_key(lambda a, b: _compare_by_date_modified(a, b, cache)))
