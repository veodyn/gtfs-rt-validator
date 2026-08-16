"""What the user typed, turned into the cycles the runner walks.

`runner/sources.py` owns what a `Source` is and how sources group into cycles;
this module owns the other half, which is deciding *which* shape a string names.
Four of them, and the split between the two entry points is the mode boundary:

- `resolve` is modern's `-rt` and its named roles: a file, a directory, or a
  URL, told apart by looking at the string and then at the filesystem.
- `resolve_walk` is upstream's `-gtfsRealtimePath`, which is a path handed
  straight to `Files.walk`. There is no URL case there at all, so a URL under
  `--compat` is a path that does not exist, which is exactly what the jar makes
  of it.

**The fetcher lives here and not in the runner.** `Source.fetch` is a callable
so that `urllib` stays off the validation path entirely: the loop calls
`read()`, and whether that opens a socket or a file is settled before the run
starts. `fetch_once` is the callable a front end supplies, and its name is its
contract - the loop reads each source once, so a URL is fetched once.

No environment variables anywhere, which for the fetcher means no proxy
configuration beyond what `urllib` reads from the platform by default.
"""

from __future__ import annotations

import platform
import urllib.request
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path

from gtfs_rt_validator.runner import (
    DEFAULT_ROLE,
    ROLE_ORDER,
    SortBy,
    Source,
    file_cycles,
    url_cycle,
)
from gtfs_rt_validator.runner.sources import Cycle
from gtfs_rt_validator.version import VERSION

__all__ = [
    "DEFAULT_TIMEOUT",
    "URL_SCHEMES",
    "USER_AGENT",
    "Inputs",
    "fetch_once",
    "is_url",
    "resolve",
    "resolve_roles",
    "resolve_walk",
]

#: The two schemes a feed is served over. Anything else is a path, which is what
#: a user who typed `./ftp.pb` meant. `file://` is deliberately not here: it
#: would turn a feed URL into an arbitrary local read.
URL_SCHEMES = ("http://", "https://")

#: The sibling's shape, `<name>/<version> (<runtime>)`, with this project's name:
#: a server's logs should say which client actually called.
USER_AGENT = f"gtfs-rt-validator/{VERSION} (Python {platform.python_version()})"

#: Seconds. A realtime message is small and a feed that will not answer in this
#: long is down, not slow.
DEFAULT_TIMEOUT = 60.0

Fetcher = Callable[[str], bytes]


def is_url(target: str) -> bool:
    return target.startswith(URL_SCHEMES)


def fetch_once(url: str, *, timeout: float = DEFAULT_TIMEOUT) -> bytes:
    """The bytes behind a URL, read once, in one piece.

    Not streamed to a file, unlike the sibling's static-feed download: a
    realtime message is a few hundred kilobytes and the decoder takes bytes.
    """
    if not is_url(url):
        raise ValueError(f"{url!r} is not an http or https URL; those are the two schemes served")
    # S310: the scheme is checked on the line above, which is what the rule asks
    # for. The URL is a CLI argument, so it cannot be anything the caller did not
    # type.
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})  # noqa: S310
    with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310
        return response.read()


@dataclass(frozen=True, slots=True)
class Inputs:
    """The realtime half of a request: cycles, and whether they are a replay.

    `directory_replay` is carried rather than inferred later because only this
    module knows how the cycles were built, and `runner/clock.py` needs the
    answer to decide where modern mode's clock comes from.
    """

    cycles: tuple[Cycle, ...]
    directory_replay: bool

    def names(self) -> tuple[str, ...]:
        return tuple(source.name for cycle in self.cycles for source in cycle)


def _one_source(target: str, role: str, fetch: Fetcher) -> Source:
    """One input under one role: a URL behind a callable, or a readable file."""
    if is_url(target):
        return Source(target, role, None, lambda: fetch(target))
    path = Path(target)
    if path.is_dir():
        raise ValueError(f"{target} is a directory, and a feed role takes one message per cycle")
    if not path.is_file():
        raise FileNotFoundError(f"{target} is neither a URL nor a file")
    return Source(target, role, path)


def resolve(
    target: str,
    *,
    sort_by: SortBy = SortBy.DATE_MODIFIED,
    role: str = DEFAULT_ROLE,
    fetch: Fetcher = fetch_once,
) -> Inputs:
    """Modern's `-rt`: a URL, a directory to replay, or a single file."""
    if is_url(target):
        return Inputs((url_cycle(target, lambda: fetch(target), role),), False)
    path = Path(target)
    if path.is_dir():
        return Inputs(tuple(file_cycles(path, sort_by)), True)
    return Inputs(((_one_source(target, role, fetch),),), False)


def resolve_roles(targets: Mapping[str, str], *, fetch: Fetcher = fetch_once) -> Inputs:
    """One cycle over the named roles, in `ROLE_ORDER`.

    That order is the CLI's own `-tu -vp -sa`, and it decides which role hosts
    the cycle's cross-feed rules; `runner/context.py` owns why.
    """
    unknown = [role for role in targets if role not in ROLE_ORDER]
    if unknown:
        raise ValueError(f"{unknown} name no feed role; the roles are {list(ROLE_ORDER)}")
    ordered = [role for role in ROLE_ORDER if role in targets]
    return Inputs((tuple(_one_source(targets[role], role, fetch) for role in ordered),), False)


def resolve_walk(target: str, sort_by: SortBy) -> Inputs:
    """Upstream's `-gtfsRealtimePath`, handed to `Files.walk` as it stands.

    Every regular file below it, one per cycle, with no extension filter and no
    URL case. A missing root raises, reproducing `NoSuchFileException`, which is
    the `IOException` `Main` catches and logs before exiting 0.
    """
    return Inputs(tuple(file_cycles(Path(target), sort_by)), True)
