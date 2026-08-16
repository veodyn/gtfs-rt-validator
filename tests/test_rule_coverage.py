"""How many of the 56 batch-reachable rules a real jar has been seen to emit.

`tests/test_completeness.py` answers "is the rule written?" by looking at the
tree. This module answers the different and harder question: **has upstream's
own jar ever been observed emitting it?** A rule can be written, registered,
unit-tested against a transcribed Java fixture, and still never have been put in
front of the jar. Only a `.results.json` the jar wrote settles that.

**Provenance, not filename.** The evidence is not "every `*.results.json` under
`tests/fixtures/`": a file this project wrote, or a golden edited by hand, has
that name too and would count as the jar's own words. What counts is a results
file a corpus manifest names *and* whose sha256 is the one that manifest
recorded, in a manifest `tools/gen_golden.py` wrote at the pin the rest of the
project is at. `unattested_files` then asserts nothing else with that name is
lying around, so the two sets are the same set.

**A floor, not an equality.** The gate used to be `len(found) == committed`,
which a commit could satisfy by deleting a feed and lowering the constant in the
same diff. So the floor is checked against something that commit cannot edit
here: `manifest.batch_reachable_ids()`, generated from upstream's own Java. Every
batch-reachable rule must appear in a golden, `JAR_VERIFIED_RULES` may not be set
below the number of them, and no committed corpus can lower either.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from gtfs_rt_validator.report import manifest

ROOT = Path(__file__).resolve().parent.parent
FIXTURES = ROOT / "tests" / "fixtures"
RESULTS_SUFFIX = ".results.json"

#: The two corpus manifests, which are the only sources of jar-written goldens.
#: `tools/gen_golden.py` writes both, one flat and one grouped.
MANIFESTS = (
    FIXTURES / "jar" / "manifest.json",
    FIXTURES / "conformance" / "manifest.json",
)

#: The upstream commit both corpora must have been generated at.
PIN = json.loads((ROOT / "upstream" / "pins.json").read_text(encoding="utf-8"))[
    "gtfs_realtime_validator"
]["commit"]

#: How many of the 56 batch-reachable rules a committed golden has caught the
#: jar emitting. A floor: raising it is the commit that adds the feeds reaching
#: more, and lowering it below the number of batch-reachable rules fails.
#:
#: It started at 10, which was every id the five `tests/fixtures/jar/` goldens
#: carried: those eight feeds were built to pin the *output contract*, not to
#: aim at rules, and the ids they trip were a bonus. The tier 1 conformance
#: corpus under `tests/fixtures/conformance/` is what took it to 56, which is
#: every batch-reachable rule: the whole set the differential is asked about.
JAR_VERIFIED_RULES = 56


class UnattestedGoldenError(AssertionError):
    """A results file's bytes are not the ones its manifest recorded."""


def _digest(blob: bytes) -> str:
    return hashlib.sha256(blob).hexdigest()


def _sections(document: dict) -> list[dict]:
    """A manifest's input lists, whichever shape it was written in.

    The jar corpus is one flat `inputs` list beside its manifest; the
    conformance corpus is a `groups` list, each with its own subdirectory,
    because a group is one jar invocation.
    """
    return document.get("groups") or [document]


def attested_goldens(manifests: tuple[Path, ...] = MANIFESTS) -> dict[Path, bytes]:
    """Every results file a generated manifest names, with its bytes checked.

    Raises rather than skipping a file that does not match what the manifest
    recorded: a golden whose bytes moved is either a hand edit or a corpus that
    was regenerated without its manifest, and both make everything below a
    statement about something other than a jar run.
    """
    found: dict[Path, bytes] = {}
    for path in manifests:
        document = json.loads(path.read_text(encoding="utf-8"))
        if not document.get("generated_by", "").startswith("tools/gen_golden.py"):
            raise UnattestedGoldenError(f"{path} does not say tools/gen_golden.py wrote it")
        if document.get("pin") != PIN:
            raise UnattestedGoldenError(f"{path} was generated at {document.get('pin')}, not {PIN}")
        for section in _sections(document):
            directory = path.parent / section.get("name", "")
            for record in section["inputs"]:
                if record["results"] is None:
                    continue
                golden = directory / record["results"]
                blob = golden.read_bytes()
                if _digest(blob) != record["results_sha256"]:
                    raise UnattestedGoldenError(f"{golden} is not the file the manifest recorded")
                found[golden] = blob
    return found


def unattested_files(
    root: Path = FIXTURES, manifests: tuple[Path, ...] = MANIFESTS
) -> tuple[Path, ...]:
    """Every file named like a golden that no manifest accounts for."""
    named = set(attested_goldens(manifests))
    return tuple(sorted(path for path in root.rglob("*" + RESULTS_SUFFIX) if path not in named))


def verified_ids(manifests: tuple[Path, ...] = MANIFESTS) -> set[str]:
    """Every errorId an attested golden shows the jar emitting."""
    found: set[str] = set()
    for blob in attested_goldens(manifests).values():
        for group in json.loads(blob):
            found.add(group["errorMessage"]["validationRule"]["errorId"])
    return found


def unverified(found: set[str]) -> tuple[str, ...]:
    """The batch-reachable ids no attested golden has the jar emitting."""
    return tuple(rule_id for rule_id in manifest.batch_reachable_ids() if rule_id not in found)


def gate(found: set[str], committed: int) -> tuple[str, ...]:
    """Every reason this corpus fails the coverage gate, or `()`.

    A pure function of the two arguments, so the states the committed corpus
    cannot be put into are still assertable. `found` is what the goldens carry;
    `committed` is `JAR_VERIFIED_RULES`.
    """
    reachable = manifest.batch_reachable_ids()
    reasons = []
    if committed < len(reachable):
        reasons.append(
            f"{committed} rules are committed as jar-verified and {len(reachable)} are "
            "batch-reachable. The marker is a floor: every rule compat can reach has to have "
            "been seen coming out of the jar, so lowering it is how coverage is lost quietly"
        )
    if len(found) < committed:
        reasons.append(
            f"{committed} rules are committed as jar-verified and {len(found)} appear in the "
            f"goldens; no golden emits {unverified(found)}: corpus feeds or goldens were "
            "deleted, or a regenerated run stopped reaching them"
        )
    missing = unverified(found)
    if missing:
        reasons.append(f"no attested golden has the jar emitting {missing}")
    return tuple(reasons)


def test_every_id_in_a_golden_is_a_rule_compat_can_reach():
    """A golden naming an id outside the 56 would mean the manifest and the jar
    disagree about what `BatchProcessor` registers, which is a far bigger
    finding than a coverage number."""
    assert unverified(set(manifest.batch_reachable_ids())) == ()
    assert verified_ids() <= set(manifest.batch_reachable_ids())


def test_the_committed_corpus_verifies_exactly_the_rules_it_claims_to():
    found = verified_ids()
    assert gate(found, JAR_VERIFIED_RULES) == (), (
        f"still unverified against the jar: {unverified(found)}"
    )
    assert found == set(manifest.batch_reachable_ids())


def test_nothing_named_like_a_golden_is_uncounted():
    """The provenance the count rests on. A results file no manifest names is
    either something this project wrote or a golden left behind by a rename, and
    both would be read as the jar's own words by anything walking the tree."""
    assert unattested_files() == ()


def test_the_marker_is_a_count_of_rules_that_exist_to_verify():
    """Above 56 the gate is unsatisfiable and below it coverage is being given
    up, and either would be a typo nothing else catches."""
    assert len(manifest.batch_reachable_ids()) == JAR_VERIFIED_RULES


def test_the_floor_cannot_be_lowered_to_meet_a_shrunken_corpus():
    """The move the old equality gate allowed: delete the feeds that reach a
    rule, drop the constant to match, and the suite stays green."""
    reachable = manifest.batch_reachable_ids()
    assert gate(set(reachable), len(reachable)) == ()
    for lowered in (0, 1, 55):
        assert gate(set(reachable[:lowered]), lowered) != ()
    assert gate(set(reachable[:55]), 55) != ()
    assert gate(set(reachable) - {reachable[0]}, len(reachable)) != ()


def _golden(rule_id: str) -> bytes:
    """The two fields this module reads out of a results file, and nothing else."""
    entry = {"errorMessage": {"validationRule": {"errorId": rule_id}}, "occurrenceList": []}
    return json.dumps([entry]).encode("utf-8")


def _fake_corpus(tmp_path: Path, blob: bytes, recorded: bytes | None = None, **fields) -> Path:
    """A one-golden corpus of the shape `gen_golden` writes, for the teeth below."""
    (tmp_path / "01-feed.pb.results.json").write_bytes(blob)
    document = {
        "generated_by": "tools/gen_golden.py",
        "pin": PIN,
        "inputs": [
            {
                "name": "01-feed.pb",
                "results": "01-feed.pb.results.json",
                "results_sha256": _digest(recorded if recorded is not None else blob),
            }
        ],
        **fields,
    }
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(document), encoding="utf-8")
    return path


def test_a_results_file_no_manifest_names_is_not_evidence(tmp_path):
    """The hole provenance closes. Anything under `tests/fixtures/` with this
    name used to count towards "the jar was seen emitting it", including a file
    this project wrote itself."""
    attested = _fake_corpus(tmp_path, _golden("W002"))
    planted = tmp_path / "hand-written.results.json"
    planted.write_bytes(_golden("E010"))

    assert verified_ids((attested,)) == {"W002"}
    assert unattested_files(tmp_path, (attested,)) == (planted,)


def test_a_golden_whose_bytes_moved_is_refused_rather_than_counted(tmp_path):
    """An edited golden is not a jar run, so it may not answer the question this
    module asks."""
    attested = _fake_corpus(tmp_path, _golden("W002"), recorded=_golden("E001"))

    with pytest.raises(UnattestedGoldenError, match="not the file the manifest recorded"):
        verified_ids((attested,))


def test_a_manifest_nothing_generated_or_from_another_pin_is_refused(tmp_path):
    """Both halves of "a manifest `tools/gen_golden.py` wrote at the pin". A
    hand-written manifest naming its own files would otherwise mint provenance
    for anything."""
    hand_written = _fake_corpus(tmp_path, _golden("W002"), generated_by="me, just now")
    with pytest.raises(UnattestedGoldenError, match=r"tools/gen_golden\.py"):
        verified_ids((hand_written,))

    (elsewhere := tmp_path / "other").mkdir()
    moved = _fake_corpus(elsewhere, _golden("W002"), pin="0" * 40)
    with pytest.raises(UnattestedGoldenError, match="was generated at"):
        verified_ids((moved,))


def test_the_failure_names_the_rules_no_golden_reaches():
    """ "Which ones?" is the first question anyone reading this failure asks, and
    a bare count cannot answer it."""
    reachable = manifest.batch_reachable_ids()

    reasons = gate(set(reachable[:30]), 56)

    assert any(reachable[30] in reason for reason in reasons)
    assert any(reachable[55] in reason for reason in reasons)
