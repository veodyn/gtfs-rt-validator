"""Modern's argument contract, and the exit codes both surfaces share.

Split from `cli.py` the way the sibling splits its own, and for the same reason:
a wrapper script sees only the flags and the exit status, so both are a closed
contract worth reading on their own. `cli.py` keeps the running and the
printing; nothing here writes to the terminal, apart from argparse's own
`--help` and `--version` actions.

**Exit codes follow the sibling.** A finding is not a tool failure:

| Situation | Code |
|---|---|
| clean run, findings or none | 0 |
| `--fail-on-error` and an error-severity rule fired | 1 |
| `--fail-on-error` and only warnings fired | 0 |
| bad flags, missing input, a dropped flag | 1 |
| static feed will not load | 255 |
| compat run finished and there is no compat writer yet | 255 |
| compat abort: upstream's own run would have died here | 1 |
| compat, realtime path missing: upstream logs it and carries on | 0 |

The last two are upstream's numbers rather than the sibling's, and only apply
under `--compat`. An uncaught exception out of a Java `main` exits 1, measured
on this machine, and the agency-less NPE and every commons-cli parse exception
escape `main`. A missing `-gtfsRealtimePath` does not: `Files.walk` throws
`NoSuchFileException`, `main` catches `IOException`, logs it, and exits 0.

**Modern's flags are ordinary, deliberately.** `--ignore-shapes` is a switch
with no value to invert, `--sort` refuses a value it does not recognise where
upstream silently means date, and every flag that wants an argument says so
through argparse rather than throwing. Upstream's two parsing bugs are compat
surface and live in `compatcli.py`; a user who types an upstream spelling here
is told which mode it belongs to.
"""

from __future__ import annotations

import argparse
import datetime as dt
from collections.abc import Sequence
from pathlib import Path
from typing import NoReturn

from gtfs_rt_validator import api
from gtfs_rt_validator.api import Request, UsageError
from gtfs_rt_validator.runner import Mode, SortBy
from gtfs_rt_validator.version import VERSION

__all__ = [
    "COMPAT_FLAG",
    "COMPAT_ONLY_FLAGS",
    "DEFAULT_OUT",
    "EQUAL_MESSAGE_ABORT_FLAG",
    "EXIT_FINDINGS",
    "EXIT_OK",
    "EXIT_RUNNER",
    "EXIT_UPSTREAM_CRASH",
    "EXIT_USAGE",
    "ROLES",
    "UPSTREAM_SPELLINGS",
    "build_parser",
    "modern_request",
    "reject_compat_only_flags",
    "reject_upstream_spellings",
]

EXIT_OK = 0
#: Bad flags. The sibling's `EXIT_USAGE`, and also what the JVM exits with when
#: an exception escapes `main`, which is every commons-cli parse failure.
EXIT_USAGE = 1
#: `--fail-on-error` opting in. The sibling returns a bare 1 here too.
EXIT_FINDINGS = 1
#: Upstream's run would have died. Same number, different reason, kept apart so
#: the table above stays honest.
EXIT_UPSTREAM_CRASH = 1
#: The sibling's `EXIT_RUNNER`: the tool could not do the job.
EXIT_RUNNER = 255

COMPAT_FLAG = "--compat"

#: Ask compat to reproduce upstream's equal-message abort as well as its rules.
#:
#: **Upstream has no such flag.** `TimestampValidator.java:66-68` throws
#: unconditionally and nothing catches it, so the jar always dies there. This
#: project makes it opt-in because upstream's behaviour throws away a complete
#: report: the file that triggered it gets no `.results.json` and neither does
#: any file after it, however many thousands were still to come. A user who
#: wants the parity asks for it; a user who wants the report gets E017 and a
#: finished run.
#:
#: It is a flag rather than an environment variable because this project reads
#: no environment at all: it is configured by CLI flags only, mirroring
#: upstream's interface.
#:
#: Spelled with two hyphens because it is *this project's* flag, not one
#: inherited from upstream. `--compat` is the only precedent on this surface and
#: it is spelled the same way, and for the same reason: `cli.main` strips both
#: before `compatcli.parse` ever sees argv, so upstream's six-option surface
#: stays exactly six options and a wrapper script written against the jar is
#: unaffected. Anything with a single hyphen would have to be one of the six.
EQUAL_MESSAGE_ABORT_FLAG = "--upstream-equal-message-abort"

#: This project's own flags that belong to `--compat` and nowhere else, with the
#: reason a modern run is told they do not apply.
COMPAT_ONLY_FLAGS = {
    EQUAL_MESSAGE_ABORT_FLAG: (
        "it reproduces an upstream crash, and modern mode disagrees with upstream on purpose, "
        "reporting an equal pair of messages as E017 and finishing the run"
    )
}

DEFAULT_OUT = "out"
ROLES = ("tu", "vp", "sa")

#: Upstream's spellings, and modern's where there is one. A user who types the
#: flag they know gets told which mode it belongs to rather than
#: "unrecognized arguments".
UPSTREAM_SPELLINGS = {
    "-gtfsRealtimePath": "-rt",
    "-sort": "--sort",
    "-ignoreShapes": "--ignore-shapes",
    "-plainText": None,
    "-stats": None,
}

EPILOG = f"""\
{COMPAT_FLAG} swaps this flag surface for upstream's:

    gtfs-rt-validator --compat -gtfs feed.zip -gtfsRealtimePath archive/

Two of upstream's parsing bugs are compat surface and are reproduced there:
`-ignoreShapes false` enables it, and a bare `-ignoreShapes` is a crash rather
than a no-op. `-stats` has the identical shape. Modern mode reproduces neither.
`-plainText` and `-stats` are not implemented in either mode and say so.

{EQUAL_MESSAGE_ABORT_FLAG} is this project's own,
takes no value, and works only alongside {COMPAT_FLAG}. Upstream has no such
flag: `TimestampValidator` throws when a message equals the one before it,
nothing catches it, and the run dies with no results for that file or for any
file after it. Pass this to reproduce that. Left off, which is the default, an
equal pair is reported as E017 and the run finishes.
"""


class _Parser(argparse.ArgumentParser):
    """argparse, with its exit turned back into this project's usage error.

    Left alone it calls `sys.exit(2)`, which is a third number for the one thing
    the table above already has one for.
    """

    def error(self, message: str) -> NoReturn:
        raise UsageError(message)


def build_parser() -> argparse.ArgumentParser:
    parser = _Parser(
        prog="gtfs-rt-validator",
        description="Validate GTFS-Realtime messages against a GTFS feed.",
        epilog=EPILOG,
        allow_abbrev=False,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--version", action="version", version=f"gtfs-rt-validator {VERSION}")
    parser.add_argument("-gtfs", metavar="PATH", help="the GTFS zip to validate against")
    parser.add_argument(
        "-rt", metavar="TARGET", help="a message, a directory to replay, or an http(s) URL"
    )
    parser.add_argument("-tu", metavar="TARGET", help="TripUpdates, under its own feed role")
    parser.add_argument("-vp", metavar="TARGET", help="VehiclePositions, under its own feed role")
    parser.add_argument("-sa", metavar="TARGET", help="Alerts, under its own feed role")
    parser.add_argument(
        "--sort",
        choices=("name", "date"),
        default="date",
        help="replay order, and where each file's clock comes from",
    )
    parser.add_argument("--at", metavar="ISO8601", help="pin the clock, for a reproducible run")
    parser.add_argument("--out", metavar="DIR", default=DEFAULT_OUT, help="where the reports go")
    parser.add_argument(
        "--ignore-shapes",
        action="store_true",
        dest="ignore_shapes",
        help="skip shapes.txt entirely; a plain switch, with no value to invert",
    )
    parser.add_argument(
        "--fail-on-error",
        action="store_true",
        dest="fail_on_error",
        help="exit 1 when an error-severity rule fired; off by default, as upstream exits 0",
    )
    return parser


def reject_upstream_spellings(argv: Sequence[str]) -> None:
    """Say which mode a flag belongs to, rather than letting argparse guess."""
    for token in argv:
        if token not in UPSTREAM_SPELLINGS:
            continue
        modern = UPSTREAM_SPELLINGS[token]
        instead = f" The modern spelling is {modern}." if modern else ""
        raise UsageError(
            f"{token} is upstream's flag, and modern mode does not take it.{instead} "
            f"Pass {COMPAT_FLAG} for upstream's flag surface, where `-ignoreShapes false` "
            f"enables it and a bare `-ignoreShapes` is a crash. Modern reproduces neither."
        )


def reject_compat_only_flags(argv: Sequence[str]) -> None:
    """Refuse this project's `--compat`-only flags on the modern surface.

    Separate from `reject_upstream_spellings` because the two say opposite
    things: that one is about a flag modern never had, this one is about a flag
    modern will not have.
    """
    for token in argv:
        why = COMPAT_ONLY_FLAGS.get(token)
        if why is not None:
            raise UsageError(f"{token} belongs to {COMPAT_FLAG} and modern mode ignores it: {why}.")


def _moment(text: str | None) -> dt.datetime | None:
    """`--at`, which must be an instant: the clock is not a wall time."""
    if text is None:
        return None
    try:
        parsed = dt.datetime.fromisoformat(text)
    except ValueError as bad:
        raise UsageError(f"--at {text!r} is not an ISO-8601 timestamp: {bad}") from bad
    if parsed.tzinfo is None:
        raise UsageError(f"--at {text!r} carries no timezone, and the clock is an instant")
    return parsed


def _modern_inputs(namespace: argparse.Namespace, sort_by: SortBy) -> api.Inputs:
    """One realtime shape, chosen by which flags arrived."""
    roles = {role: getattr(namespace, role) for role in ROLES if getattr(namespace, role)}
    if namespace.rt and roles:
        raise UsageError("-rt takes the whole feed; -tu, -vp and -sa name roles. Use one or other.")
    if not namespace.rt and not roles:
        raise UsageError("give -rt a message, a directory or a URL, or name roles with -tu/-vp/-sa")
    try:
        if namespace.rt:
            return api.resolve(namespace.rt, sort_by=sort_by, fetch=api.fetch_once)
        return api.resolve_roles(roles, fetch=api.fetch_once)
    except (OSError, ValueError) as bad:
        raise UsageError(str(bad)) from bad


def modern_request(namespace: argparse.Namespace) -> Request:
    """The parsed flags as a run, or a `UsageError` saying what is missing."""
    if namespace.gtfs is None:
        raise UsageError("-gtfs is required: a realtime message is validated against a GTFS feed")
    sort_by = SortBy.from_cli(namespace.sort)
    return Request(
        mode=Mode.MODERN,
        gtfs=Path(namespace.gtfs),
        inputs=_modern_inputs(namespace, sort_by),
        sort_by=sort_by,
        at=_moment(namespace.at),
        ignore_shapes=namespace.ignore_shapes,
    )
