"""Where the two clause indexes and their verdict files live, for two modules.

`test_clause_citations.py` asserts what the rules do with them;
`test_clause_index.py` asserts that the files are what the scanner produces.
Both need the same four paths and the same loader, and neither is the natural
home for it.
"""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
UPSTREAM = ROOT / "upstream"

#: Tier name to (index, verdicts). The tier names are `registry.CITED_TIERS`'.
TIERS = {
    "spec": (UPSTREAM / "spec-clauses.json", UPSTREAM / "spec-clause-verdicts.json"),
    "practice": (UPSTREAM / "practice-clauses.json", UPSTREAM / "practice-clause-verdicts.json"),
}

#: Verdicts under which a rule quotes the clause as its `source=` string.
CITING = ("rule", "rule_in_part")

#: Every verdict a clause may carry. `deferred` is a real verdict and not an
#: escape hatch: it says the clause was read, no rule covers it, and the note
#: says what is missing. No clause carries it today. `413#1` was the one and it
#: is now rejected under R6, since E002, E045 and E051 own all three ways a feed
#: can express a stop order that differs from `stop_times.txt`. The kind stays
#: in the vocabulary for a clause a later pin introduces mid-review.
VERDICT_KINDS = ("rule", "rule_in_part", "folded", "rejected", "deferred")


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def index(tier: str) -> dict:
    return load(TIERS[tier][0])


def verdicts(tier: str) -> dict:
    return load(TIERS[tier][1])
