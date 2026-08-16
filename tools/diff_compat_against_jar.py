"""Differential: this project's `--compat` output against a running jar.

`tests/test_compat_writer.py` compares what this project writes against five
`.results.json` files committed under `tests/fixtures/jar/`. That is a comparison
against a recording, and a recording cannot notice that the jar was rebuilt, that
the JDK moved, or that the corpus grew. This is the comparison against the jar
itself: one corpus, staged twice with the same names and the same mtimes,
validated once by `java -jar` and once by `gtfs_rt_validator`, then compared byte
for byte by `tools/resultsdiff.py`.

**The absence of a file is compared too.** A feed the jar skips, for a duplicate
MD5 or a decode failure, gets no output file at all, and that absence is part of
parity. Comparing only the files that exist would let this project write an empty
`[ ]` for a message upstream never read and still come back green.

**Never weaken a comparison to make it pass.** A red diff is the deliverable. An
earlier geometry differential in this repository compared vertex counts instead
of positions and a containment check failed open; both were caught by audit, and
both would have shipped as green. So there is no normalisation here, no
whitespace tolerance, no substring match, no file skipped for being awkward, and
no `except` that turns a mismatch into a pass.

## Four things this pins, three of them measured the hard way

**The mtimes**, because upstream reads a file's modification time as both the
validation clock and the sort key (`BatchProcessor.java:171` and `:223`).
`tools/run_jar.stage` stamps them one second apart in the order given and
`tests/fixtures/jar/manifest.json` records the result, so both sides here stage
through that one function rather than through a second corpus format.

**JDK 17 specifically.** `Float.toString` was rewritten in JDK 19 (JDK-4511638)
to emit the shortest round-tripping decimal, so goldens regenerated on 19 or
later differ in E026, E027, E028, E029 and W004 occurrence text, and neither
result is wrong. `jarenv.checked_java_17` refusing anything else is load
bearing, and it re-reads the JVM's own `java.version` rather than trusting the
lookup that found it.

**The FORMAT locale, which is not the default locale.**
`VehicleValidator.java:185` and `:229` call `String.format("%.2f", ...)` with no
`Locale`, and `Formatter` with no `Locale` reads
`Locale.getDefault(Locale.Category.FORMAT)`. That category has its own two
properties: `-Duser.language.format=de -Duser.country.format=DE` moves it while
leaving `user.language` and `user.country` at `en`/`US`. Reading only the base
pair therefore reports `locale en-US` for a run that is formatting in German,
which is measured, not hypothetical: the same jar over the same committed corpus
under those two flags writes

    ... is more than 1609.0 meters (1,00 mile(s)) outside ...

into `04-combined-feed.pb.results.json` where the golden has `1.00 mile(s)`.
`jarenv.format_locale` reads the `.format` pair first and falls back to the base
pair, which is the fallback Java itself applies. Neither rendering is wrong, and
this project writes a dot unconditionally, so a FORMAT locale that is not the
goldens' is refused up front rather than producing a red diff that reads like a
bug in E028. Note that `LANG` and `LC_ALL` do not reach `Locale.getDefault()` on
macOS, which is why the JVM is asked rather than the shell, and that
`JAVA_TOOL_OPTIONS` reaches both the probe and the jar, so the probe sees what
the jar will get.

**The jar's provenance, as far as it can be shown.** `jarenv.pin()` is
configuration: it names the commit a jar should come from and says nothing about
the artefact. `tools/jarattest.py` checks the checkout the jar sits inside and
`environment()` prints the evidence and the jar's own sha256 next to the SHA, so
a report never presents a pin nobody looked at as ground truth.

## Both sides get the committed archive, unmodified

`tests/fixtures/gtfs/testagency.zip` as it stands, which is the archive the
goldens were measured against. This used to hand both sides a copy whose two
lettered `direction_id` cells had been blanked, because compat read its static
feed through the sibling's strict typed path and that path refuses the original
outright. Compat now reads it as onebusaway's `GtfsReader` does, so the
workaround and `tools/loadablegtfs.py` with it are gone.

Run:
    .venv/bin/python tools/diff_compat_against_jar.py
    .venv/bin/python tools/diff_compat_against_jar.py tests/fixtures/jar
"""

from __future__ import annotations

import argparse
import sys
import tempfile
from collections.abc import Mapping
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tools"))

import jarattest  # noqa: E402
import jarenv  # noqa: E402
import run_jar  # noqa: E402
from resultsdiff import (  # noqa: E402,F401
    Divergence,
    Environment,
    Report,
    compare,
    first_difference,
)

from gtfs_rt_validator import api  # noqa: E402
from gtfs_rt_validator.report.compat import RESULTS_SUFFIX, ResultsWriter  # noqa: E402
from gtfs_rt_validator.runner import Mode, SortBy  # noqa: E402

#: Re-exported so a caller that has this module already has the pin. The
#: definitions live in `tools/jarenv.py` because every path that starts a JVM
#: has to apply them, not only this one.
GOLDEN_LOCALE = jarenv.GOLDEN_LOCALE
WrongLocaleError = jarenv.WrongLocaleError


def environment() -> Environment:
    """The JDK, locale and jar this comparison may run under, or raise.

    The pin is *attested* rather than restated: `jarenv.pin()` is what a jar
    should have been built from, and printing it as the run's provenance would
    label a jar built from some other commit with this project's SHA.
    `jarattest.attested_pin` returns the evidence alongside it and
    `Environment.describe` prints both.
    """
    _java, version, locale = jarenv.checked_java_17()
    pin, evidence = jarattest.attested_pin()
    return Environment(version, locale, jarenv.JAR, pin, evidence, jarattest.jar_digest())


#: This project's `SortBy` to the word upstream's own `-sort` option takes
#: (`Main.java:34` and `:158-177`). `DATE_MODIFIED` maps to `None` rather than
#: to `"date"` so that the default command line is byte-identical to the one
#: every committed golden was generated with; the two are the same run.
JAR_SORT: dict[SortBy, str | None] = {SortBy.DATE_MODIFIED: None, SortBy.NAME: "name"}


def compat_side(
    inputs: Mapping[str, bytes],
    gtfs: Path,
    directory: Path,
    sort_by: SortBy = SortBy.DATE_MODIFIED,
) -> dict[str, bytes | None]:
    """This project under `--compat`, over the same staged bytes and mtimes.

    Keyed by input name with `None` for a file that got no results, so it lines
    up with what `run_jar.collect` reports and absence compares as absence.
    """
    run_jar.stage(inputs, directory)
    writer = ResultsWriter()
    request = api.Request(
        mode=Mode.COMPAT,
        gtfs=gtfs,
        inputs=api.resolve_walk(str(directory), sort_by),
        sort_by=sort_by,
    )
    api.validate(request, sink=writer)
    written = {path.name: path.read_bytes() for path in writer.written}
    side: dict[str, bytes | None] = {
        name: written.pop(f"{name}{RESULTS_SUFFIX}", None) for name in inputs
    }
    # Anything left over is a results file for something nobody staged. It has no
    # counterpart on the jar's side, so `compare` reports it rather than this
    # dropping it quietly.
    side.update(written)
    return side


def jar_side(
    inputs: Mapping[str, bytes],
    gtfs: Path,
    directory: Path,
    sort_by: SortBy = SortBy.DATE_MODIFIED,
) -> dict[str, bytes | None]:
    """Upstream's jar over the same staged bytes, keyed the same way."""
    run_jar.stage(inputs, directory)
    run_jar.invoke(directory, gtfs, sort=JAR_SORT[sort_by])
    collected = run_jar.collect(directory, list(inputs))
    return {name: collected.results.get(name) for name in inputs}


def differential(
    inputs: Mapping[str, bytes],
    workdir: Path,
    gtfs: Path | None = None,
    sort_by: SortBy = SortBy.DATE_MODIFIED,
) -> Report:
    """Run both sides over `inputs` and compare. Each side gets its own directory.

    Two directories rather than one because both sides write
    `<input>.results.json` beside the input, and upstream walks every regular
    file with no extension filter, so one shared directory would make each run
    ingest the other's output. Neither is ever the committed corpus.
    """
    recorded = environment()
    workdir.mkdir(parents=True, exist_ok=True)
    archive = gtfs or jarenv.GOLDEN_GTFS
    jar_directory, our_directory = workdir / "jar", workdir / "ours"
    jar_directory.mkdir()
    our_directory.mkdir()

    jars = jar_side(inputs, archive, jar_directory, sort_by)
    ours = compat_side(inputs, archive, our_directory, sort_by)
    return Report(
        ours=ours,
        jars=jars,
        divergences=compare(ours, jars),
        environment=recorded,
        jar_directory=jar_directory,
        our_directory=our_directory,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Compare --compat output against upstream's jar.")
    parser.add_argument(
        "corpus", nargs="?", default=str(jarenv.CORPUS), help="directory of inputs, never modified"
    )
    parser.add_argument("--gtfs", default=None, help="GTFS zip both sides validate against")
    args = parser.parse_args(argv)

    inputs = run_jar.read_corpus(Path(args.corpus))
    if not inputs:
        print(f"no inputs under {args.corpus}", file=sys.stderr)
        return 1
    with tempfile.TemporaryDirectory(prefix="gtfs-rt-diff-") as workdir:
        gtfs = Path(args.gtfs) if args.gtfs else None
        report = differential(inputs, Path(workdir), gtfs)
    print(report.render())
    return report.exit_code


if __name__ == "__main__":
    sys.exit(main())
