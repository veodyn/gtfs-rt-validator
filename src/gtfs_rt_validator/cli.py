"""The command line: two flag surfaces, one run underneath.

`api.py` is the thing; this maps argv onto it through `cliargs.py`, and maps
what comes back to an exit code. It is also the only module in this project
allowed to write to the terminal - everything else reports through a
`NoticeContainer` - which is why `ruff.toml` exempts exactly this file from
T201.

**Two surfaces, because there are two validators.** Modern's flags are this
project's own and live in `cliargs.py` with the exit-code table. `--compat`
hands the rest of argv to `compatcli.py`, which is upstream's surface including
the two commons-cli bugs it has to reproduce. Nothing of this project's own is
accepted there, because a wrapper script written against the jar has to work
against this and upstream would have refused the flag.

**The two modes part company at the writer, here.** Modern writes the sibling's
report shape under `--out`. Compat has no output directory at all: it writes one
`.results.json` beside each input as the run goes, through the sink
`report/compat.py` provides, which is where upstream writes it from too.
"""

from __future__ import annotations

import sys
from collections.abc import Sequence
from pathlib import Path

from gtfs_rt_validator import api, compatcli
from gtfs_rt_validator.api import Request, Result, UsageError
from gtfs_rt_validator.cliargs import (
    COMPAT_FLAG,
    EQUAL_MESSAGE_ABORT_FLAG,
    EXIT_FINDINGS,
    EXIT_OK,
    EXIT_RUNNER,
    EXIT_UPSTREAM_CRASH,
    EXIT_USAGE,
    build_parser,
    modern_request,
    reject_compat_only_flags,
    reject_upstream_spellings,
)
from gtfs_rt_validator.runner import CompatAbort, Mode, SortBy
from gtfs_rt_validator.static.adapter import StaticLoadError
from gtfs_rt_validator.version import VERSION

__all__ = [
    "EXIT_FINDINGS",
    "EXIT_OK",
    "EXIT_RUNNER",
    "EXIT_UPSTREAM_CRASH",
    "EXIT_USAGE",
    "main",
]


def _counted(result: Result) -> str:
    return (
        f"gtfs-rt-validator {VERSION}: validated {result.run.messages_validated} messages, "
        f"skipped {result.run.files_skipped}, in {result.validation_time_seconds}s"
    )


def _modern(argv: Sequence[str]) -> int:
    reject_upstream_spellings(argv)
    reject_compat_only_flags(argv)
    namespace = build_parser().parse_args(list(argv))
    result = api.validate(modern_request(namespace))
    written = result.write(Path(namespace.out))
    print(_counted(result))
    print(f"wrote {written.report}")
    print(f"wrote {written.system_errors}")
    if namespace.fail_on_error and result.has_errors():
        print(f"error-severity rules fired: {', '.join(result.error_ids())}", file=sys.stderr)
        return EXIT_FINDINGS
    return EXIT_OK


def _compat(argv: Sequence[str], *, abort_on_equal_message: bool = False) -> int:
    """Upstream's `main`, in its order: parse, check inputs, then run.

    The order is load-bearing. Every getter re-parses the whole argv and
    `getGtfsPathAndFileFromArgs` is the first call in `main`, so a commons-cli
    parse exception beats the `IllegalArgumentException` for a missing input,
    which in turn beats anything either dropped flag has to say.

    `abort_on_equal_message` arrives as a keyword rather than in `argv` because
    `main` has already stripped its flag: upstream's surface is six options and
    this project does not add a seventh to it.
    """
    parsed = compatcli.parse(argv)
    if parsed.gtfs is None or parsed.gtfs_realtime_path is None:
        raise UsageError(compatcli.MISSING_INPUTS)
    compatcli.check_dropped(parsed)
    sort_by = SortBy.from_cli(parsed.sort)
    try:
        inputs = api.resolve_walk(parsed.gtfs_realtime_path, sort_by)
    except OSError as unreadable:
        # `main` catches `IOException` around `processFeeds`, logs this line and
        # exits 0 having validated nothing.
        print(f"Error running batch processor: {unreadable}", file=sys.stderr)
        return EXIT_OK
    writer = api.ResultsWriter()
    try:
        result = api.validate(
            Request(
                mode=Mode.COMPAT,
                gtfs=Path(parsed.gtfs),
                inputs=inputs,
                sort_by=sort_by,
                ignore_shapes=parsed.ignore_shapes,
                abort_on_equal_message=abort_on_equal_message,
            ),
            sink=writer,
        )
    except OSError as unwritable:
        # The same catch as above, and it has to cover the write too.
        # `writeResults` raises `IOException` out of `processFeeds`, and
        # `Main.java:71-73` catches `IOException | NoSuchAlgorithmException`,
        # logs one line and returns normally, so the process exits 0. Leaving
        # this uncovered made an unwritable output directory a Python traceback
        # and a nonzero exit, which is a divergence on a path a read-only mount
        # or an existing directory named `one.pb.results.json` reaches.
        print(f"Error running batch processor: {unwritable}", file=sys.stderr)
        return EXIT_OK
    print(_counted(result))
    print(f"wrote {len(writer.written)} {api.RESULTS_SUFFIX} files")
    # Upstream returns 0 whether or not the feeds carry findings, and has no
    # flag to change that: `--fail-on-error` is this project's own and is
    # refused on this surface.
    return EXIT_OK


def main(argv: Sequence[str] | None = None) -> int:
    """One invocation. Returns the exit code rather than raising it, so a test
    reads it as a value and a console script still exits with it."""
    args = list(sys.argv[1:] if argv is None else argv)
    try:
        if COMPAT_FLAG in args:
            args.remove(COMPAT_FLAG)
            # Stripped here, like `--compat` itself and for the same reason:
            # `compatcli.parse` is commons-cli over upstream's six options, and a
            # seventh reaching it would be an `UnrecognizedOption`. See
            # `cliargs.EQUAL_MESSAGE_ABORT_FLAG` for why this project has a flag
            # upstream does not.
            equal_message_abort = EQUAL_MESSAGE_ABORT_FLAG in args
            if equal_message_abort:
                args.remove(EQUAL_MESSAGE_ABORT_FLAG)
            return _compat(args, abort_on_equal_message=equal_message_abort)
        return _modern(args)
    except UsageError as bad:
        print(bad, file=sys.stderr)
        return EXIT_USAGE
    except CompatAbort as died:
        print(died, file=sys.stderr)
        return EXIT_UPSTREAM_CRASH
    except StaticLoadError as failed:
        print(failed, file=sys.stderr)
        return EXIT_RUNNER
    except SystemExit as done:
        # argparse's `--help` and `--version` are actions, not errors.
        return int(done.code or EXIT_OK)


if __name__ == "__main__":
    raise SystemExit(main())
