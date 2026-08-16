"""How many rules each tier is meant to have, and why each number is that number.

Split out of `tests/test_completeness.py`, which asserts against these and had
grown past the file-size hook once the second retired rule earned its paragraph.
The seam is the one the hook suggests and the one the two halves already had:
this module is the committed statement, that one is the check that reads it.

**Nothing here is derived and nothing here may be.** A marker computed from the
tree it exists to protect would agree with the tree after a deletion, which is
the one moment it exists for. Each number moves in exactly the commit that moves
the tree, and the prose beside it is why a gap in an id range is a decision
rather than an oversight.
"""

from __future__ import annotations

__all__ = [
    "WRITTEN_CITED_RULES",
    "WRITTEN_COMPAT_RULES",
    "WRITTEN_PRACTICE_RULES",
    "WRITTEN_SPEC_RULES",
]

#: How many of the 56 batch-reachable rules this tree is known to have written.
#: The committed half of the completeness gate, and the only thing that survives
#: `rm -r rules/upstream/*.py` to say that they were there.
#:
#: It ratchets, and the gate is an equality rather than a floor, so the number
#: moves in exactly the commit that moves the tree: landing rules without
#: raising it fails, and raising it without landing them fails too. Nothing
#: derives it, on purpose. A marker computed from the tree it is meant to
#: protect would agree with the tree after a deletion, which is the one moment
#: it exists for.
WRITTEN_COMPAT_RULES = 56

#: The same ratchet for the two cited tiers, which have no manifest to bound
#: them: `data/rules.json` is generated from upstream's Java and cannot grow an
#: `S` or `P` id, so this is the *only* committed statement of how many rules
#: each tier is meant to have. The `spec` tier was designed at 52 rules and the
#: `practice` tier at 15; the commit that lands a cohort of them raises the
#: number in the same diff, so progress is a reviewable integer rather than a
#: judgement call about how full a directory looks.
#:
#: 51 and not 52, and the missing one is `S022` rather than the last id, for the
#: same reason and by the same call as `P014` below. S022 was designed for
#: `schedule_relationship = DUPLICATED` on a trip `frequencies.txt` gives
#: `exact_times=0`, declaring no overlap with any upstream rule on the strength
#: of its own sentence: "Nothing in the 56 reads DUPLICATED at all: it is
#: post-2015 and the 2015 descriptor has no member for it." True, and not the
#: question. E013 never reads the member by name. `rules/_shared/frequencies.py:129` gates its
#: TripUpdate half on `exact_times_zero_trip_ids` alone and `e013.py:68` fires
#: on a `schedule_relationship` that is present and not `UNSCHEDULED`;
#: `DUPLICATED` is 6, which is present and is not 2. So S022's trigger was a
#: strict subset of E013's and every S022 occurrence arrived beside an E013 one.
#: Measured over S022's own fixture in modern mode:
#: `E013: 'trip_id T1 schedule_relationship DUPLICATED'` beside
#: `S022: 'trip_id T1 is DUPLICATED but frequencies.txt gives it exact_times=0'`.
#: Compat could not have shown it: the 2015 enum has no `DUPLICATED`, so the jar
#: reads the field as absent and its verdict on that fixture is W009 alone. A
#: rule can be shadowed by an upstream rule that has never heard of the thing it
#: checks. Retired rather than shipped with a permanent exemption from
#: `tests/test_tier_overlap.py`. The id is not reused and nothing is renumbered,
#: so that this sentence stays findable from the gap.
WRITTEN_SPEC_RULES = 51

#: 14 and not 15, and the missing one is `P014` rather than the last id. P014
#: was designed for an `exact_times=0` trip with no `schedule_relationship`, as
#: a band E013 cannot reach. The band against E013 is real, and one jar invocation
#: per case proved it: the field absent produced W009, present and SCHEDULED
#: produced E013, present and UNSCHEDULED produced nothing. But W009 fires on
#: `!hasScheduleRelationship()` for *any* TripDescriptor
#: (`TripDescriptorValidator.java:470-474`), and
#: `rules/_shared/walk_trip_descriptor.py:141-142` calls it with none of the
#: whole-feed suppression its stop_time_update overload has, so P014's trigger
#: was a strict subset of W009's and no feed shape escaped it. Retired rather
#: than shipped with a permanent exemption from the tier overlap invariant. The
#: id is not reused and P015 is not renumbered, so that this sentence stays
#: findable from the gap.
WRITTEN_PRACTICE_RULES = 14

#: Keyed by tier so the gate below reads it rather than naming either constant,
#: which is what keeps a third cited tier from being silently unratcheted.
WRITTEN_CITED_RULES = {"spec": WRITTEN_SPEC_RULES, "practice": WRITTEN_PRACTICE_RULES}
