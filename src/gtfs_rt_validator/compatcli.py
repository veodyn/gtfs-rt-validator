"""Upstream's command line, bugs included, as `LibMain.java` declares it.

Six options, all declared `.hasArg()`, all with no long form:

    -gtfs <path>  -gtfsRealtimePath <path>  -sort <name|date>
    -plainText <ext>  -stats <ignored>  -ignoreShapes <ignored>

Two of them are read with `cmd.hasOption` instead of `cmd.getOptionValue`
(`LibMain.java:203-220`), which is where the two quirks come from, and both are
compat surface rather than accidents to be tidied up:

1. **`-ignoreShapes false` enables it.** The value is parsed, stored, and never
   looked at again. `-stats` has the identical shape. `-sort` and `-plainText`
   are declared the same way but genuinely read their value, so they do not have
   this bug.
2. **A bare flag is a crash, not a no-op.** commons-cli's `checkRequiredArgs`
   throws `MissingArgumentException`, which `main` declares and does not catch,
   so the JVM exits 1. Measured on this machine: an uncaught exception out of a
   Java `main` exits 1.

The parser below is commons-cli 1.4's `DefaultParser` narrowed to these six
options, and the narrowing is what makes it small. Every option here is a
multi-character *short* option with no long form and no single-character
prefix, so `DefaultParser.isOption` reduces to "is this token one of the six",
and `isArgument` to "is it not". That is why `-gtfs -foo` sets gtfs to `-foo`:
`-foo` names no option, so it is an argument. It is also why `--compat` and
`--fail-on-error` are unrecognised options here rather than flags: they match no
long option, because these six have none.

**Not reproduced, and unmeasured:** `-gtfs=feed.zip`. `DefaultParser` splits a
token at `=` before matching, so commons-cli probably accepts it; nobody has run
the jar to find out, and guessing would put an unmeasured behaviour in the one
place this project exists to reproduce exactly. It lands as an unrecognised
option, which is loud rather than silent. `tools/build_jar.py` builds the jar
that would settle it.

Nothing here writes to the terminal: it parses, or raises for `cli.py` to print.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from gtfs_rt_validator.api import UsageError

__all__ = [
    "MISSING_INPUTS",
    "OPTIONS",
    "PLAIN_TEXT_DROPPED",
    "STATS_DROPPED",
    "VALUE_IGNORED",
    "CompatArgs",
    "MissingArgument",
    "UnrecognizedOption",
    "check_dropped",
    "parse",
]

#: The six, in `setupCommandLineOptions` order.
OPTIONS = ("gtfs", "gtfsRealtimePath", "sort", "plainText", "stats", "ignoreShapes")

#: The two read with `hasOption`, so presence is the whole answer and any value
#: is discarded. This tuple *is* the first quirk.
VALUE_IGNORED = ("stats", "ignoreShapes")

#: `LibMain.java:48-50`, verbatim. A wrapper script may well be matching on it.
MISSING_INPUTS = (
    "For batch mode you must provide a path and file name to GTFS data "
    "(e.g., -gtfs /dir/gtfs.zip) and path to directory of all archived GTFS-rt "
    "files (e.g., -gtfsRealtimePath /dir/gtfsarchive)"
)


#: Why `-plainText` is not implemented. It is upstream's flag surface and it is
#: not free: `BatchProcessor` writes the plain-text file with protobuf's
#: `TextFormat.printToString`, so honouring it without a protobuf runtime means
#: reproducing that printer, unknown-field rendering included. This project has
#: exactly one runtime dependency and it is not protobuf. Dropped deliberately,
#: and loudly: silently accepting the flag and writing nothing would be worse
#: than refusing, because the file a user asked for would simply not appear.
PLAIN_TEXT_DROPPED = (
    "-plainText is deliberately not implemented. Upstream writes those files with protobuf's "
    "TextFormat.printToString, and reproducing that printer (unknown fields included) needs a "
    "protobuf runtime this project does not have. It writes nothing to any .results.json, so "
    "dropping it costs no output parity. Re-run without it."
)

#: Why `-stats` is not implemented. `IterationStatistics` is wall clock:
#: `BatchProcessor` fills it with the GTFS read time, the byte-array time, the
#: protobuf decode time and a per-rule time, and `main` prints them through
#: slf4j. The numbers describe the machine the jar ran on, so reproducing them
#: is meaningless, and reproducing the lines would mean pinning slf4j's default
#: log format, which is logging configuration and not validator output. Nothing
#: about it reaches a `.results.json`.
STATS_DROPPED = (
    "-stats is deliberately not implemented. Upstream logs per-file and per-rule wall clock "
    "through slf4j; those numbers describe the machine the jar ran on and none of them reaches "
    "a .results.json. Note that -stats false still means -stats, which is upstream's own bug "
    "and is reproduced here. Re-run without it."
)


class MissingArgument(UsageError):
    """commons-cli's `MissingArgumentException`, with its message."""


class UnrecognizedOption(UsageError):
    """commons-cli's `UnrecognizedOptionException`, with its message."""


@dataclass(frozen=True, slots=True)
class CompatArgs:
    """What `main` reads back out of the parse, in the order it reads it.

    `stats` and `ignore_shapes` are booleans because upstream reads them as
    booleans; whatever value was typed is gone by this point, exactly as it is
    gone by the time `BatchProcessor.Builder` sees it.
    """

    gtfs: str | None = None
    gtfs_realtime_path: str | None = None
    sort: str | None = None
    plain_text: str | None = None
    stats: bool = False
    ignore_shapes: bool = False


def check_dropped(args: CompatArgs) -> None:
    """Refuse the two flags this project does not implement, in declaration order.

    Called after the missing-input check, because `main` reads `-gtfs` and
    `-gtfsRealtimePath` before it reads either of these and throws first.
    """
    if args.plain_text is not None:
        raise UsageError(PLAIN_TEXT_DROPPED)
    if args.stats:
        raise UsageError(STATS_DROPPED)


def _option_name(token: str) -> str | None:
    """The option a token names, or None if it names none of the six."""
    if not token.startswith("-") or len(token) == 1:
        return None
    name = token[1:]
    return name if name in OPTIONS else None


def parse(argv: Sequence[str]) -> CompatArgs:
    """`DefaultParser.parse` over the six, then `main`'s six getters.

    Raises `MissingArgument` for a flag whose value never arrived and
    `UnrecognizedOption` for a hyphenated token that names no option and is not
    standing in as one's value. A token with no hyphen is collected into the
    argument list and ignored, which is what `handleUnknownToken` does with it.
    """
    values: dict[str, str] = {}
    present: set[str] = set()
    pending: str | None = None
    for token in argv:
        name = _option_name(token)
        if name is not None:
            if pending is not None:
                raise MissingArgument(f"Missing argument for option: {pending}")
            present.add(name)
            pending = name
            continue
        if pending is not None:
            values.setdefault(pending, token)
            pending = None
            continue
        if token.startswith("-") and len(token) > 1:
            raise UnrecognizedOption(f"Unrecognized option: {token}")
    if pending is not None:
        raise MissingArgument(f"Missing argument for option: {pending}")
    return CompatArgs(
        gtfs=values.get("gtfs"),
        gtfs_realtime_path=values.get("gtfsRealtimePath"),
        sort=values.get("sort"),
        plain_text=values.get("plainText"),
        stats="stats" in present,
        ignore_shapes="ignoreShapes" in present,
    )
