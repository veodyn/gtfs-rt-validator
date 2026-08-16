"""What order the modern writer promises, and what order it deliberately does not.

The module docstring used to say two runs that found the same things in a
different sequence produce the same file. That was true of the entry order and
false of everything inside an entry, and the only test behind it rebuilt one
fixed construction twice, which cannot tell the two apart.

**The position taken, of the two available: sample order is meaningful.** An
entry's samples are the first N found, in the order the run walked its messages
and its entities, and a sample's keys are in the order the rule built its
context. Both carry information. Sorting the samples would throw away "these are
the first two of fourteen, in feed order" and buy an invariance the run does not
need; sorting a context's keys would scatter a rule's own field order, which is
the sibling's declared-field order and Gson's on the far side of it. Upstream
and the sibling both keep discovery order inside a group, and under `--compat`
upstream wins by default; there is no reason for modern to differ here.

Rule *entries* are the other case and are sorted, because which rule fired first
is an artefact of the runner's walk rather than a fact about the feed, and a set
of codes has no order of its own to lose.

So the promise is: **the same sequence of occurrences produces the same bytes,
and the entry order survives a permutation of that sequence.** No more. The
tests below pin both halves, and three of them fail under the other reading:
they assert that permuting the occurrences *does* change the samples and that a
context's keys come back unsorted.
"""

from __future__ import annotations

from gtfs_rt_validator.report import modern
from gtfs_rt_validator.report.occurrence import NoticeContainer, Occurrence
from modernrun import a_run, a_summary, occurrence

#: Deliberately not in sorted order, and not in `Occurrence` field order either.
#: A rule builds its context in the order that reads best for the rule.
CONTEXT_KEYS = ("tripId", "stopSequence", "arrivalTime", "delaySeconds", "routeId")


def entries(container: NoticeContainer) -> list[dict]:
    return modern.build_report(container, a_summary())["notices"]


def containing(rule_ids: tuple[str, ...]) -> NoticeContainer:
    container = NoticeContainer()
    for rule_id in rule_ids:
        container.add(Occurrence(rule_id, "p", {}))
    return container


def test_the_entry_order_is_sorted_whatever_order_the_rules_fired_in():
    """Ordering is a contract, not an accident of which rule fired first."""
    forwards = containing(("E002", "E019", "W002"))
    backwards = containing(("W002", "E019", "E002"))
    assert [entry["code"] for entry in entries(forwards)] == ["E002", "E019", "W002"]
    assert entries(forwards) == entries(backwards)


def test_the_writer_never_parses_an_id_so_the_s_and_p_tiers_sort_with_the_rest():
    """`E`, `W`, `S` and `P` sort as whole strings by code point, so a tier with
    no rules written yet is not a special case in the sort either."""
    container = containing(("W002", "S001", "P001", "E002"))
    assert modern.ordered_ids(container) == ("E002", "P001", "S001", "W002")


def test_samples_keep_discovery_order_within_a_rule():
    samples = entries(a_run())[0]["sampleNotices"]
    assert [sample["stopSequence"] for sample in samples] == [0, 1]


def test_permuting_the_occurrences_permutes_the_samples_and_that_is_the_point():
    """The negative half of the promise, and the test that fails if anyone
    sorts the samples: a report says which two of the fourteen were found
    first, so two runs that walked the feed differently say different things.
    """
    forwards, backwards = NoticeContainer(), NoticeContainer()
    for index in (0, 1, 2):
        forwards.add(occurrence("E002", index))
    for index in (2, 1, 0):
        backwards.add(occurrence("E002", index))
    assert [entry["code"] for entry in entries(forwards)] == [
        entry["code"] for entry in entries(backwards)
    ]
    assert [s["stopSequence"] for s in entries(forwards)[0]["sampleNotices"]] == [0, 1, 2]
    assert [s["stopSequence"] for s in entries(backwards)[0]["sampleNotices"]] == [2, 1, 0]


def test_a_samples_keys_stay_in_the_order_the_rule_built_them():
    """The other test that fails under the canonical reading. A context is a
    rule's own field order, so the writer moves the prefix to the front and
    then touches nothing."""
    container = NoticeContainer()
    container.add(Occurrence("E002", "p", dict.fromkeys(CONTEXT_KEYS, "x")))
    sample = entries(container)[0]["sampleNotices"][0]
    assert tuple(sample) == (modern.PREFIX_KEY, *CONTEXT_KEYS)
    assert tuple(sample) != tuple(sorted(sample))


def test_the_same_sequence_of_occurrences_produces_the_same_bytes():
    """The promise itself, over a sequence built twice rather than a container
    serialised twice: the assembly is a pure function of what it was handed."""
    assert modern.dumps_json(modern.build_report(a_run(), a_summary())) == modern.dumps_json(
        modern.build_report(a_run(), a_summary())
    )
