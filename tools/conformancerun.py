"""Run one conformance group, on either side, with the shapes mode it declares.

`tools/run_jar.py` is still what stages inputs and stamps their mtimes, and
`tools/resultsdiff.py` is still what compares two sides' bytes. What is here is
the one thing neither of them takes: `-ignoreShapes`, which is a property of the
whole invocation rather than of a corpus directory, and which one of the four
groups needs.

**Upstream declares that flag with `hasArg()` and reads it with `hasOption()`**
(`Main.java:101` and `:219` at the pin), so the value is required on the command
line and then ignored: `-ignoreShapes false` **enables** it and a bare
`-ignoreShapes` is a parse error, not a default. `IGNORED_VALUE` below is the
argument upstream throws away, spelled `false` precisely because it is the value
that reads as "off" and is not.

Both sides get the committed archive the group asks for, unmodified. Two of the
four carry `trips.txt` cells the canonical static schema will not type, which
used to mean staging a patched copy; compat reads its static feed as
onebusaway's `GtfsReader` does now, so both sides see the bytes on disk.
"""

from __future__ import annotations

import subprocess
import sys
from collections.abc import Mapping
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tools"))

import jarenv  # noqa: E402
import run_jar  # noqa: E402
from conformancefeeds import Group  # noqa: E402

from gtfs_rt_validator import api  # noqa: E402
from gtfs_rt_validator.report.compat import RESULTS_SUFFIX, ResultsWriter  # noqa: E402
from gtfs_rt_validator.runner import Mode, SortBy  # noqa: E402

#: The argument upstream parses and discards. See the module docstring.
IGNORED_VALUE = "false"


def archive(group: Group) -> Path:
    """Where the group's static feed is committed."""
    return jarenv.GTFS_FIXTURES / group.gtfs


def jar_command(directory: Path, gtfs: Path, *, ignore_shapes: bool) -> list[str]:
    """`run_jar.invoke`'s command line, plus the flag it has no argument for."""
    command = [
        # `checked_java_17` rather than `java_17`: the release and the FORMAT
        # locale are properties of the JVM the jar runs in, and this path
        # generates the conformance goldens as well as comparing against them.
        str(jarenv.checked_java_17()[0]),
        "-jar",
        str(jarenv.JAR),
        "-gtfs",
        str(gtfs),
        "-gtfsRealtimePath",
        str(directory),
    ]
    if ignore_shapes:
        command += ["-ignoreShapes", IGNORED_VALUE]
    return command


def jar_side(
    inputs: Mapping[str, bytes], gtfs: Path, directory: Path, *, ignore_shapes: bool = False
) -> dict[str, bytes | None]:
    """Upstream's jar over these staged bytes, keyed by input name.

    `None` for an input that got no results file, so absence compares as
    absence rather than as a missing key.
    """

    run_jar.stage(inputs, directory)
    if not jarenv.JAR.exists():
        raise FileNotFoundError(f"no jar at {jarenv.JAR}; run tools/build_jar.py")
    done = subprocess.run(
        jar_command(directory, gtfs, ignore_shapes=ignore_shapes),
        capture_output=True,
        text=True,
        check=False,
        timeout=run_jar.RUN_TIMEOUT,
    )
    if done.returncode != 0:
        raise RuntimeError(f"jar exited {done.returncode}:\n{done.stderr[-4000:]}")
    collected = run_jar.collect(directory, list(inputs))
    return {name: collected.results.get(name) for name in inputs}


def compat_side(
    inputs: Mapping[str, bytes], gtfs: Path, directory: Path, *, ignore_shapes: bool = False
) -> dict[str, bytes | None]:
    """This project under `--compat`, over the same staged bytes and mtimes."""
    run_jar.stage(inputs, directory)
    writer = ResultsWriter()
    request = api.Request(
        mode=Mode.COMPAT,
        gtfs=gtfs,
        inputs=api.resolve_walk(str(directory), SortBy.DATE_MODIFIED),
        sort_by=SortBy.DATE_MODIFIED,
        ignore_shapes=ignore_shapes,
    )
    api.validate(request, sink=writer)
    written = {path.name: path.read_bytes() for path in writer.written}
    side: dict[str, bytes | None] = {
        name: written.pop(f"{name}{RESULTS_SUFFIX}", None) for name in inputs
    }
    # Anything left is a results file for something nobody staged: it has no
    # counterpart on the jar's side, so it is reported rather than dropped.
    side.update(written)
    return side
