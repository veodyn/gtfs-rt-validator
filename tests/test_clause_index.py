"""Whether the two clause indexes still are what `tools/scan_clauses.py` makes.

The half of the clause gate that is about the files rather than about the
rules. `test_clause_citations.py` asserts that every rule quotes a sentence in
an index; this asserts that the indexes are generated, not typed, that the
scanner's two keyword passes both earn their place, and that the counts quoted
elsewhere are the counts the scanner actually produces.

The counts matter more here than they look. The cited tiers were designed
against numbers from an early scan nobody committed, and four of those numbers
came out differently once the scanner became a tool. Pinning them makes the next
difference a diff somebody reads rather than a number somebody transcribes.
"""

import hashlib
import subprocess
import sys

import pytest

from clauseindex import ROOT, TIERS, index

# Measured against the two pins by `tools/scan_clauses.py`, never transcribed
# from prose. A number here that disagrees with the scanner means the pinned
# source moved: re-run the tool and update this table in the same commit.
SPEC_COUNTS = {
    "lines": 1271,
    "messages": 28,
    "enums": 12,
    "field_definitions": 140,
    "required_fields": 9,
    "deprecated_sites": 2,
    "experimental_fields": 26,
    "experimental_messages": 9,
    "comment_blocks": 234,
    "comment_sentences": 566,
    "normative_sentences": 124,
    "definitional_clauses": 2,
    "normative_blocks": 75,
    "found_by_pass_one": 116,
    "found_by_pass_two": 8,
}
PRACTICE_COUNTS = {
    "lines": 166,
    "headings": 22,
    "table_recommendation_rows": 26,
    "top_level_bullets": 23,
    "free_paragraphs": 16,
    "normative_statements_raw": 71,
    "normative_statements_distinct": 62,
    "found_by_pass_one": 51,
    "found_by_pass_two": 5,
    "found_by_hand": 6,
}


@pytest.fixture(scope="module", params=sorted(TIERS))
def tier(request: pytest.FixtureRequest) -> str:
    return request.param


def test_regenerating_reproduces_the_committed_indexes_byte_for_byte():
    """Both sources are committed, so unlike `map_rules.py` this needs no
    network and the check is unconditional: there is no version of this
    checkout where a generated index may quietly differ from its generator.
    Hand-editing one would make every assertion next door lie."""
    before = {path: path.read_bytes() for path, _ in TIERS.values()}
    subprocess.run([sys.executable, "tools/scan_clauses.py"], check=True, cwd=ROOT)
    for path, body in before.items():
        assert path.read_bytes() == body, f"{path.name} is not what tools/scan_clauses.py produces"


def test_the_index_names_the_bytes_it_read(tier: str):
    """A swapped source is visible without regenerating."""
    payload = index(tier)
    source = (ROOT / payload["source"]).read_bytes()
    assert hashlib.sha256(source).hexdigest() == payload["source_sha256"]
    assert payload["generated_by"] == "tools/scan_clauses.py"


def test_the_measured_counts_are_ratcheted(tier: str):
    assert index(tier)["counts"] == {"spec": SPEC_COUNTS, "practice": PRACTICE_COUNTS}[tier]


def test_the_second_keyword_pass_earns_its_place(tier: str):
    """The scanner's two passes, defended by measurement rather than a comment.

    The first keyword set alone would miss real clauses in both sources, and
    the temptation to collapse the two lists into one and then drop half of it
    as redundant is exactly what this stops. If a later pin makes the second
    pass contribute nothing, that is a decision to take deliberately, with this
    assertion in the diff.
    """
    recovered = [c for c in index(tier)["clauses"] if c["found_by"] == "pass_two"]
    assert recovered, f"{tier}: the second keyword pass found nothing"
    for clause in recovered:
        assert clause["modals"], clause["id"]


def test_the_spec_index_recovers_the_clauses_a_single_pass_would_lose():
    """Named, not counted, because the interesting thing is which ones.

    `TripDescriptor.ADDED`'s deprecation and both copies of "At most one
    translation is allowed to have an unspecified language tag" are all cited by
    a spec-tier rule, and no keyword in the first set reaches any of the three.
    """
    recovered = {
        c["line"]: c["text"] for c in index("spec")["clauses"] if c["found_by"] == "pass_two"
    }
    assert recovered[853].startswith("This value has been deprecated")
    assert (
        recovered[1024] == "At most one translation is allowed to have an unspecified language tag."
    )
    assert recovered[1072] == recovered[1024]
    assert recovered[157].startswith("There can be at most one TripUpdate entity")


def test_the_repeated_statements_are_counted_once_each():
    """The Best Practices document repeats itself, and counting occurrences
    would overstate its surface by a seventh. The `TripDescriptor` and
    `VehicleDescriptor` pairing sentence and its worked example appear four
    times each; three more statements appear twice. Nine occurrences fold into
    five statements."""
    repeated = {c["id"]: c["also_at"] for c in index("practice")["clauses"] if c["also_at"]}
    assert repeated == {
        "44#1": [114],
        "50#1": [127],
        "56#1": [58, 66, 83],
        "56#2": [58, 68, 85],
        "89#1": [116],
    }
    assert sum(len(lines) for lines in repeated.values()) == 9


def test_the_proto_index_does_not_fold_its_two_identical_sentences():
    """`TranslatedString` and `TranslatedImage` carry the same sentence about
    untagged translations, and it is two rules, not one: they constrain
    different messages and the tier gives them S032 and S034. So the proto
    index keeps every occurrence where the markdown index folds duplicates.
    The two sources genuinely differ here and the scanner is not being
    inconsistent."""
    texts = [c["text"] for c in index("spec")["clauses"]]
    duplicated = {text for text in texts if texts.count(text) > 1}
    assert duplicated == {
        "At most one translation is allowed to have an unspecified language tag.",
        "If cause_detail is included, then Cause must also be included.",
        "If effect_detail is included, then Effect must also be included.",
        "Must be the same as in stop_times.txt in the corresponding GTFS feed.",
        "Must be the same as in stops.txt in the corresponding GTFS feed.",
        (
            "Required if schedule_relationship=DUPLICATED, otherwise this field must not be "
            "populated and will be ignored by consumers."
        ),
        (
            "This field is required as per reference.md, but needs to be specified here "
            'optional because "Required is Forever"'
        ),
    }


def test_declared_definitional_clauses_are_not_scanner_misses():
    """The proto's third kind of clause, and the narrowest of the three slots.

    `hand_added` next door says the sweep missed a statement. These two say the
    opposite: the sentence has no modal verb, should not have one, and fixes the
    field's *value domain* instead. "Refers to a stop_id defined in the GTFS
    stops.txt" and "in the YYYYMMDD format" are definitional, and a value outside
    the stated domain is malformed whether or not any sentence says "must",
    because the field would otherwise have no meaning.

    So the severity cannot come from decision 4's modal-verb mapping, which has
    nothing to read. It comes from what the clause is, and the generator pins it:
    a definitional clause declares ERROR and nothing else, with a reason, because
    there is no advisory reading of a value domain. That keeps the slot from
    becoming a way to declare an arbitrary severity for an arbitrary sentence,
    which is the failure this test is here to prevent.
    """
    from clauseindex import verdicts

    declared = verdicts("spec")["definitional"]
    lines = (ROOT / "upstream" / "gtfs-realtime.proto").read_text(encoding="utf-8").split("\n")
    assert [entry["line"] for entry in declared] == [272, 1221]
    for entry in declared:
        assert entry["text"] in lines[entry["line"] - 1]
        assert entry["severity"] == "ERROR"
        assert entry["reason"].strip()
    in_index = [c for c in index("spec")["clauses"] if c["found_by"] == "declared"]
    assert [c["id"] for c in in_index] == ["272#1", "1221#2"]
    for clause in in_index:
        assert clause["kind"] == "definitional"
        assert clause["modals"] == []
        assert clause["severities"] == ["ERROR"]
        assert clause["reason"].strip()


def test_hand_added_statements_are_the_ones_no_keyword_can_reach():
    """The Best Practices document writes six of its recommendations in the
    imperative. A modal-verb sweep cannot see them, and widening it until it
    could would sweep in the document's narration as well, so a human names
    them in the verdict file and `tools/scan_clauses.py` verifies each against
    the line it claims. `:128` is the one that matters: P012 has no other
    statement to cite."""
    from clauseindex import verdicts

    added = verdicts("practice")["hand_added"]
    lines = (
        (ROOT / "upstream" / "realtime-best-practices.md").read_text(encoding="utf-8").split("\n")
    )
    assert [entry["line"] for entry in added] == [18, 95, 128, 129, 133, 162]
    for entry in added:
        assert entry["text"] in lines[entry["line"] - 1]
    by_hand = {c["line"] for c in index("practice")["clauses"] if c["found_by"] == "hand"}
    assert by_hand == {entry["line"] for entry in added}
