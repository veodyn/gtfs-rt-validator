"""The citation is the contract, because the two cited tiers have no oracle.

The 56 upstream rules are checked against somebody else's implementation, byte
for byte. Nothing implements the `spec` and `practice` tiers, so
`tools/diff_compat_against_jar.py` cannot confirm one of their rules and never
will. What replaces it is this: two committed clause indexes generated from the
two pinned sources, a committed verdict for every sentence in them, and four
assertions.

- Every registered cited-tier rule's `source=` string, minus its tier prefix,
  is **verbatim** a sentence in its index. A typo, a paraphrase or a tidied
  quote fails.
- Every sentence in an index has a verdict: cited by a rule, folded into one,
  rejected with a reason code, or deferred with a note. A sentence with no
  verdict fails.
- A severity agrees with the modal verb of the sentence it cites. A rule that
  cites a `should` and declares ERROR fails. **This assertion lands here rather
  than with the first cohort**, so no cohort can be the one that introduces an
  exception.
- Both indexes reproduce from their sources byte for byte, which is
  `test_clause_index.py` next door.

What that buys is exactly what the jar buys for the 56: a change in the source
is a red test rather than a silent drift. Move a pin and a reworded clause
fails its rule's citation, a new clause fails for having no verdict, and a
removed clause fails for having a rule. It also catches the failure prose
cannot: a rule that drifts away from its own citation while still passing its
own fixtures, because its fixtures drifted with it.

What it does not buy: that the sentences chosen are the right ones. The verdict
files are the reviewable artifact for that, which is why the rejections are
enumerated with reasons rather than summarised.
"""

import pytest

from clauseindex import CITING, TIERS, VERDICT_KINDS, index, verdicts
from gtfs_rt_validator.rules import registry


@pytest.fixture(scope="module", params=sorted(TIERS))
def tier(request: pytest.FixtureRequest) -> str:
    return request.param


@pytest.fixture(scope="module")
def registered() -> tuple[registry.RegisteredRule, ...]:
    registry.discover()
    return tuple(rule for rule in registry.Registry.modern() if rule.tier in registry.CITED_TIERS)


def quoted_by(rule: registry.RegisteredRule) -> str:
    """The sentence a rule claims, with its `spec: ` or `practice: ` prefix off.

    **No `.strip()`.** The gate's whole claim is that a citation is verbatim, and
    stripping here quietly made `"spec:   " + clause + "   "` pass a comparison
    the rest of this file describes as byte for byte. A codex audit found it.
    `registry._check_citation` now refuses the padding at registration, so this
    slice is exact and the two layers agree about what a citation is.
    """
    return rule.source[len(rule.tier) + 2 :]


def test_every_clause_has_exactly_one_verdict(tier: str):
    """The keys of the two files are the same set, in both directions.

    A clause with no verdict is an unreviewed clause. A verdict with no clause
    is a verdict for a sentence the pin no longer has, which is how a moved pin
    announces that the adjudication needs redoing.
    """
    clause_ids = [clause["id"] for clause in index(tier)["clauses"]]
    assert len(clause_ids) == len(set(clause_ids)), f"{tier}: duplicate clause ids"
    assert set(verdicts(tier)["verdicts"]) == set(clause_ids)


def test_every_verdict_is_shaped_the_way_its_kind_requires(tier: str):
    """A rejection without a reason code is a shrug with a file name on it."""
    committed = verdicts(tier)
    codes = set(committed["reason_codes"])
    for clause_id, verdict in committed["verdicts"].items():
        where = f"{tier} {clause_id}"
        assert verdict["verdict"] in VERDICT_KINDS, where
        if verdict["verdict"] == "rejected":
            assert verdict["code"] in codes, where
            assert verdict["note"].strip(), where
        if verdict["verdict"] in CITING:
            assert verdict["rules"], where
            assert verdict["severity"] in ("ERROR", "WARNING"), where
        if verdict["verdict"] == "rule":
            assert len(verdict["rules"]) == 1, f"{where}: one rule enforces the whole sentence"
        if verdict["verdict"] in ("folded", "deferred"):
            assert verdict["note"].strip(), where


def test_a_verdicts_severity_agrees_with_its_clauses_modal_verb(tier: str):
    """Decision 4, as a build gate rather than a convention.

    The clause's own modal verb decides: `must`, `required`, `forbidden` and
    their neighbours give ERROR, `should`, `recommended` and `deprecated` give
    WARNING. A sentence that mixes both permits either, because such a clause is
    enforced by the half a rule chose to cite, and the index records both
    candidates rather than guessing. A sentence whose only modal grants a
    permission permits neither, so no rule can cite it.

    The two definitional clauses have no modal verb for this to read, so their
    permitted severity is the ERROR the index declares for them, which
    `test_clause_index.py` pins to that one value. The assertion below is the
    same either way, and it is deliberately not relaxed for them.
    """
    allowed = {clause["id"]: clause["severities"] for clause in index(tier)["clauses"]}
    for clause_id, verdict in verdicts(tier)["verdicts"].items():
        if verdict["verdict"] in CITING:
            assert verdict["severity"] in allowed[clause_id], (
                f"{tier} {clause_id} declares {verdict['severity']} for a sentence whose "
                f"modal verbs permit {allowed[clause_id]}"
            )


def test_no_rule_is_claimed_by_two_clauses_as_its_whole_citation(tier: str):
    """One rule, one `source=` string. A rule appearing under two `rule`
    verdicts would have two sentences claiming to be the one it quotes, and the
    verbatim check below could only ever match one of them."""
    whole = [
        rule
        for verdict in verdicts(tier)["verdicts"].values()
        if verdict["verdict"] == "rule"
        for rule in verdict["rules"]
    ]
    assert sorted(whole) == sorted(set(whole))


def test_every_registered_rule_cites_a_sentence_in_its_index(registered):
    """The verbatim check, over the real tree rather than over a fixture.

    Empty while `rules/spec/` and `rules/practice/` are empty, and that is the
    point of landing it before the first cohort: the first rule to paraphrase
    its clause fails on the commit that adds it, not three cohorts later.
    """
    texts = {name: {c["text"] for c in index(name)["clauses"]} for name in TIERS}
    for rule in registered:
        assert quoted_by(rule) in texts[rule.tier], (
            f"{rule.rule_id} in {rule.module} quotes a sentence that is not in "
            f"{TIERS[rule.tier][0].name}: {quoted_by(rule)!r}"
        )


def test_every_registered_rule_declares_the_severity_its_clause_permits(registered):
    """The other half: the quote resolves to a clause, and that clause's modal
    verb permits the severity the registration declares."""
    for rule in registered:
        permitted = {
            severity
            for clause in index(rule.tier)["clauses"]
            if clause["text"] == quoted_by(rule)
            for severity in clause["severities"]
        }
        assert rule.severity.name in permitted, (
            f"{rule.rule_id} declares {rule.severity.name} for a clause permitting {permitted}"
        )


def test_every_registered_rule_is_the_one_its_verdict_names(registered):
    """A rule may not appear from nowhere. Its id is in the verdict file, under
    the clause it quotes, which is what makes the verdict file a review of the
    proposed rule set rather than a record of what got written."""
    for rule in registered:
        committed = verdicts(rule.tier)["verdicts"]
        owning = {c["id"] for c in index(rule.tier)["clauses"] if c["text"] == quoted_by(rule)}
        assert [c for c in owning if rule.rule_id in committed[c].get("rules", [])], (
            f"{rule.rule_id} quotes a clause whose verdict does not name it"
        )


def test_every_cited_tier_records_its_whole_rule_set():
    """The verdict files are seeded from the decisions taken when each tier was
    designed rather than from the rules, so this compares the ids they name
    against the full proposed range, `S001` to `S052` and `P001` to `P015`.

    Every proposed id now has a clause. S012 and S050 quote a field
    description that fixes the field's value domain rather than stating an
    obligation, which is a third kind of clause rather than a scanner miss or a
    rejection; both are declared in the spec verdict file's `definitional` list
    and merged into the index by the generator, and
    `test_clause_index.py::test_declared_definitional_clauses_are_not_scanner_misses`
    holds the rules that slot obeys.

    **The spec tier ships 51, and S022 is the gap.** 52 were proposed, S022
    declaring no upstream overlap for `schedule_relationship = DUPLICATED` on a
    trip `frequencies.txt` gives `exact_times=0`, resting on the rule module's
    own sentence: "Nothing in the 56 reads DUPLICATED at all: it is post-2015
    and the 2015 descriptor has no member for it." True, and not the question,
    because E013 never reads the member by name.
    `rules/_shared/frequencies.py:129` gates E013's TripUpdate half on
    `exact_times_zero_trip_ids` alone and `rules/upstream/e013.py:68` fires on a
    `schedule_relationship` that is present and not `UNSCHEDULED`; `DUPLICATED`
    is 6, which is present and is not 2. So S022's trigger was a strict subset
    of E013's, measured over S022's own fixture in modern mode as
    `E013: 'trip_id T1 schedule_relationship DUPLICATED'` beside the S022 text.
    Compat could not have shown it: the 2015 enum lacks the member, so the jar's
    verdict on that fixture was W009 alone. A rule can be shadowed by an
    upstream rule that has never heard of the thing it checks. Clause `879#1` is
    re-adjudicated as rejected under **R6**, this file's code for "already
    checked by one of the 56", with the measurement in its note. R6 rather than
    the practice file's R1 because the two codebooks are not the same list: R1
    here is "It describes what a consumer does, not what a feed contains".

    **The practice tier ships 14, and P014 is the gap.** 15 were proposed, and
    P014's in-band fixture was measured to make the jar emit W009: that rule
    fires on `!hasScheduleRelationship()` for any TripDescriptor
    (`TripDescriptorValidator.java:470-474`) and
    `_shared/walk_trip_descriptor.py:141-142` calls it with none of the
    suppression its stop_time_update overload has, so P014's trigger was a
    strict subset of it. Clause `143#2` is re-adjudicated as rejected under R1
    with the measurement in its note. The id is not reused and P015 is not
    renumbered, so the gap stays lookup-able from a report code.
    """
    named = {
        name: {
            rule
            for verdict in verdicts(name)["verdicts"].values()
            if verdict["verdict"] in CITING
            for rule in verdict["rules"]
        }
        for name in TIERS
    }
    assert named["spec"] == {f"S{n:03d}" for n in range(1, 53)} - {"S022"}
    assert named["practice"] == {f"P{n:03d}" for n in range(1, 16)} - {"P014"}


@pytest.mark.parametrize(
    "source",
    [
        "spec:106#1",  # no space at all
        "spec:  106#1",  # two spaces
        "spec: 106#1 ",  # trailing padding
        "spec: \t106#1",  # a tab where the space should be
        "spec: 106#1\n",  # a trailing newline
        "spec: ",  # prefix and nothing else
        "spec:   ",  # prefix and whitespace
    ],
)
def test_a_citation_with_padding_is_refused_at_registration(source: str):
    """The gate says verbatim, so it has to mean verbatim.

    Registration used to accept any non-whitespace body after the prefix, and
    `quoted_by` then stripped before comparing, so a citation padded at either
    end passed a comparison this file describes as byte for byte. A codex audit
    found it. Neither layer strips now, and this pins the refusal so the two
    cannot drift apart again.

    Every one of these differs from a good citation only in bytes no reader would
    notice, which is exactly why a machine has to.
    """
    with pytest.raises(registry.RegistrationError, match="cite its source"):
        registry._check_citation("S999", "spec", source)


def test_the_exact_citation_is_accepted():
    """The negative cases above are worthless without this one: a gate that
    refuses everything would pass them all."""
    registry._check_citation("S999", "spec", "spec: 106#1")
    registry._check_citation("P999", "practice", "practice: some clause")


def test_every_registered_rule_cites_without_padding():
    """Over the real tree rather than a synthetic rule.

    `_check_citation` runs at registration, so this can only fail if a rule
    reached the registry another way. It is here because the suite has already
    been bitten by a guard that was proved with a synthetic and then stopped
    being the same claim once real modules existed.
    """
    registry.discover()
    for rule in registry.Registry.modern():
        if rule.tier not in registry.CITED_TIERS:
            continue
        prefix = f"{rule.tier}: "
        assert rule.source.startswith(prefix), rule.rule_id
        body = rule.source[len(prefix) :]
        assert body == body.strip() and body, rule.rule_id
