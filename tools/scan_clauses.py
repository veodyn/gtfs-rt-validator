"""Generate the two clause indexes the cited tiers cite against.

`upstream/spec-clauses.json` is every normative sentence of the pinned
`gtfs-realtime.proto`; `upstream/practice-clauses.json` is every normative
statement of the pinned Best Practices markdown. Both carry the sentence, where
it starts, what modal verbs it uses and therefore which severities a rule citing
it may declare.

**This is what replaces the jar for the `spec` and `practice` tiers.** The 56
upstream rules have a byte-for-byte differential against somebody else's
implementation; these two tiers have no implementation to differ against, so
the citation is the contract instead. `tests/test_clause_citations.py` asserts
that every rule's `source=` string is verbatim a sentence in one of these files,
that every sentence in them has a committed verdict, that a rule's severity
agrees with its sentence's modal verb, and that both files reproduce from their
sources byte for byte. Move a pin and a reworded clause fails its rule, a new
clause fails for having no verdict, and a removed clause fails for having a
rule.

Both sources are committed under `upstream/`, so this needs no network and the
check is unconditional, the way `tools/pack_rules.py` is and `tools/map_rules.py`
is not. `tools/fetch_practices.py` is what puts the markdown there.

Each index takes one extra input from its verdict file, and the two are
deliberately different mechanisms because they answer different questions.

The markdown index takes `hand_added`, which records a **scanner miss**: the
Best Practices document writes six recommendations in the imperative, `:128`
"Do not apply the alert to every stop of the line." among them, and a modal-verb
sweep cannot reach a statement that is normative in the document's own voice.
Those six are why the markdown yields 62 distinct normative statements from 71
raw, and all 62 carry a verdict in `upstream/practice-clause-verdicts.json`.

The proto index takes `definitional`, which is the opposite. Two of the proto's
field descriptions fix the field's *value domain* rather than stating an
obligation: `:272` "Refers to a stop_id defined in the GTFS stops.txt." and
`:1221` "Dates on which the modifications occurs, in the YYYYMMDD format."
Neither carries a modal verb and neither should, because a value outside the
stated domain is not ill-advised, it is meaningless. Calling them `hand_added`
would report a scanner defect that does not exist, so they are their own kind,
with an explicitly declared severity and a reason.

Both lists are inputs a human writes and this tool verifies: a `hand_added`
statement must be a verbatim substring of the line it names, a `definitional`
one must be a sentence the splitter itself cuts at that line, must carry no
modal verb, and must declare ERROR with a reason. So each index still
reproduces from committed inputs, and an entry that stops matching its source
fails the build like any other drift.

Run: .venv/bin/python tools/scan_clauses.py
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import clausemd
import clauseproto
from clausescan import Block, Sentence, modals, normative, severities

ROOT = Path(__file__).resolve().parent.parent
UPSTREAM = ROOT / "upstream"
PINS = json.loads((UPSTREAM / "pins.json").read_text(encoding="utf-8"))

PROTO = UPSTREAM / "gtfs-realtime.proto"
PRACTICES = UPSTREAM / "realtime-best-practices.md"
SPEC_INDEX = UPSTREAM / "spec-clauses.json"
PRACTICE_INDEX = UPSTREAM / "practice-clauses.json"
SPEC_VERDICTS = UPSTREAM / "spec-clause-verdicts.json"
PRACTICE_VERDICTS = UPSTREAM / "practice-clause-verdicts.json"

#: The only severity a definitional clause may declare. A sentence that fixes a
#: field's value domain carries no modal verb, so `clausescan.severities` has
#: nothing to read; the severity comes from what the clause *is* instead. There
#: is no advisory reading of "this field holds a YYYYMMDD date", because a value
#: outside the domain is not ill-advised but meaningless, and a consumer cannot
#: act on it either way. Anything softer would be this file inventing an opinion
#: the proto does not state, which is the same objection
#: `rules/registry.py:_check_severity` makes to defaulting a rule's severity.
DEFINITIONAL_SEVERITY = "ERROR"


def _digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _clause(block: Block, sentence: Sentence, ordinal: int) -> dict:
    found = modals(sentence.text)
    from clausescan import PASS_ONE

    return {
        "id": f"{sentence.line}#{ordinal}",
        "line": sentence.line,
        "unit_line": block.line,
        "scope": block.scope,
        "kind": block.kind,
        "found_by": "pass_one" if any(w in PASS_ONE for w in found) else "pass_two",
        "modals": list(found),
        "severities": list(severities(found)),
        "text": sentence.text,
        "sha256": _digest(sentence.text),
    }


def _numbered(pairs: list[tuple[Block, Sentence]]) -> list[dict]:
    """Give each sentence an id, counting within its starting line."""
    seen: dict[int, int] = {}
    out = []
    for block, sentence in pairs:
        seen[sentence.line] = seen.get(sentence.line, 0) + 1
        out.append(_clause(block, sentence, seen[sentence.line]))
    return out


def _definitional() -> list[dict]:
    """Value-domain sentences a human declared, verified against the proto."""
    if not SPEC_VERDICTS.is_file():
        return []
    return json.loads(SPEC_VERDICTS.read_text(encoding="utf-8")).get("definitional", [])


def _declared(clauses: list[dict], blocks: list[tuple[Block, list[int]]]) -> None:
    """Merge the declared definitional clauses into `clauses`, in place.

    Four checks, and each one is a way the declaration could go wrong. The text
    must be a sentence the splitter itself cuts at the line it names, not merely
    a substring of it, so a citation quotes what a reader of the index would
    quote. It must carry no modal verb, because a sentence that does is the
    keyword sweep's and declaring it here would give it two entries. And it must
    declare ERROR with a reason, which is where a definitional clause's severity
    comes from now that there is no modal verb to read.
    """
    from clausescan import sentences

    cut = {
        (sentence.line, sentence.text): block
        for block, line_of in blocks
        for sentence in sentences(block, line_of)
    }
    for declared in _definitional():
        line, text = declared["line"], declared["text"]
        block = cut.get((line, text))
        where = f"declared clause at line {line} of {PROTO.name}"
        if block is None:
            raise SystemExit(f"{where} is not a sentence the splitter cuts there: {text!r}")
        if modals(text):
            found = ", ".join(modals(text))
            raise SystemExit(f"{where} carries {found}, so the keyword sweep already has it")
        if declared.get("severity") != DEFINITIONAL_SEVERITY:
            raise SystemExit(f"{where} must declare {DEFINITIONAL_SEVERITY}: {declared!r}")
        if not declared.get("reason", "").strip():
            raise SystemExit(f"{where} declares a severity with no reason")
        clauses.append(
            {
                "id": f"{line}#{sum(1 for c in clauses if c['line'] == line) + 1}",
                "line": line,
                "unit_line": block.line,
                "scope": block.scope,
                "kind": "definitional",
                "found_by": "declared",
                "modals": [],
                "severities": [DEFINITIONAL_SEVERITY],
                "reason": declared["reason"],
                "text": text,
                "sha256": _digest(text),
            }
        )
    clauses.sort(key=lambda clause: (clause["line"], clause["id"]))


def spec_index() -> dict:
    from clausescan import sentences

    source = PROTO.read_text(encoding="utf-8")
    blocks = clauseproto.blocks(source)
    clauses = _numbered(normative(blocks))
    _declared(clauses, blocks)
    counts = clauseproto.counts(source)
    counts.update(
        {
            "comment_blocks": len(blocks),
            "comment_sentences": sum(len(sentences(block, line_of)) for block, line_of in blocks),
            "normative_sentences": sum(1 for c in clauses if c["found_by"] != "declared"),
            "definitional_clauses": sum(1 for c in clauses if c["found_by"] == "declared"),
            "normative_blocks": len({clause["unit_line"] for clause in clauses}),
            "found_by_pass_one": sum(1 for c in clauses if c["found_by"] == "pass_one"),
            "found_by_pass_two": sum(1 for c in clauses if c["found_by"] == "pass_two"),
        }
    )
    return {
        "generated_by": "tools/scan_clauses.py",
        "tier": "spec",
        "source": PROTO.relative_to(ROOT).as_posix(),
        "source_sha256": _digest(source),
        "pin": PINS["gtfs_realtime_proto"],
        "counts": counts,
        "clauses": clauses,
    }


def _hand_added() -> list[dict]:
    """Imperative statements a human named, verified against the document."""
    if not PRACTICE_VERDICTS.is_file():
        return []
    return json.loads(PRACTICE_VERDICTS.read_text(encoding="utf-8")).get("hand_added", [])


def practice_index() -> dict:
    source = PRACTICES.read_text(encoding="utf-8")
    lines = source.split("\n")
    raw = _numbered(normative(clausemd.units(source)))
    for added in _hand_added():
        line, text = added["line"], added["text"]
        if text not in lines[line - 1]:
            raise SystemExit(
                f"hand-added statement is not on line {line} of {PRACTICES.name}: {text!r}"
            )
        found = modals(text)
        raw.append(
            {
                "id": f"{line}#{sum(1 for c in raw if c['line'] == line) + 1}",
                "line": line,
                "unit_line": line,
                "scope": "",
                "kind": "imperative",
                "found_by": "hand",
                "modals": list(found),
                "severities": list(severities(found)) or ["WARNING"],
                "text": text,
                "sha256": _digest(text),
            }
        )
    raw.sort(key=lambda clause: (clause["line"], clause["id"]))

    # Eight of the document's recommendations are repeated verbatim, the
    # `TripDescriptor`/`VehicleDescriptor` pairing sentence and its worked
    # example four times each. The index keeps one entry per distinct statement
    # and records the other lines, because counting occurrences would overstate
    # the surface and give one statement four verdicts.
    clauses: list[dict] = []
    by_text: dict[str, dict] = {}
    for clause in raw:
        first = by_text.get(clause["text"])
        if first is None:
            clause["also_at"] = []
            by_text[clause["text"]] = clause
            clauses.append(clause)
        else:
            first["also_at"].append(clause["line"])

    counts = clausemd.counts(source)
    counts.update(
        {
            "normative_statements_raw": len(raw),
            "normative_statements_distinct": len(clauses),
            "found_by_pass_one": sum(1 for c in clauses if c["found_by"] == "pass_one"),
            "found_by_pass_two": sum(1 for c in clauses if c["found_by"] == "pass_two"),
            "found_by_hand": sum(1 for c in clauses if c["found_by"] == "hand"),
        }
    )
    return {
        "generated_by": "tools/scan_clauses.py",
        "tier": "practice",
        "source": PRACTICES.relative_to(ROOT).as_posix(),
        "source_sha256": _digest(source),
        "pin": PINS["realtime_best_practices"],
        "counts": counts,
        "clauses": clauses,
    }


def write(target: Path, payload: dict) -> None:
    # No key sorting, so field order is the generator's; ASCII-escaped by
    # default so the digest and the diff do not move with a writer's locale;
    # 2-space indent so a drift diff reads line by line. Same three choices as
    # `tools/map_rules.py`, for the same reasons.
    target.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    write(SPEC_INDEX, spec_index())
    write(PRACTICE_INDEX, practice_index())
    for path in (SPEC_INDEX, PRACTICE_INDEX):
        payload = json.loads(path.read_text(encoding="utf-8"))
        print(f"{path.relative_to(ROOT)}: {len(payload['clauses'])} clauses")
        for name, value in payload["counts"].items():
            print(f"    {name}: {value}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
