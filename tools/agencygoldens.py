"""The shape the jar's agency results are committed in: a digest and a census.

Split out of `tools/gen_agency_goldens.py` for the reason `tools/resultsdiff.py`
was split out of `tools/diff_compat_against_jar.py`: the generator needs a jar, a
JDK 17 and the recorded bytes, and the comparison must run on a checkout that has
only the bytes. Nothing here starts a JVM or reads a results file off disk.

**Digests, not the bytes.** `tests/fixtures/jar/` commits the jar's
`.results.json` outright, and for eight crafted feeds that costs 56 KB. The
recorded agency corpus is a different size: MBTA alone is 3.5 MB of results per
sort regime, and the whole point of gitignoring `corpus/` was to keep this
repository small. A SHA-256 is exact, so the check loses nothing; what it loses
is the ability to say *where* two runs differ, which is what the census restores.

**The census is the diagnosis.** Rule id to occurrence count, per input. The
common failure is that a rule started or stopped firing, and a digest alone
reports that as "these 64 hex characters are not those 64 hex characters". With
the census the same failure reads `E050: ours 12, the jar's golden 0`. When the
census matches and the digest does not, the difference is in occurrence text or
ordering, and the message says so and points at the tool that reports the byte
offset.

**Nothing here carries feed content.** A digest, a length, a count and a set of
rule ids. No trip id, no stop id, no coordinate, no occurrence prefix.
`tests/test_agency_goldens.py` asserts that rather than trusting this paragraph.

Three states, the same three `resultsdiff.compare` distinguishes: a name absent
from a side, a name present with no results file, and a name present with a
record. Collapsing the first two would let a side that dropped every skipped
input compare clean.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from typing import Any

from agencycorpus import FIXTURES
from resultsdiff import UNSEEN, Divergence, not_results

#: Where the committed golden lives. Beside the manifest whose SHA-256s the
#: bytes it describes are verified against, because neither is readable alone.
GOLDEN = FIXTURES / "jar-goldens.json"

GENERATOR = "tools/gen_agency_goldens.py"
REGENERATE = f"Regenerate with .venv/bin/python {GENERATOR}"

#: The keys one input's record has, and all it has. Asserted by the test module,
#: because "carries no feed content" is a claim about this tuple and not about a
#: docstring.
RECORD_KEYS = ("sha256", "bytes", "occurrences", "census")


def digest(blob: bytes) -> str:
    return hashlib.sha256(blob).hexdigest()


def census(blob: bytes) -> dict[str, int]:
    """Rule id to occurrence count for one `.results.json`, in id order.

    Upstream writes one array element per rule that fired, each carrying its own
    `occurrenceList` (`BatchProcessor.java:321` writes what `NoticeContainer`
    grouped). Summing rather than taking the last is deliberate: nothing in
    upstream promises a rule appears once, and a census that silently dropped a
    second entry would under-report the very thing it exists to explain.
    """
    counts: dict[str, int] = {}
    for entry in json.loads(blob):
        rule_id = entry["errorMessage"]["validationRule"]["errorId"]
        counts[rule_id] = counts.get(rule_id, 0) + len(entry["occurrenceList"])
    return {rule_id: counts[rule_id] for rule_id in sorted(counts)}


def record(blob: bytes) -> dict[str, Any]:
    """One results file, reduced to what gets committed."""
    tally = census(blob)
    return {
        "sha256": digest(blob),
        "bytes": len(blob),
        "occurrences": sum(tally.values()),
        "census": tally,
    }


def side(results: Mapping[str, bytes | None]) -> dict[str, Any]:
    """A whole run's results, reduced. `None` stays `None`: it is a claim.

    A results file the jar never wrote is not an empty one, and the golden has
    to be able to say so for the eighteen MBTA inputs it wrote nothing for.
    """
    return {name: (None if blob is None else record(blob)) for name, blob in results.items()}


def _census_lines(ours: dict[str, int], theirs: dict[str, int]) -> list[str]:
    """Every rule the two disagree about, zeros stated on the side that has none."""
    lines = []
    for rule_id in sorted(set(ours) | set(theirs)):
        mine, jars = ours.get(rule_id, 0), theirs.get(rule_id, 0)
        if mine != jars:
            lines.append(f"  {rule_id}: ours {mine}, the jar's golden {jars}")
    return lines


def _differing(name: str, mine: dict[str, Any], theirs: dict[str, Any]) -> Divergence:
    """Two records with different digests, told apart by their censuses."""
    head = (
        f"sha256 ours {mine['sha256'][:12]}, the jar's golden {theirs['sha256'][:12]}\n"
        f"  ours {mine['bytes']} bytes / {mine['occurrences']} occurrences, "
        f"the jar's golden {theirs['bytes']} bytes / {theirs['occurrences']} occurrences"
    )
    lines = _census_lines(mine["census"], theirs["census"])
    if lines:
        return Divergence(name, "bytes", "\n".join([head, "the rule census differs:", *lines]))
    return Divergence(
        name,
        "bytes",
        f"{head}\nthe rule census is identical, so the difference is in occurrence text or "
        "order rather than in which rules fired. Run\n"
        "  .venv/bin/python tools/diff_agency_against_jar.py\n"
        "against a real jar for the first differing byte offset.",
    )


def compare(ours: Mapping[str, bytes | None], golden: Mapping[str, Any]) -> list[Divergence]:
    """This project's raw output against the committed golden, name by name.

    Deliberately the same vocabulary `resultsdiff.compare` uses, so a divergence
    from the jarless check and one from the live differential read alike and a
    reader never has to ask which harness produced a `only-ours`.

    Our side is passed as raw bytes rather than as records so that this can
    reject bytes that are not a results file at all. `record` would happily
    digest `b""`, and two sides that both wrote nothing agree on every byte of
    it.
    """
    names = sorted(set(ours) | set(golden))
    if not names:
        return [
            Divergence(
                "<no inputs>",
                "vacuous",
                "neither side was handed an input, so nothing was compared. An empty "
                "comparison agrees about everything and is evidence of nothing.",
            )
        ]
    divergences = []
    for name in names:
        mine = ours.get(name, UNSEEN)
        theirs = golden.get(name, UNSEEN)
        if mine is UNSEEN:
            held = "no results file" if theirs is None else f"{theirs['bytes']} bytes"
            detail = f"the golden has it ({held}); this project's run never saw it"
            divergences.append(Divergence(name, "unseen-by-ours", detail))
        elif theirs is UNSEEN:
            held = "no results file" if mine is None else f"{len(mine)} bytes"
            detail = f"this project's run has it ({held}); the golden never recorded it"
            divergences.append(Divergence(name, "unseen-by-jar", detail))
        elif mine is None and theirs is None:
            continue
        elif theirs is None:
            detail = f"the jar wrote no results file; this project wrote {len(mine)} bytes"
            divergences.append(Divergence(name, "only-ours", detail))
        elif mine is None:
            detail = f"the jar wrote {theirs['bytes']} bytes; this project wrote no results file"
            divergences.append(Divergence(name, "only-jar", detail))
        elif reason := not_results(mine):
            detail = f"this project wrote {reason}, which is not something to compare"
            divergences.append(Divergence(name, "not-results", detail))
        else:
            produced = record(mine)
            if produced["sha256"] != theirs["sha256"]:
                divergences.append(_differing(name, produced, theirs))
    return divergences
