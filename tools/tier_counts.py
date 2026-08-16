"""How often every `spec` and `practice` rule fires on a real agency's feed.

Runs modern mode over the recorded agency corpus and writes one file per cited
tier, `spec-tier-counts.json` and `practice-tier-counts.json` under
`tests/fixtures/agencies/`, in the same shape so the two read side by side.

**The file is not the deliverable; the reading of it is.** A crafted fixture can
only show that a rule fires on the shape it was written for. A count over 782
real TripUpdates is the only thing that shows a rule firing on a third of a live
feed, which is the signal that a rule is wrong rather than that a feed is.

**Each message is validated at the instant its own producer stamped it**, which
`agencycorpus.py` arranges and explains. Several of these rules read the run's
clock: P005 measures a VehiclePosition's age against it, P008 asks whether any
prediction is still ahead of it, S049 turns it into a service date. Wall-clock
"now" would make the file unreproducible, and one fixed instant for the whole
recording would be wrong by the recording's own span: a round is one distinct
producer message per role, so an agency's recording spans as long as its slowest
role takes to publish six of them, which for MBTA's Alerts feed at 60 seconds
apart is five minutes. P005's threshold is 90 seconds, so a single clock would
report a fleet as stale purely for having been recorded first.

Standard library plus this project, like every other tool here, and it reads no
environment variable. Runs nowhere in CI: the bytes it needs are gitignored.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

from agencycorpus import (
    FIXTURES,
    MANIFEST,
    ROLES,
    ROOT,
    CorpusMissing,
    manifest,
    stage,
)

from gtfs_rt_validator import api
from gtfs_rt_validator.inputs import Inputs
from gtfs_rt_validator.report.occurrence import ENTITY_PATH_KEY
from gtfs_rt_validator.rules.registry import CITED_TIERS, Registry
from gtfs_rt_validator.runner import MessageResult, Mode, SortBy
from gtfs_rt_validator.version import VERSION

PINS = ROOT / "upstream" / "pins.json"
GENERATOR = "tools/tier_counts.py"
REGENERATE = f"Regenerate with .venv/bin/python {GENERATOR}"

#: What identifies the thing an occurrence is about, most specific first. A rule
#: that fires 685 times on 685 trips and one that fires 685 times on 132 trips
#: are different findings, and only this distinction tells them apart.
ENTITY_KEYS = ("tripId", "vehicleId", "routeId")

#: The fallback, and every row says which of the two it used. An occurrence that
#: names no id can only be identified by where it was found, and an entity index
#: is not stable between messages, so `distinct_entities` degenerates to
#: `occurrences` for such a rule. Stating the key is what stops a reader taking
#: that equality for a finding about the feed.
PATH_IDENTITY = "entityPath"


def tier_path(tier: str) -> Path:
    return FIXTURES / f"{tier}-tier-counts.json"


def subject(context: dict[str, Any]) -> tuple[str, str]:
    """(which key identified this occurrence, the identity it gives)."""
    for key in ENTITY_KEYS:
        value = context.get(key)
        if value is not None:
            return key, f"{key}={value}"
    path = f"{context.get(ENTITY_PATH_KEY)}@{context.get('sourceFile')}"
    return PATH_IDENTITY, f"{ENTITY_PATH_KEY}={path}"


class Tally:
    """Per rule: how many, over how many messages, over how many entities.

    `count_for` rather than the retained occurrences, because the container's
    caps are a presentation limit and the count is the true one. `dropped` is
    carried so a reader can tell whether `distinct_entities`, which can only be
    computed from what was retained, is complete or a sample.
    """

    def __init__(self) -> None:
        self.occurrences: dict[str, int] = {}
        self.messages: dict[str, int] = {}
        self.dropped: dict[str, int] = {}
        self.by_role: dict[str, dict[str, int]] = {}
        self.entities: dict[str, set[str]] = {}
        self.identity: dict[str, set[str]] = {}

    def observe(self, result: MessageResult) -> None:
        grouped = result.notices.grouped()
        for rule_id in result.notices.rule_ids():
            count = result.notices.count_for(rule_id)
            dropped = result.notices.dropped_for(rule_id)
            self.occurrences[rule_id] = self.occurrences.get(rule_id, 0) + count
            self.messages[rule_id] = self.messages.get(rule_id, 0) + 1
            self.dropped[rule_id] = self.dropped.get(rule_id, 0) + dropped
            roles = self.by_role.setdefault(rule_id, {})
            roles[result.source.role] = roles.get(result.source.role, 0) + count
            found = self.entities.setdefault(rule_id, set())
            keys = self.identity.setdefault(rule_id, set())
            for one in grouped.get(rule_id, []):
                key, identity = subject(one.context)
                keys.add(key)
                found.add(identity)

    def row(self, rule_id: str) -> dict[str, Any]:
        roles = self.by_role.get(rule_id, {})
        return {
            "occurrences": self.occurrences.get(rule_id, 0),
            "messages": self.messages.get(rule_id, 0),
            "distinct_entities": len(self.entities.get(rule_id, ())),
            "identified_by": sorted(self.identity.get(rule_id, ())),
            "dropped": self.dropped.get(rule_id, 0),
            "by_role": {role: roles[role] for role in ROLES if roles.get(role)},
        }


def run_agency(agency: dict[str, Any]) -> tuple[dict[str, Any], Tally]:
    """One modern run over one agency's whole recording, in round order."""
    tally = Tally()
    with tempfile.TemporaryDirectory(prefix="tier-counts-") as scratch:
        staged = stage(agency, Path(scratch))
        result = api.validate(
            api.Request(
                mode=Mode.MODERN,
                gtfs=staged.archive,
                inputs=Inputs(staged.cycles, directory_replay=True),
                sort_by=SortBy.NAME,
            ),
            sink=tally.observe,
        )
    return {
        "static_mdb_id": agency["static_mdb_id"],
        "agency_name": agency["agency_name"],
        "static_sha256": agency["static"]["sha256"],
        "rounds": len(agency["rounds"]),
        "messages_validated": result.run.messages_validated,
        "files_skipped": result.run.files_skipped,
        "entities": staged.entities,
        "header_timestamps": staged.header_timestamps,
        "system_errors": {
            code: result.run.system_errors.count_for(code)
            for code in sorted(result.run.system_errors.rule_ids())
        },
    }, tally


def revision() -> str:
    """The commit these counts were taken at, informational and not compared.

    A ratchet that compared it would go red on every commit, which is the
    opposite of what it is for. It is here so a later reader can diff the range
    between two versions of this file and see what moved the numbers.
    """
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


def clock_note() -> dict[str, str]:
    return {
        "source": "file_name",
        "derivation": "every message is validated at its own header.timestamp",
        "why": (
            "a fixed corpus with a moving clock is not reproducible, and one fixed instant for a "
            "recording spanning minutes would report the first round's vehicles as stale purely "
            "for being recorded first. tools/agencycorpus.py stages the names that carry it."
        ),
    }


def tier_ids(tier: str) -> tuple[str, ...]:
    """Every registered rule of one tier, so a zero is stated rather than absent."""
    return tuple(sorted(rule.rule_id for rule in Registry.modern() if rule.tier == tier))


def payload(
    tier: str, agencies: list[tuple[dict[str, Any], Tally]], corpus: dict[str, Any]
) -> dict[str, Any]:
    pins = json.loads(PINS.read_text(encoding="utf-8"))
    ids = tier_ids(tier)
    return {
        "generated_by": GENERATOR,
        "do_not_edit": REGENERATE,
        "tier": tier,
        "mode": "modern",
        "generated_at": generated_at(),
        "code_revision": revision(),
        "validator_version": VERSION,
        "corpus_manifest": str(MANIFEST.relative_to(ROOT)),
        "corpus_recorded_at": corpus["recorded_at"],
        "pins": {name: pins[name] for name in ("gtfs_realtime_proto", "realtime_best_practices")},
        "clock": clock_note(),
        "entity_identity": {
            "keys": list(ENTITY_KEYS),
            "fallback": f"{ENTITY_PATH_KEY} and sourceFile",
            "note": (
                "each rule's identified_by says which was used. A rule identified by "
                f"{PATH_IDENTITY} has distinct_entities equal to occurrences by construction, "
                "since an entity index is not stable between messages; that equality is a "
                "property of the occurrence's context and not a finding about the feed."
            ),
        },
        "agencies": [
            summary | {"rules": {rule_id: tally.row(rule_id) for rule_id in ids}}
            for summary, tally in agencies
        ],
    }


def generate() -> dict[str, dict[str, Any]]:
    """Both tier files' contents, from one run per agency."""
    corpus = manifest()
    agencies = [run_agency(agency) for agency in corpus["agencies"]]
    return {tier: payload(tier, agencies, corpus) for tier in sorted(CITED_TIERS)}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.parse_args(argv)
    try:
        written = generate()
    except CorpusMissing as absent:
        print(f"corpus unavailable: {absent}", file=sys.stderr)
        return 1
    for tier, content in written.items():
        path = tier_path(tier)
        path.write_text(json.dumps(content, indent=2) + "\n", encoding="utf-8")
        print(f"wrote {path.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
