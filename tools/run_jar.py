"""Run upstream's jar over a corpus, always on an isolated copy.

Upstream walks the realtime directory with `Files.walk(...).filter(isRegularFile)`
and no extension filter, then writes each result to `<input>.results.json` beside
its input (`BatchProcessor.java:168` and `:321` at the pin). Those two facts
together mean a second run over the same directory feeds the first run's JSON
back in as if it were a protobuf, so the committed corpus must never be a run
directory. This module is the only thing that invokes the jar, and it copies into
a fresh temp directory every time. `plan()` refuses a name ending in
`.results.json` outright, so the trap cannot be reintroduced by a caller.

Two more `BatchProcessor` behaviours make the copy's *metadata* part of the
input, not just its bytes:

- files are sorted by last-modified time by default (`:171`), and that same
  time is the "current" clock every timestamp rule compares against (`:223`),
  so a run whose mtimes are whatever `cp` left behind is not reproducible;
- a file whose MD5 equals the previous file's is skipped without a result
  (`:215`), and the previous-message state carries across files (`:296`), so
  results depend on order and not only on content.

Every run therefore stamps mtimes explicitly, one second apart in the order the
caller gives.

Run: .venv/bin/python tools/run_jar.py tests/fixtures/jar
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path

from jarenv import CORPUS, GOLDEN_GTFS, JAR, RESULTS_SUFFIX, checked_java_17

# The first mtime stamped on a run directory. Fixed rather than "now" because
# upstream uses the file's mtime as the clock, so a moving base moves every
# W008 ("header timestamp is older than 65 seconds") string in the output.
MTIME_BASE = 1_700_000_000

# How long one jar invocation may take before it is killed.
#
# Not defensive: upstream has a measured infinite spin.
# `FrequencyTypeOneValidator`'s `while (startTime < f.getEndTime())` loop
# advances by `startTime += f.getHeadwaySecs()`, so an `exact_times = 1` row
# with `headway_secs = 0` never advances, and the loop is entered for any trip a
# realtime TripUpdate or VehiclePosition names. `jstack` on the live process
# names that frame after 12.1 seconds of burned CPU.
# It is a spin rather than a block, so nothing inside the JVM will end it and
# the bound has to be ours.
#
# 300 seconds is roughly 700x the measured wall clock of a full run over the
# committed corpus, which is under half a second end to end, so no legitimate
# run is at risk of hitting it.
RUN_TIMEOUT = 300.0


@dataclass
class RunResult:
    """What one jar invocation produced."""

    results: dict[str, bytes] = field(default_factory=dict)
    skipped: list[str] = field(default_factory=list)
    stderr: str = ""

    def summary(self) -> str:
        return f"{len(self.results)} results, {len(self.skipped)} skipped: {self.skipped}"


def plan(names: Sequence[str]) -> dict[str, int]:
    """Input name to the mtime it will be stamped with, in the given order.

    Rejects a name that would itself look like output. Copying a `.results.json`
    into a run directory is the one mistake that silently produces a plausible
    but meaningless comparison, so it is refused here rather than filtered
    quietly: a caller that hands one in has a bug worth seeing.
    """
    stamped = {}
    for index, name in enumerate(names):
        if name.endswith(RESULTS_SUFFIX):
            raise ValueError(
                f"{name!r} is jar output, not an input. Feeding results back in is the "
                "second-run trap; pass only the corpus inputs."
            )
        if "/" in name or name in stamped:
            raise ValueError(f"{name!r} is not a usable flat input name")
        stamped[name] = MTIME_BASE + index
    return stamped


def stage(inputs: Mapping[str, bytes], directory: Path) -> dict[str, int]:
    """Write the inputs into a directory and stamp their mtimes."""
    mtimes = plan(list(inputs))
    for name, blob in inputs.items():
        path = directory / name
        path.write_bytes(blob)
        os.utime(path, (mtimes[name], mtimes[name]))
    return mtimes


def invoke(
    directory: Path, gtfs: Path, timeout: float = RUN_TIMEOUT, sort: str | None = None
) -> str:
    """`java -jar <fat jar> -gtfs <zip> -gtfsRealtimePath <dir>`, as documented.

    `sort` is upstream's own `-sort` vocabulary, `"name"` or `"date"`, and `None`
    omits the flag. Omitting is not the same edit as passing `"date"` even though
    `Main.getSortBy:158-177` maps both to `DATE_MODIFIED`, because every
    committed golden was generated with no `-sort` at all; leaving the default at
    `None` keeps `tools/gen_golden.py` producing the same command line it always
    did. `"name"` is the switch that matters: it makes the clock
    `TimestampUtils.getTimestampFromFileName` rather than the mtime
    (`BatchProcessor.java:220-232`), which is the regime the recorded agency
    corpus is named for.

    Upstream returns 0 whether or not the feeds carry errors, and returns 0 even
    when it skips every file, so the exit code is not the signal; the presence of
    a `.results.json` is. A nonzero code means the jar itself failed and is worth
    raising on.

    The run is bounded. One spinning input would otherwise hang the differential
    for as long as the harness will wait, and a differential that never returns
    is worse than a red one: nobody reads it.

    The JVM is `checked_java_17`'s rather than `java_17`'s, so the release and
    the FORMAT locale are pinned at the point the jar is started rather than by
    whichever caller remembered to check. `tools/gen_golden.py` reaches this
    function too, and a golden generated under a comma-decimal FORMAT locale
    would be committed as the contract.
    """
    if not JAR.exists():
        raise FileNotFoundError(f"no jar at {JAR}; run .venv/bin/python tools/build_jar.py")
    if not gtfs.exists():
        raise FileNotFoundError(f"no GTFS zip at {gtfs}")
    command = [
        str(checked_java_17()[0]),
        "-jar",
        str(JAR),
        "-gtfs",
        str(gtfs),
        "-gtfsRealtimePath",
        str(directory),
    ]
    if sort is not None:
        command += ["-sort", sort]
    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            check=False,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as expired:
        raise RuntimeError(
            f"the jar timed out after {timeout} s over {directory} and was killed. "
            "A run this long is a spin, not slowness: an exact_times=1 frequency with "
            "headway_secs=0, named by a realtime entity, never leaves "
            "FrequencyTypeOneValidator's loop. Find the input that did it before raising "
            "RUN_TIMEOUT."
        ) from expired
    if result.returncode != 0:
        raise RuntimeError(f"jar exited {result.returncode}:\n{result.stderr[-4000:]}")
    return result.stderr


def collect(directory: Path, names: Sequence[str]) -> RunResult:
    """Read `<input>.results.json` back, recording which inputs got none."""
    run = RunResult()
    for name in names:
        produced = directory / (name + RESULTS_SUFFIX)
        if produced.exists():
            run.results[name] = produced.read_bytes()
        else:
            run.skipped.append(name)
    unexpected = {
        path.name
        for path in directory.iterdir()
        if path.name not in names and path.name[: -len(RESULTS_SUFFIX)] not in names
    }
    if unexpected:
        raise RuntimeError(f"the jar wrote files nobody asked for: {sorted(unexpected)}")
    return run


def run(inputs: Mapping[str, bytes], gtfs: Path = GOLDEN_GTFS) -> RunResult:
    """Validate `inputs` in the order given, in a throwaway directory.

    The temp directory is removed even when the jar raises, so a failed run
    cannot leave a half-written corpus behind for the next one to ingest.
    """
    directory = Path(tempfile.mkdtemp(prefix="gtfs-rt-jar-"))
    try:
        stage(inputs, directory)
        stderr = invoke(directory, gtfs)
        collected = collect(directory, list(inputs))
        collected.stderr = stderr
        return collected
    finally:
        shutil.rmtree(directory, ignore_errors=True)


def read_corpus(directory: Path) -> dict[str, bytes]:
    """A corpus directory's inputs, in sorted-name order, output files excluded.

    Sorted rather than as-listed: `os.listdir` order is the filesystem's, and the
    mtimes `plan` stamps decide both the sort and the clock, so a run that walked
    the directory in a different order would produce different output for the
    same bytes.
    """
    return {
        path.name: path.read_bytes()
        for path in sorted(directory.iterdir())
        if path.is_file() and not path.name.endswith(RESULTS_SUFFIX) and path.suffix != ".json"
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Run upstream's jar over a corpus directory.")
    parser.add_argument(
        "corpus", nargs="?", default=str(CORPUS), help="directory of .pb inputs (never modified)"
    )
    parser.add_argument("--gtfs", default=str(GOLDEN_GTFS), help="GTFS zip to validate against")
    args = parser.parse_args()

    inputs = read_corpus(Path(args.corpus))
    if not inputs:
        print(f"no inputs under {args.corpus}", file=sys.stderr)
        return 1
    outcome = run(inputs, Path(args.gtfs))
    for name in inputs:
        blob = outcome.results.get(name)
        if blob is None:
            print(f"{name}: skipped, no results file")
        else:
            print(f"{name}: {len(blob)} bytes")
            print(blob.decode("utf-8"))
    print(outcome.summary(), file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
