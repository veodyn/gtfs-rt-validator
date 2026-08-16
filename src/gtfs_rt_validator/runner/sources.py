"""What a run reads, and how the reads group into cycles.

A `Source` is one realtime input under one role. A *cycle* is the tuple of
sources that belong to the same instant: one file for an archive replay, one
file per role for `-tu tu.pb -vp vp.pb`. `runner/context.py` explains why
alignment is positional and what a cycle means to a cross-feed rule.

The runner never opens a socket. A URL input arrives as a `Source` carrying a
`fetch` callable, which keeps `urllib` out of the validation path entirely and
lets a test hand the loop bytes with no file behind them. "Fetch a URL once" is
then literally true: the loop calls `read()` once per source.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path

from gtfs_rt_validator.runner.clock import SortBy
from gtfs_rt_validator.runner.context import DEFAULT_ROLE, role_key
from gtfs_rt_validator.runner.dedupe import walk

__all__ = ["Cycle", "Source", "file_cycles", "role_cycle", "url_cycle"]


@dataclass(frozen=True, slots=True)
class Source:
    """One realtime input: what to call it, which role it plays, where it is.

    `name` is what lands in a report under `sourceFile` and what the compat
    writer appends `.results.json` to, so it is the path as given rather than a
    resolved one: upstream writes beside the file it was handed.
    """

    name: str
    role: str = DEFAULT_ROLE
    path: Path | None = None
    fetch: Callable[[], bytes] | None = None

    def read(self) -> bytes:
        """The bytes, or `OSError` for an input that went away or will not open.

        `OSError` is upstream's L206 arm, where it logs and skips the file. A
        `fetch` that raises something else is a bug in whatever supplied it, and
        propagates like any other bug in this project.
        """
        if self.fetch is not None:
            return self.fetch()
        if self.path is None:
            raise OSError(f"{self.name} has neither a path nor a fetch")
        return self.path.read_bytes()


Cycle = tuple[Source, ...]


def file_cycles(root: Path, sort_by: SortBy) -> list[Cycle]:
    """Upstream's walk, one file per cycle, in `dedupe.walk`'s order.

    One file per cycle rather than one cycle holding everything: an archive
    replay is a sequence of instants, and a rule's "previous message" is the
    file before this one.
    """
    return [(Source(str(path), DEFAULT_ROLE, path),) for path in walk(root, sort_by)]


def role_cycle(paths: Mapping[str, Path]) -> Cycle:
    """One cycle over named roles, in `ROLE_ORDER` so the host comes first."""
    return tuple(
        Source(str(paths[role]), role, paths[role]) for role in sorted(paths, key=role_key)
    )


def url_cycle(url: str, fetch: Callable[[], bytes], role: str = DEFAULT_ROLE) -> Cycle:
    """One cycle over one URL. It has no path, so it has no modification time,
    which is why `modern_reading` takes `None` and answers "now"."""
    return (Source(url, role, None, fetch),)
