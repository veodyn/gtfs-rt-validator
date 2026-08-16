"""Record a tier 2 corpus: real agency feeds, snapshotted rather than polled live.

Reads `tests/fixtures/agencies/picks.json`, which is committed and records how
the agencies were chosen, fetches each one's static archive once and
each realtime role it publishes several times, and writes a manifest pinning the
SHA-256 of every byte recorded.

**Snapshot, never live fetch.** A test that pulls a live endpoint is not
reproducible: the feed at that URL is different an hour later, so a differential
against it can go red for reasons that have nothing to do with this project. The
bytes land under `corpus/`, which is gitignored; the manifest is committed, so a
drift in our output still fails the build without carrying tens of megabytes in
git.

**The static archive is recorded in the same pass as the realtime files.** The
rules join them: E003 asks whether a realtime trip_id is in `trips.txt`, E029
asks whether a vehicle is near its shape. An agency that rolls its static feed
overnight silently invalidates every pairing recorded before it, so the archive's
own checksum goes in the manifest beside the realtime ones rather than only its
URL.

A sequence rather than a single message, because the cross-file rules are the
ones a crafted feed reproduces worst: E017 and E018 compare a header timestamp
against the previous file's, W007 measures the interval between them, and the
MD5 skip needs two files whose bytes are equal to exercise at all.

**Every role a pick declares, which is `-tu`, `-vp` and `-sa`.** Alerts were
missing from the first recording, and the cost was exact: sixteen rules that only
ever see an `Alert` counted zero over the corpus and could not be told apart from
sixteen rules a clean feed never trips. A role is recorded because a pick
declares it, so an agency publishing two of the three is still recorded.

**What a round is, and why it is not a poll, lives in `corpuspoll.py`.** That
module owns the cadence decision, which is the one thing about this recorder that
reaches the counts: P004 and W007 are about the producer's refresh rate, and a
recorder that keeps one message per poll records its own rate instead.

Runs nowhere in CI and is not imported by the package. It reads no environment
variable, and the only import beyond the standard library is this project's own
decoder, for the header timestamp.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any

from corpuspoll import (
    DISTINCT_MESSAGES,
    POLL_INTERVAL_SECONDS,
    fetch,
    gather,
    record,
    rounds_of,
)

ROOT = Path(__file__).resolve().parent.parent
PICKS = ROOT / "tests" / "fixtures" / "agencies" / "picks.json"
MANIFEST = ROOT / "tests" / "fixtures" / "agencies" / "manifest.json"
CORPUS = ROOT / "corpus" / "agencies"

ROUNDS_ARE = (
    "one distinct producer message per role, keyed on header.timestamp advancing, not one "
    "poll. Each agency's refresh block holds the intervals between them, which is the "
    "producer's cadence rather than this recorder's."
)


def snapshot(agency: dict[str, Any], wanted: int, interval: float) -> dict[str, Any]:
    """One agency: the static archive once, then the realtime sequence."""
    slug = agency["static_mdb_id"]
    out = CORPUS / slug
    # `total_voms` is the NTD fleet size the first three picks were spread over,
    # and a pick sourced from the Mobility Database rather than that survey has
    # none. Null rather than a guess, so nothing here sorts or prints one.
    fleet = f"{agency['total_voms']} vehicles" if agency["total_voms"] else "fleet size unrecorded"
    print(f"  {agency['agency_name']} ({fleet}, {slug})")
    static = record(out / "static.zip", fetch(agency["static_url"]))
    static["url"] = agency["static_url"]
    print(f"    static: {static['bytes']} bytes {static['sha256'][:12]}")
    gathered = gather(agency, out, wanted, interval)
    rounds = rounds_of(gathered["kept"])
    if len(rounds) < wanted:
        print(f"    only {len(rounds)} of {wanted} rounds: a role ran out of polls")
    return {
        "agency_name": agency["agency_name"],
        "state": agency["state"],
        "size_class": agency["size_class"],
        "total_voms": agency["total_voms"],
        "static_mdb_id": slug,
        "static": static,
        "license_urls": {
            kind: feed.get("license_url") for kind, feed in sorted(agency["realtime"].items())
        },
        "refresh": gathered["refresh"],
        "failures": gathered["failures"],
        "rounds": rounds,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--only", help="one static_mdb_id, instead of every pick")
    parser.add_argument("--rounds", type=int, default=DISTINCT_MESSAGES)
    parser.add_argument("--interval", type=float, default=POLL_INTERVAL_SECONDS)
    args = parser.parse_args()

    picks = json.loads(PICKS.read_text(encoding="utf-8"))
    agencies = picks["agencies"]
    if args.only:
        agencies = [a for a in agencies if a["static_mdb_id"] == args.only]
        if not agencies:
            sys.exit(f"no pick with static_mdb_id {args.only!r}")

    print(
        f"recording {len(agencies)} agencies, {args.rounds} distinct messages per role, "
        f"polled every {args.interval}s"
    )
    recorded = [snapshot(agency, args.rounds, args.interval) for agency in agencies]

    # `recorded_at` is stamped from the clock rather than passed in because the
    # manifest is a record of when these bytes were true, and nothing reads it
    # as an input. The differential pins mtimes separately, in run_jar.py.
    manifest = {
        "generated_by": "tools/fetch_corpus.py",
        "do_not_edit": "Regenerate with .venv/bin/python tools/fetch_corpus.py",
        "recorded_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "note": "Bytes live under corpus/ and are gitignored. This manifest is committed.",
        "rounds_are": ROUNDS_ARE,
        "poll_interval_seconds": args.interval,
        "agencies": recorded,
    }
    existing = json.loads(MANIFEST.read_text(encoding="utf-8")) if MANIFEST.exists() else None
    if existing and args.only:
        kept = [a for a in existing["agencies"] if a["static_mdb_id"] != args.only]
        manifest["agencies"] = sorted(kept + recorded, key=lambda a: -(a["total_voms"] or 0))
    MANIFEST.parent.mkdir(parents=True, exist_ok=True)
    MANIFEST.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {MANIFEST.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
