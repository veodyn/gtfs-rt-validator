"""Generate `tests/fixtures/agencies/jar-goldens.json` from a real jar run.

The recording rule for this tier is that the bytes stay gitignored under
`corpus/` while the manifest and the jar's goldens are committed. The manifest
shipped and the
goldens did not, so until this existed nothing in a checkout could detect drift
against the jar on the recorded tier: `tests/test_agency_differential.py`
re-derives the jar's side live and needs a built jar, a JDK 17 and the recorded
bytes to do it. This takes the jar and the JDK out of that loop. It does not take
the bytes out: they are what this project's side is recomputed from, and
`tools/fetch_corpus.py` fetches them against the manifest's SHA-256.

**The comparison is not reimplemented here.** `diff_agency_against_jar.run_one`
stages both sides, runs them and reports, exactly as it does for the live
differential; this module only reduces the jar's half of its report to digests
and writes them out. `tools/agencygoldens.py` owns that reduction, so the
checking side and the generating side cannot drift apart.

**Every regime, including the diagnostic one.** Four agencies under `--sort
name` and `--sort date` is eight runs, and for MBTA the jar writes nothing in
either: it refuses the archive before it reaches its file loop. Those two runs
therefore pin no jar bytes at all, which would leave the largest and most
interesting agency contributing nothing to a jarless check. So the two
`--drop-static-file areas.txt` runs are generated too. They are a **diagnostic
and not a parity result**, every record says so, and they are what pins the
13,177 and 22,169 occurrences of real jar output over MBTA's six-thousand-entity
surface that the refusal otherwise hides.

Run: .venv/bin/python tools/build_jar.py && \\
     .venv/bin/python tools/gen_agency_goldens.py
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

import agencygoldens
import diff_agency_against_jar as tool
import diff_compat_against_jar as diff
import jarenv
from agencycorpus import MANIFEST, ROOT, CorpusMissing, manifest
from agencygoldens import GENERATOR, GOLDEN, REGENERATE
from resultsdiff import Environment, Report

from gtfs_rt_validator.version import VERSION

#: Which entries an agency's archive is rebuilt without for its diagnostic run.
#: Declared rather than discovered: dropping a file changes what the jar reads,
#: so which file is dropped is a decision a human makes once and records, not
#: something a generator should search for. `main` refuses to write a golden for
#: an agency the jar refused and that has no entry here.
DIAGNOSTIC_DROPS: dict[str, tuple[str, ...]] = {"mdb-437": ("areas.txt",)}

DIAGNOSTIC_NOTE = (
    "the static archive was rebuilt without the listed entries, so this is not a parity "
    "result for the recorded corpus. It says only that the two implementations agree on "
    "the realtime feeds once the jar can read the archive at all."
)

REFUSAL_NOTE = (
    "the jar did not skip these inputs, it never reached them. GtfsReader.run parses every "
    "file it has a model for, onebusaway-gtfs-1.3.87 models areas.txt as "
    "org.onebusaway.gtfs.model.Area whose wkt field carries no @CsvField annotation, and "
    "csv-entities reads an unannotated field as required. The current spec's areas.txt has "
    "area_id and area_name and no geometry, so the read throws, Main.main:62 catches only "
    "IOException and NoSuchAlgorithmException, and the JVM exits having written nothing. "
    "Nothing in gtfs-realtime-validator-lib reads an Area, so the file it died on could not "
    "have changed a single occurrence. This project's compat static loader reads seven "
    "tables and never opens areas.txt, so it validates everything: that is a real parity "
    "gap and it is recorded here as an outcome rather than as an absence, so that a jar or "
    "an archive that does read this file fails loudly instead of looking like an improvement."
)

_EXIT = re.compile(r"jar exited (\d+)")
_THROWN = re.compile(r'Exception in thread "main" (\S+): ')
_ENTITY = re.compile(r"entityType=(\S+) path=(\S+) lineNumber=(\d+)")
_CAUSE = re.compile(r"Caused by: (\S+): missing required field: (\w+)")


def revision() -> str:
    """The commit this golden was taken at. Informational, never compared."""
    try:
        found = subprocess.run(
            ["git", "-C", str(ROOT), "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return "unknown"
    return found.stdout.strip()


def generated_at() -> str:
    return dt.datetime.now(tz=dt.UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _frames(trace: str) -> list[str]:
    """The `at ...` lines of one trace. Class, method and line number, no paths."""
    return [line.strip() for line in trace.splitlines() if line.strip().startswith("at ")]


def refusal_of(report: Report) -> dict[str, Any] | None:
    """The jar's refusal as structured facts, or None if it validated.

    Extracted rather than transcribed, and *not* the raw stderr: upstream logs
    the archive it is reading by absolute path, so committing the trace verbatim
    would put this machine's home directory in a fixture and make the generator
    non-idempotent across checkouts. The stack frames are kept because they are
    the evidence and they carry no paths.
    """
    aborted = next((one for one in report.divergences if one.kind == "jar-aborted"), None)
    if aborted is None:
        return None
    detail = aborted.detail
    entity = _ENTITY.search(detail)
    cause = _CAUSE.search(detail)
    thrown = _THROWN.search(detail)
    exit_code = _EXIT.search(detail)
    if not (entity and cause and thrown and exit_code):
        sys.exit(
            "the jar aborted in a way this generator cannot describe. Read the trace with\n"
            "  .venv/bin/python tools/diff_agency_against_jar.py --agency <id>\n"
            "and teach refusal_of about it rather than committing a golden that records an "
            f"unexplained abort as an absence:\n{detail}"
        )
    return {
        "exit_code": int(exit_code.group(1)),
        "results_files_written": 0,
        "exception": thrown.group(1),
        "entity_type": entity.group(1),
        "path": entity.group(2),
        "line_number": int(entity.group(3)),
        "caused_by": cause.group(1),
        "missing_field": cause.group(2),
        "frames": _frames(detail[: cause.start()]),
        "cause_frames": _frames(detail[cause.start() :]),
        "why": REFUSAL_NOTE,
    }


def run_record(
    entry: dict[str, Any], sort: str, dropped: tuple[str, ...]
) -> tuple[dict[str, Any], Environment | None]:
    """One agency under one regime: the jar's side reduced, and what it implies."""
    with tempfile.TemporaryDirectory(prefix="gtfs-rt-goldens-") as workdir:
        result = tool.run_one(entry, Path(workdir), tool.SORTS[sort], dropped)
        jars = agencygoldens.side(result.report.jars)
        # Computed from the same run, so the divergences recorded are the ones a
        # checkout will reproduce rather than ones this module predicted.
        expected = agencygoldens.compare(result.report.ours, jars)
        environment = result.report.environment
    written = sum(1 for one in jars.values() if one is not None)
    return {
        "static_mdb_id": result.mdb_id,
        "agency_name": result.agency_name,
        "sort": sort,
        "jar_sort_flag": diff.JAR_SORT[tool.SORTS[sort]],
        "dropped_static_files": list(dropped),
        "diagnostic": bool(dropped),
        "diagnostic_note": DIAGNOSTIC_NOTE if dropped else None,
        "static_sha256": result.static_sha256,
        "messages": result.messages,
        "jar_outcome": "validated" if written else "refused-the-archive",
        "jar_refusal": refusal_of(result.report),
        "jar_results_files": written,
        "jar_occurrences": sum(one["occurrences"] for one in jars.values() if one),
        "expected_divergences": [{"name": one.name, "kind": one.kind} for one in expected],
        "inputs": jars,
    }, environment


def payload(runs: list[dict[str, Any]], environment: Environment) -> dict[str, Any]:
    repo, _configured = jarenv.pin()
    corpus = manifest()
    return {
        "generated_by": GENERATOR,
        "do_not_edit": REGENERATE,
        "generated_at": generated_at(),
        "code_revision": revision(),
        "validator_version": VERSION,
        "what_this_is": (
            "the jar's side of tools/diff_agency_against_jar.py, reduced to a SHA-256, a "
            "byte length and a rule census per input. The results bytes themselves are not "
            "committed: MBTA alone is 3.5 MB of them per sort regime, and corpus/ is "
            "gitignored to keep this repository small. tests/test_agency_goldens.py "
            "recomputes this project's side from the recorded bytes and compares against "
            "this file, which needs neither a jar nor a JDK. "
            "tests/test_agency_differential.py is the stronger check against a running jar "
            "and this does not replace it."
        ),
        "jar": {
            "repo": repo,
            "pin": environment.pin,
            "pin_evidence": environment.pin_evidence,
            "sha256": environment.jar_sha256,
        },
        "jdk": {"java_version": environment.java_version, "format_locale": environment.locale},
        "corpus": {
            "manifest": str(MANIFEST.relative_to(ROOT)),
            "manifest_sha256": agencygoldens.digest(MANIFEST.read_bytes()),
            "recorded_at": corpus["recorded_at"],
        },
        "runs": runs,
    }


def regimes(corpus: dict[str, Any]) -> list[tuple[dict[str, Any], str, tuple[str, ...]]]:
    """Every (agency, sort, dropped) this golden covers, in a stable order."""
    plan: list[tuple[dict[str, Any], str, tuple[str, ...]]] = []
    for agency in corpus["agencies"]:
        for sort in sorted(tool.SORTS):
            plan.append((agency, sort, ()))
            dropped = DIAGNOSTIC_DROPS.get(agency["static_mdb_id"])
            if dropped:
                plan.append((agency, sort, dropped))
    return plan


def generate() -> dict[str, Any]:
    """Every regime, run against the jar, reduced to the committed shape.

    One `Environment` for the whole file rather than one per run: every run here
    starts the same jar under the same JVM, and recording it ten times would
    invite a reader to think two of them could differ.
    """
    corpus = manifest()
    produced = [run_record(agency, sort, dropped) for agency, sort, dropped in regimes(corpus)]
    runs = [run for run, _ in produced]
    for run in runs:
        if run["jar_outcome"] == "refused-the-archive" and not DIAGNOSTIC_DROPS.get(
            run["static_mdb_id"]
        ):
            sys.exit(
                f"the jar refused {run['static_mdb_id']}'s archive and DIAGNOSTIC_DROPS has no "
                "entry for it, so this golden would pin no jar bytes for that agency at all. "
                "Find which entry the jar died on and declare it."
            )
    return payload(runs, next(one for _, one in produced if one is not None))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.parse_args(argv)
    try:
        content = generate()
    except CorpusMissing as absent:
        print(f"the recorded agency corpus is not available: {absent}", file=sys.stderr)
        return 2
    text = json.dumps(content, indent=2) + "\n"
    if str(ROOT) in text:
        sys.exit("the golden holds this checkout's absolute path, which is not a committable fact")
    GOLDEN.write_text(text, encoding="utf-8")
    print(f"wrote {GOLDEN.relative_to(ROOT)} ({len(text)} bytes)")
    for run in content["runs"]:
        label = " ".join(f"--drop-static-file {name}" for name in run["dropped_static_files"])
        print(
            f"  {run['static_mdb_id']} --sort {run['sort']} {label}: "
            f"{run['jar_results_files']}/{run['messages']} results files, "
            f"{run['jar_occurrences']} occurrences, "
            f"{len(run['expected_divergences'])} expected divergences"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
