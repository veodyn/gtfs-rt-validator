"""The declared overlap of every cited rule, asserted over the whole corpus.

`test_spec_tier_does_not_shadow_the_jar.py` and
`test_practice_tier_does_not_shadow_the_jar.py` ask the jar one crafted feed at
a time: this feed is S016's, and the jar says nothing, or says only what the
rule declared. This module is the complementary question, and it catches
an overlap nobody thought to build a fixture for: **run the modern registry over
every message available and look at what fired beside what.**

## The unit of co-occurrence: the subject

A subject is `(message, the narrowest identity the occurrence names)`, and
`tiersubjects.subject_of` is what reads it out of the occurrence prefix. Two
occurrences co-occur when they name the same trip, the same vehicle or the same
entity inside the same message. Two rules firing on different entities of one
message are not an overlap and are not counted as one.

## Why the literal reading of the invariant is not what is asserted

Both cited tiers were built to an invariant worded "no single entity produced
both an `S` occurrence and an upstream occurrence whose id the rule did not
declare as an overlap", and the same for `P`. Taken literally, at subject
granularity, that is **false over any real feed, and false by a wide margin**:
measured over this corpus, 169 distinct `(cited, upstream)` pairs fire on some
shared subject.
Almost all of them are two independent defects on one broken trip. A trip whose
predictions are stale (P008) is also a trip whose `stop_sequence` repeats
(E036), whose `stop_id` does not match GTFS (E045) and whose vehicle is off its
shape (E029); none of that says P008 restates any of them. Asserting the literal
form would need an exemption list the size of that set, and this test may not
have one. The number is a measurement at one corpus and moves when the corpus
does: it was 168 before a fourth agency was recorded. Nothing ratchets it, on
purpose, because the claim under test is the shape of the failure and not its
count.

**So the assertion is the one the literal form was reaching for: domination.**
An overlap that matters is a cited rule whose occurrences are *always*
accompanied by the same undeclared upstream occurrence on the same subject.
That is exactly the shape P014 had and was retired for: its trigger,
`TripDescriptor.schedule_relationship` absent on an `exact_times=0` trip, was a
strict subset of W009's, which fires on an absent `schedule_relationship` for
any descriptor, so no feed could produce P014 without W009. Co-firing once is
noise; co-firing on every subject a rule ever had is a rule reporting something
already reported.

**It has caught two rules, and both were retired rather than exempted.** P014
was the first, before this module existed, on the crafted-fixture evidence
`test_practice_tier_does_not_shadow_the_jar.py` carries. S022 was the second and
the first this module found on its own: `schedule_relationship = DUPLICATED` on
a trip `frequencies.txt` gives `exact_times=0`, which declared no overlap at all
on the strength of the rule's own sentence, "Nothing in the 56 reads DUPLICATED
at all: it is post-2015 and the 2015 descriptor has no member for it". True, and
not the question. `rules/_shared/frequencies.py:129` gates E013's TripUpdate
half on `exact_times_zero_trip_ids` alone and `e013.py:68` fires on a
`schedule_relationship` that is present and not `UNSCHEDULED`; `DUPLICATED` is
6, and E013 never reads the member by name. **A rule can be shadowed by an
upstream rule that has never heard of the thing it checks**, which is the
sentence worth carrying away, and it is also why no differential could have
found this: the 2015 enum has no `DUPLICATED`, so the jar's verdict on S022's
own fixture was W009 alone.

## The honest limit of the formulation

**Domination catches narrowing into another rule's shadow. It does not catch
broadening.** Measured while proving this module has teeth: redirecting
`p013.py`'s predicate to E013's was caught on the first run, and simply dropping
P013's `delay` condition, which widens it to every event of a frequency trip,
was not, because the wider rule still fires on subjects E013 does not reach. A
rule that grows until it reports half a feed is a real defect and this test is
blind to it; `tests/fixtures/agencies/*-tier-counts.json` is the ratchet that is
not, and the two are complementary rather than redundant.

## The allow-list, and why it has two halves

Neither half is invented at assertion time. Both are committed data, so a
changed declaration or a re-measured fixture has one place to land:

1. `OVERLAP` below. It is the record itself, not a copy of one kept elsewhere:
   each entry carries, as a comment, the sentence written when the rule was
   designed saying why it does not restate the upstream rule it borders on. A
   cited rule absent from `OVERLAP` declares no overlap.
2. The `jar_ids` recorded on the rule's own shadow fixture in
   `specshadowfeeds.py` or `practiceshadowfeeds.py`. A fixture that provokes an
   upstream rule alongside its own records it there with a note saying why; S020
   is the worked example, whose duplicate trip is absent from `trips.txt` by
   construction and so draws E003 and W003. Reusing that record is not an
   exemption invented here, it is the tier's own measurement.

**This test must never grow a third half.** An id it flags that neither
`OVERLAP` nor a fixture accounts for is a finding about a rule, not a gap in the
allow-list. When a rule's overlap genuinely changes, because its predicate was
deliberately widened or an upstream rule was re-read, edit that rule's entry in
`OVERLAP` and rewrite its comment to the sentence that now justifies the border.
When no such sentence can honestly be written, retire the rule. P014 is the
precedent: it was removed rather than exempted.

## What is not covered

A domination claim is only as good as the corpus. A cited rule that fired on one
subject in one crafted fixture supports a very weak one, and this test says so
by reporting how many subjects each rule had rather than hiding it: a rule that
fires nowhere is skipped and named, because an empty set is a subset of
everything and would flag every upstream rule at once.
"""

from __future__ import annotations

import pytest

import tieroverlap
import tiersubjects
from gtfs_rt_validator.rules.registry import Registry
from practiceshadowfeeds import FIXTURES as PRACTICE_FIXTURES
from specshadowfeeds import FIXTURES as SPEC_FIXTURES
from test_practice_tier_does_not_shadow_the_jar import blobs

#: The declared overlap of each cited rule, by rule id. A rule absent from this
#: mapping declares none; the ids here are the upstream ground it was designed
#: to border on, and the comment above each entry is the sentence that justifies
#: the border. A rule whose near miss was worth explaining in prose but which
#: borders on nothing is deliberately absent rather than mapped to an empty set.
OVERLAP: dict[str, frozenset[str]] = {
    # "E043 requires *one*; this requires *both*."
    "S006": frozenset({"E043"}),
    # "E013 reads the *trip's* schedule_relationship, never the update's."
    "S007": frozenset({"E013"}),
    # "E011 checks `StopTimeUpdate.stop_id`, a different field."
    "S012": frozenset({"E011"}),
    # "E016's inverse."
    "S015": frozenset({"E016"}),
    # "E040 accepts `stop_id` **or** `stop_sequence` ... W006 warns
    # about the missing `trip_id` and stops there."
    "S018": frozenset({"E040", "W006"}),
    # "E044 accepts `delay` **or** `time`; here only `time` will do."
    "S019": frozenset({"E044"}),
    # "E047 pairs ids between feeds; this pairs a `trip_id` against
    # a *different field* on the other side."
    "S020": frozenset({"E047"}),
    # "E003 and E016 branch **on** `ADDED` without ever objecting to it."
    "S024": frozenset({"E003", "E016"}),
    # "E033 requires *a* specifier; this requires a *companion*."
    "S030": frozenset({"E033"}),
    # "E040 is the same shape on a different message."
    "S042": frozenset({"E040"}),
    # "E011, on a different message and with a wider resolution set."
    "S043": frozenset({"E011"}),
    # "E011, same note as S043."
    "S046": frozenset({"E011"}),
    # "E015 is the same predicate on `StopTimeUpdate.stop_id`."
    "S047": frozenset({"E015"}),
    # "E021 is the same predicate on `TripDescriptor.start_date`."
    "S050": frozenset({"E021"}),
    # "E038 checks *validity* ... E048 and E049 gate *on* v2."
    "P001": frozenset({"E038", "E048", "E049"}),
    # "E052 owns the *unique* half within one message."
    "P003": frozenset({"E052"}),
    # "W007, in the disjoint band above 35."
    "P004": frozenset({"W007"}),
    # "E041 requires *some* stop_time_update."
    "P008": frozenset({"E041"}),
    # "E029, whose degree buffer is not 200 metres."
    "P015": frozenset({"E029"}),
}

#: The one entry that declares a **disjoint band** rather than neighbouring
#: ground: P004 owns 31 to 35 seconds and W007 owns everything above it, so the
#: two may never fire on one message. That is a pairwise claim, stronger than
#: the domination test below, and this is where it is stated.
#:
#: One pair, not two. P014 and E013 were proposed as the second; P014 was
#: retired for the reason this module's docstring gives, and
#: `practiceshadowfeeds.IN_BAND` carries the measurement.
DISJOINT_BANDS = (("P004", "W007"),)


def recorded_upstream_ids() -> dict[str, frozenset[str]]:
    """The `jar_ids` each cited rule's own shadow fixture records.

    The second half of the allow-list. Unioned across a rule's fixtures, because
    the band rules have several and each records its own verdict.
    """
    found: dict[str, frozenset[str]] = {}
    for fixture in (*SPEC_FIXTURES, *PRACTICE_FIXTURES):
        found[fixture.rule_id] = found.get(fixture.rule_id, frozenset()) | fixture.jar_ids
    return found


def allowed_for(rule_id: str) -> frozenset[str]:
    return OVERLAP.get(rule_id, frozenset()) | recorded_upstream_ids().get(rule_id, frozenset())


@pytest.fixture(scope="session")
def corpus(tmp_path_factory) -> dict[str, set[tuple[str, ...]]]:
    """`{rule_id: every subject it fired on}` over the whole available corpus.

    Built once for the session: the agency half loads an 18 MB static feed and
    the conformance half replays 30 messages, and every assertion here reads the
    same run.
    """
    tmp = tmp_path_factory.mktemp("tier-overlap")
    runs = [
        *tieroverlap.conformance_runs(tmp / "conformance"),
        *tieroverlap.fixture_runs(tmp / "fixtures", blobs),
        *tieroverlap.agency_runs(tmp / "agencies"),
    ]
    fired: dict[str, set[tuple[str, ...]]] = {}
    for name, notices in runs:
        for rule_id, seen in tiersubjects.subjects(notices).items():
            fired.setdefault(rule_id, set()).update((name, *subject) for subject in seen)
    return fired


CITED = sorted(rule_id for rule_id in Registry.modern().ids() if rule_id[0] in ("S", "P"))

#: Why the recorded agency feeds cannot be read here, or the empty string.
#:
#: **The domination assertion is gated on them and the gate is not a
#: convenience.** Measured: without the agency corpus the crafted feeds are the
#: only evidence, and S024 then looks dominated by E013 for the sole reason that
#: the one fixture it fires on is a frequency-based trip. With the corpus it
#: fires on 510 subjects across two real feeds and the domination disappears. A
#: claim that a rule *always* co-occurs with another cannot be made from a
#: corpus of one message per rule, so it is skipped rather than guessed at.
AGENCIES_MISSING = tieroverlap.agencies_missing()
needs_agencies = pytest.mark.skipif(
    bool(AGENCIES_MISSING), reason=AGENCIES_MISSING or "the recorded agency feeds are here"
)


def test_the_allow_list_names_rules_that_exist():
    """A spelling check on `OVERLAP`, which is hand-maintained and is the only
    thing here a typo could silently weaken: a key that is not a cited rule, or
    a value that is not one of the 56, would quietly widen the allow-list for
    nothing."""
    registered = set(Registry.modern().ids())
    compat = set(Registry.compat().ids())

    assert set(OVERLAP) <= set(CITED)
    assert {name for names in OVERLAP.values() for name in names} <= compat
    assert {name for pair in DISJOINT_BANDS for name in pair} <= registered


def test_the_corpus_is_the_one_the_module_docstring_describes(corpus):
    """A run that read nothing would pass every assertion below. This is what
    says it read something, and how much."""
    assert tieroverlap.message_count() >= 30
    assert len([rule_id for rule_id in corpus if rule_id[0] in ("S", "P")]) >= 20


@needs_agencies
@pytest.mark.parametrize("rule_id", CITED)
def test_no_cited_rule_is_shadowed_by_an_upstream_rule_it_did_not_declare(rule_id, corpus):
    """The invariant. See the module docstring for the unit and the allow-list.

    A rule that never fired is skipped rather than passed: the empty set is a
    subset of every upstream rule's, so an unexercised rule would otherwise
    report every one of the 56 at once, which is the opposite of a finding.
    """
    subjects = corpus.get(rule_id, set())
    if not subjects:
        pytest.skip(f"{rule_id} fired nowhere in the corpus, so it dominates nothing")
    allowed = allowed_for(rule_id)
    shadows = sorted(
        upstream
        for upstream, seen in corpus.items()
        if upstream[0] in ("E", "W") and upstream not in allowed and subjects <= seen
    )

    assert shadows == [], (
        f"{rule_id} fired on {len(subjects)} subjects and every one of them also carries "
        f"{shadows}, which `OVERLAP` does not name and no fixture records. Either the "
        f"rule restates one of them, as P014 restated W009, or its `OVERLAP` entry is wrong."
    )


@pytest.mark.parametrize(("cited", "upstream"), DISJOINT_BANDS)
def test_a_declared_band_never_shares_a_subject_with_its_neighbour(cited, upstream, corpus):
    """The strong form, for the one rule that claims a disjoint band rather than
    neighbouring ground. This one is plain co-occurrence with no allow-list in
    it at all: if P004 and W007 ever fire on the same message the band split is
    a paragraph rather than a fact, and the band fixtures are what make the
    claim non-vacuous here."""
    shared = sorted(corpus.get(cited, set()) & corpus.get(upstream, set()))

    assert corpus.get(cited), f"{cited} fired nowhere, so this claim proves nothing"
    assert corpus.get(upstream), f"{upstream} fired nowhere, so this claim proves nothing"
    assert shared == [], f"{cited} and {upstream} both fired on {shared}"
