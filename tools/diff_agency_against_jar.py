"""Differential: `--compat` against the jar over the *recorded agency* corpus.

`tools/diff_compat_against_jar.py` compares the two implementations over eight
crafted fixtures. Every one of those was written to make a particular rule fire,
which means every one of them is a shape somebody already thought of. This runs
the same comparison over `tests/fixtures/agencies/manifest.json`: four real
agencies, six rounds each, recorded off their live endpoints.

**The comparison is not reimplemented here.** `diff_compat_against_jar.jar_side`,
`.compat_side` and `resultsdiff.compare` do all of it, so there is exactly one
thing to trust and one place a tolerance could ever be introduced. This module
only decides what bytes go in, under what names, in what order, and against which
archive.

## What a round is, and where the clock comes from

`tools/agencycorpus.py` owns the corpus: it verifies every file against the
manifest's SHA-256 and stages each message under a name whose last twenty
characters encode its own `header.timestamp`. Those names are the point.
Upstream's `-sort name` switches the validation clock from the file's mtime to
`TimestampUtils.getTimestampFromFileName` (`BatchProcessor.java:220-232`), so a
run under `--sort name` validates every recorded message at the instant its
producer stamped it. That is the default here, and it is the first time this
repository has compared the file-name clock in `runner/clock.py` against a
running JVM: every committed golden was generated with no `-sort` at all.

`--sort date` is the other regime, and it is the goldens'. `run_jar.plan` stamps
mtimes one second apart from a fixed base in 2023, so a 2026 recording read
under that clock is uniformly "in the future" and E050 fires on most of the
feed. Both regimes were measured and both agree; the flag exists so the second
one can be re-run rather than described.

Files are staged round-major with the roles in `-tu -vp -sa` order, which is the
order a deployment polls them in. It matters: `BatchProcessor` keeps one
`prevMessage` across the whole directory regardless of role (`:188`, `:296`), so
E017, E018 and W007 read "previous" as "the file before this one in the sort",
not "the previous message of this role". Both sides are staged by the same
`run_jar.stage` call, so whatever that order implies, it implies for both.

## The MBTA does not get validated by the jar at all

Measured, and the headline result of this comparison. `mdb-437`'s archive
carries a current-spec `areas.txt` whose columns are `area_id,area_name`. The
onebusaway version the jar bundles, `onebusaway-gtfs-1.3.87`, models that file as
`org.onebusaway.gtfs.model.Area`, and `javap -v` on that class shows the `wkt`
field carrying no `@CsvField` annotation at all, which is csv-entities' required
default. So `GtfsReader.run` throws `MissingRequiredFieldException` at line 2 of
that file, wrapped in `CsvEntityIOException`, `BatchProcessor.readGtfsData:314`
does not catch it, `Main.main:62` catches only
`IOException | NoSuchAlgorithmException`, and the JVM exits 1 having written no
`.results.json` for any input.

This project's compat static loader reads seven tables and never opens
`areas.txt`, so it validates all eighteen MBTA messages and writes 3.5 MB of
results the jar wrote nothing for. That is a real parity gap and it is reported
as one: `run_one` turns the jar's non-zero exit into a `jar-aborted` divergence
rather than letting the exception end the run, so the report says what happened
instead of the tool dying.

`Area` is read by nothing in the validator lib (`grep -rn "model.Area"` over
`gtfs-realtime-validator-lib/src/main/java` is empty), so the file is parsed only
because `GtfsReader` parses every file it has a model for. Which is why
`--drop-static-file areas.txt` exists: with that one entry removed the jar reads
the archive in about four seconds and validates it normally, and the eighteen
messages compare byte-for-byte over 13,177 occurrences under `--sort name` and
22,169 under `--sort date`. That is a **diagnostic**, not a parity result, and
the report says so on its own line. It is the only way to reach the
6,000-entity rule surface while the gap above is open.

## A green run here is narrower evidence than its size suggests

Which of this project's hard reproductions this corpus reaches is what decides
what a clean run means, so it is worth naming.
`String.format("%.2f")` and `_shared/javafmt.py` are exercised and agree, but
the JDK 17 versus JDK 19 `Float.toString` difference is not reached (of 4,410
distinct float32 position values here, exactly one renders differently from the
shortest round-trip, and it is the exponent form `1.0E-6`), `_shared/javahash.py`
is not reached at the byte level, and `report/jackson.py`'s upper-case escapes
are not reached at all: no results file from any run holds a single `\\uXXXX`
escape or a single byte above 127.

Run:
    .venv/bin/python tools/diff_agency_against_jar.py
    .venv/bin/python tools/diff_agency_against_jar.py --agency mdb-437
    .venv/bin/python tools/diff_agency_against_jar.py --sort date
    .venv/bin/python tools/diff_agency_against_jar.py --agency mdb-437 \\
        --drop-static-file areas.txt
"""

from __future__ import annotations

import argparse
import hashlib
import sys
import tempfile
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tools"))

import agencycorpus  # noqa: E402
import diff_compat_against_jar as diff  # noqa: E402
from agencycorpus import CorpusMissing  # noqa: E402
from resultsdiff import Divergence, Report, compare  # noqa: E402

from gtfs_rt_validator.runner import SortBy  # noqa: E402

#: `--sort` on the command line to this project's enum. Named after upstream's
#: own option values so the flag reads the same as the jar's.
SORTS = {"name": SortBy.NAME, "date": SortBy.DATE_MODIFIED}

#: The default. See the module docstring: it is the clock the recorded names
#: carry, and the regime no committed golden covers.
DEFAULT_SORT = "name"


@dataclass(frozen=True)
class AgencyResult:
    """One agency's comparison, and enough provenance to reproduce it."""

    mdb_id: str
    agency_name: str
    report: Report
    messages: int
    static_sha256: str
    dropped: tuple[str, ...]

    @property
    def exit_code(self) -> int:
        return self.report.exit_code

    def render(self) -> str:
        head = [
            f"=== {self.mdb_id} ({self.agency_name}): {self.messages} recorded messages",
            f"  static archive sha256 {self.static_sha256[:12]}",
        ]
        if self.dropped:
            head += [
                f"  DIAGNOSTIC RUN: the static archive was rebuilt without {list(self.dropped)},",
                "  so this is not a parity result for the recorded corpus. It says only that the",
                "  two implementations agree on the realtime feeds once the jar can read the",
                "  archive at all. See this module's docstring.",
            ]
        return "\n".join([*head, self.report.render()])


def agency(mdb_id: str) -> dict[str, Any]:
    for entry in agencycorpus.manifest()["agencies"]:
        if entry["static_mdb_id"] == mdb_id:
            return entry
    raise CorpusMissing(f"{mdb_id} is not in {agencycorpus.MANIFEST}")


def agency_ids() -> list[str]:
    return [entry["static_mdb_id"] for entry in agencycorpus.manifest()["agencies"]]


def inputs_for(entry: dict[str, Any]) -> dict[str, bytes]:
    """Every recorded message, verified, round-major, clock in the name.

    The names are `agencycorpus.staged_name`'s rather than this module's, so the
    file-name clock a `--sort name` run reads is the same one
    `tools/tier_counts.py` runs modern mode against. Two harnesses disagreeing
    about what instant a message was validated at would make their findings
    incomparable.
    """
    roles = agencycorpus.roles_of(entry)
    if not roles:
        raise CorpusMissing(f"{entry['static_mdb_id']} has no role present in every round")
    inputs: dict[str, bytes] = {}
    for record in entry["rounds"]:
        for role in roles:
            blob = agencycorpus.verified_bytes(record["files"][role])
            stamp = agencycorpus.header_timestamp(blob)
            inputs[agencycorpus.staged_name(role, record["round"], stamp)] = blob
    return inputs


def static_for(entry: dict[str, Any], workdir: Path, dropped: tuple[str, ...]) -> tuple[Path, str]:
    """The agency's archive and its sha256, rebuilt only if entries were dropped.

    With nothing dropped this hands back the recorded path itself, already
    verified against the manifest, so the ordinary run cannot be reading a copy
    of anything.
    """
    recorded = ROOT / entry["static"]["path"]
    agencycorpus.verified_bytes(entry["static"])
    if not dropped:
        return recorded, entry["static"]["sha256"]
    rebuilt = workdir / "static-without-dropped.zip"
    with zipfile.ZipFile(recorded) as source, zipfile.ZipFile(rebuilt, "w") as out:
        missing = set(dropped) - set(source.namelist())
        if missing:
            raise CorpusMissing(f"{sorted(missing)} is not in {entry['static']['path']}")
        for info in source.infolist():
            if info.filename not in dropped:
                # The source's own `ZipInfo`, not a fresh one. `writestr` with a
                # bare name stamps the archive with the wall clock, which would
                # give the rebuilt file a different sha256 on every run and make
                # the digest printed below evidence of nothing.
                out.writestr(info, source.read(info.filename))
    return rebuilt, hashlib.sha256(rebuilt.read_bytes()).hexdigest()


def run_one(
    entry: dict[str, Any], workdir: Path, sort_by: SortBy, dropped: tuple[str, ...]
) -> AgencyResult:
    """Both sides over one agency, with a jar that dies reported rather than raised.

    A non-zero exit from the jar is not an accident of this harness and must not
    end the run: for `mdb-437` it is the finding. `run_jar.invoke` raises on it,
    so it is caught here, this project's side is run on its own, and the two are
    compared with the jar credited with the nothing it wrote. The extra
    `jar-aborted` divergence carries the stack trace, because "the jar wrote no
    results file" and "the jar never reached its file loop" are different facts
    and only one of them is a rule disagreeing.
    """
    inputs = inputs_for(entry)
    archive, archive_sha = static_for(entry, workdir, dropped)
    try:
        report = diff.differential(inputs, workdir / "both", archive, sort_by)
    except RuntimeError as died:
        alone = workdir / "ours-alone"
        alone.mkdir(parents=True)
        ours = diff.compat_side(inputs, archive, alone, sort_by)
        jars: dict[str, bytes | None] = dict.fromkeys(inputs)
        aborted = Divergence(
            "<the jar>",
            "jar-aborted",
            "the jar exited non-zero before validating anything, so it wrote no results "
            f"file for any of the {len(inputs)} inputs:\n{died}",
        )
        report = Report(
            ours=ours,
            jars=jars,
            divergences=[aborted, *compare(ours, jars)],
            environment=diff.environment(),
            our_directory=alone,
        )
    return AgencyResult(
        mdb_id=entry["static_mdb_id"],
        agency_name=entry["agency_name"],
        report=report,
        messages=len(inputs),
        static_sha256=archive_sha,
        dropped=dropped,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--agency", action="append", help="an mdb id; repeatable, default all")
    parser.add_argument("--sort", choices=sorted(SORTS), default=DEFAULT_SORT)
    parser.add_argument(
        "--drop-static-file",
        action="append",
        default=[],
        metavar="NAME",
        help="rebuild the archive without this entry. Diagnostic, not a parity run.",
    )
    args = parser.parse_args(argv)

    try:
        wanted = args.agency or agency_ids()
        entries = [agency(mdb_id) for mdb_id in wanted]
    except (CorpusMissing, FileNotFoundError) as absent:
        print(f"the recorded agency corpus is not available: {absent}", file=sys.stderr)
        return 2

    dropped = tuple(args.drop_static_file)
    worst = 0
    for entry in entries:
        with tempfile.TemporaryDirectory(prefix="gtfs-rt-agency-") as workdir:
            try:
                result = run_one(entry, Path(workdir), SORTS[args.sort], dropped)
            except CorpusMissing as absent:
                print(f"{entry['static_mdb_id']}: {absent}", file=sys.stderr)
                return 2
            print(result.render())
            worst = max(worst, result.exit_code)
    return worst


if __name__ == "__main__":
    sys.exit(main())
