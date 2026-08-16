"""Generate `tests/fixtures/jar/` from the crafted feeds, using a real jar run.

The goldens are the output contract in committed form: what the jar wrote, byte
for byte, for inputs this repository owns. They are transcribed from nothing.
Upstream's README sample cannot be trusted (it shows `"messageId" : 0` for a
boxed `Integer` nothing sets, which Jackson writes as `null`), so the only
honest source is a run.

The jar and its checkout are gitignored; the `.pb` inputs, the `.results.json`
goldens, the manifest and the static feed are all small and committed, so a
machine with no JDK can still check the shape of what compat has to reproduce.

**Two corpora, one generator.** Without arguments this writes
`tests/fixtures/jar/`, the eight feeds that pin the output contract. With
`--conformance` it writes `tests/fixtures/conformance/`, tier 1, which is aimed
at rule coverage instead and is grouped because a group is one jar invocation.
The two manifests are shaped differently on purpose: the jar corpus's is a flat
`inputs` list and is pinned byte for byte by `tests/test_manifest_drift.py`, so
it is left exactly as it was.

Run: .venv/bin/python tools/build_jar.py && .venv/bin/python tools/gen_golden.py
     .venv/bin/python tools/gen_golden.py --conformance
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
import tempfile
from collections.abc import Sequence
from pathlib import Path

import conformancerun
import run_jar
from conformancefeeds import ARCHIVES, GROUPS, Group
from goldenfeeds import FEEDS
from jarenv import (
    CONFORMANCE,
    CONFORMANCE_MANIFEST,
    CORPUS,
    GOLDEN_GTFS,
    GTFS_FIXTURES,
    MANIFEST,
    RESULTS_SUFFIX,
    TEST_RESOURCES,
    pin,
)


def digest(blob: bytes) -> str:
    return hashlib.sha256(blob).hexdigest()


def ensure_archive(name: str) -> Path:
    """Copy one of upstream's GTFS archives out of the build tree if needed.

    They are Apache-2.0 test data and NOTICE already declares
    `tests/fixtures/gtfs/*.zip` as material taken from upstream rather than
    derived from it. Committing them is what lets the goldens be regenerated,
    and read, without the gitignored build tree.
    """
    committed = GTFS_FIXTURES / name
    if committed.exists():
        return committed
    source = TEST_RESOURCES / name
    if not source.exists():
        sys.exit(f"no {name} at {source}; run tools/build_jar.py first")
    GTFS_FIXTURES.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, committed)
    print(f"copied {source} -> {committed}")
    return committed


def ensure_static_feed() -> None:
    ensure_archive(GOLDEN_GTFS.name)


def rule_ids(blob: bytes) -> list[str]:
    """The errorIds a golden reports, in the order the jar wrote them."""
    return [entry["errorMessage"]["validationRule"]["errorId"] for entry in json.loads(blob)]


def sweep(keep: set[str]) -> None:
    """Delete corpus files no feed claims, so a renamed feed cannot leave a ghost."""
    for path in sorted(CORPUS.iterdir()):
        if path.is_file() and path.name not in keep:
            path.unlink()
            print(f"removed stale {path.name}")


def _input_record(feed, mtime: int, blob: bytes | None) -> dict:
    """One manifest row. Shared by both corpora, because both pin the same facts.

    The feed declares what the jar should do and the run says what it did.
    Recording only the run would make the manifest a description of whatever
    happened; disagreeing here means upstream's file loop moved.
    """
    if (blob is None) != (feed.skip is not None):
        sys.exit(
            f"{feed.name} declares skip={feed.skip!r} but the jar "
            f"{'skipped' if blob is None else 'produced results for'} it"
        )
    record = {
        "name": feed.name,
        "why": feed.why,
        "mtime": mtime,
        "sha256": digest(feed.blob),
        "skip": feed.skip,
        "results": None if blob is None else feed.name + RESULTS_SUFFIX,
    }
    if blob is not None:
        record["results_sha256"] = digest(blob)
        record["rules"] = rule_ids(blob)
    return record


def build(outcome: run_jar.RunResult, mtimes: dict[str, int]) -> dict:
    repo, commit = pin()
    records = [
        _input_record(feed, mtimes[feed.name], outcome.results.get(feed.name)) for feed in FEEDS
    ]
    return {
        "generated_by": "tools/gen_golden.py",
        "do_not_edit": "Regenerate with .venv/bin/python tools/gen_golden.py",
        "repo": repo,
        "pin": commit,
        "gtfs": GOLDEN_GTFS.name,
        "gtfs_sha256": digest(GOLDEN_GTFS.read_bytes()),
        "mtime_base": run_jar.MTIME_BASE,
        "inputs": records,
    }


def write(manifest: dict, inputs: dict[str, bytes], results: dict[str, bytes]) -> None:
    CORPUS.mkdir(parents=True, exist_ok=True)
    for name, blob in inputs.items():
        (CORPUS / name).write_bytes(blob)
    for name, blob in results.items():
        (CORPUS / (name + RESULTS_SUFFIX)).write_bytes(blob)
    sweep(set(inputs) | {name + RESULTS_SUFFIX for name in results} | {MANIFEST.name})
    # 2-space indent so a drift diff reads line by line, matching map_rules.py.
    MANIFEST.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")


def conformance_group(group: Group, destination: Path = CONFORMANCE) -> dict:
    """Run one group and write its subdirectory, returning its manifest section."""

    gtfs = ensure_archive(group.gtfs)
    inputs = {feed.name: feed.blob for feed in group.feeds}
    mtimes = run_jar.plan(list(inputs))
    directory = destination / group.name
    directory.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="gtfs-rt-conformance-") as workdir:
        # Never the committed directory: upstream writes its results beside each
        # input and walks every regular file, so a run there would leave a corpus
        # whose next run ingests its own output.
        run_directory = Path(workdir) / "run"
        run_directory.mkdir()
        results = conformancerun.jar_side(
            inputs, gtfs, run_directory, ignore_shapes=group.ignore_shapes
        )
    for name, blob in inputs.items():
        (directory / name).write_bytes(blob)
        produced = results[name]
        if produced is not None:
            (directory / (name + RESULTS_SUFFIX)).write_bytes(produced)
    keep = set(inputs) | {
        name + RESULTS_SUFFIX for name, blob in results.items() if blob is not None
    }
    for path in sorted(directory.iterdir()):
        if path.is_file() and path.name not in keep:
            path.unlink()
            print(f"removed stale {group.name}/{path.name}")
    return {
        "name": group.name,
        "why": group.why,
        "gtfs": group.gtfs,
        "gtfs_sha256": digest(gtfs.read_bytes()),
        "ignore_shapes": group.ignore_shapes,
        "inputs": [
            _input_record(feed, mtimes[feed.name], results[feed.name]) for feed in group.feeds
        ],
    }


def conformance_main(destination: Path = CONFORMANCE) -> int:
    """Regenerate the conformance corpus into `destination`.

    The destination is a parameter because the test that checks regenerating is
    a no-op must not *be* a regeneration of the committed corpus: this function
    overwrites inputs and goldens, deletes files no feed claims, removes whole
    group directories and rewrites the manifest, so a run that differed or
    failed partway would leave the working tree modified and the committed
    fixtures already gone. `--out` gives that test somewhere disposable to
    compare against instead.
    """
    repo, commit = pin()
    destination.mkdir(parents=True, exist_ok=True)
    sections = [conformance_group(group, destination) for group in GROUPS]
    manifest = {
        "generated_by": "tools/gen_golden.py --conformance",
        "do_not_edit": "Regenerate with .venv/bin/python tools/gen_golden.py --conformance",
        "repo": repo,
        "pin": commit,
        "mtime_base": run_jar.MTIME_BASE,
        "archives": list(ARCHIVES),
        "groups": sections,
    }
    for stale in sorted(destination.iterdir()):
        if stale.is_dir() and stale.name not in {group.name for group in GROUPS}:
            shutil.rmtree(stale)
            print(f"removed stale group {stale.name}")
    written = destination / CONFORMANCE_MANIFEST.name
    written.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {written}")
    seen: set[str] = set()
    for section in sections:
        for record in section["inputs"]:
            rules = record.get("rules")
            seen.update(rules or ())
            # An empty list and no list at all are different claims: the first is
            # a results file the jar wrote with nothing in it, the second is a
            # file it never wrote because it skipped the input.
            told = f"skipped ({record['skip']})" if rules is None else rules
            print(f"  {section['name']}/{record['name']}: {told}")
    print(f"{len(seen)} distinct rules across the corpus", file=sys.stderr)
    return 0


def main(argv: Sequence[str] = ()) -> int:
    """The jar corpus by default, the conformance corpus with `--conformance`.

    `argv` defaults to empty rather than to `sys.argv[1:]` so that calling
    `main()` from a test is the no-argument run and not whatever pytest was
    invoked with. `__main__` below passes the real command line.
    """
    parser = argparse.ArgumentParser(description="Generate a committed jar corpus.")
    parser.add_argument(
        "--conformance",
        action="store_true",
        help="generate tests/fixtures/conformance/ instead of tests/fixtures/jar/",
    )
    parser.add_argument(
        "--out",
        default=None,
        help="write the conformance corpus here instead of over the committed one",
    )
    args = parser.parse_args(argv)
    if args.conformance:
        return conformance_main(Path(args.out) if args.out else CONFORMANCE)
    if args.out:
        parser.error("--out is only meaningful with --conformance")

    ensure_static_feed()
    inputs = {feed.name: feed.blob for feed in FEEDS}
    # One run, not one per artefact: two runs of the same corpus should agree,
    # and generating from two of them would hide it when they do not.
    mtimes = run_jar.plan(list(inputs))
    outcome = run_jar.run(inputs, GOLDEN_GTFS)
    print(outcome.summary(), file=sys.stderr)
    manifest = build(outcome, mtimes)
    write(manifest, inputs, outcome.results)
    print(f"wrote {MANIFEST}")
    for record in manifest["inputs"]:
        if record["results"] is None:
            print(f"  {record['name']}: skipped ({record['why']})")
        else:
            print(f"  {record['name']}: {record['rules']}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
