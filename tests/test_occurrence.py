"""The occurrence model: what a rule appends, and what a container does with it.

Four behaviours are pinned here, and the first is the reason the type exists.

1. Upstream's JSON stores the prefix and the occurrence suffix in separate
   fields; there is no concatenated one. So an `Occurrence` carries the prefix
   and nothing else of the message, and the suffix is looked up from the rule
   manifest at write time.
2. A container never reorders what it was given. `report/compat.py` owns the
   full cross-rule ordering contract; this layer only promises not to scramble.
3. Sample caps follow the sibling's `NoticeContainer`: the count is the true
   total, the retained list is a sample.
4. Adding never raises. Feeds are expected to be malformed; that is the product.
"""

from __future__ import annotations

import dataclasses

from gtfs_rt_validator.report.occurrence import (
    ENTITY_PATH_KEY,
    MAX_EXPORTS_PER_RULE,
    MAX_OCCURRENCES_PER_RULE,
    MAX_TOTAL_OCCURRENCES,
    SOURCE_FILE_KEY,
    NoticeContainer,
    Occurrence,
)

# upstream/rules-7041fa3.json, E002. The suffix belongs to the manifest, never
# to the occurrence, and this test module is the only place it is written down.
E002_SUFFIX = "is not strictly sorted by increasing stop_sequence"


def an_occurrence(rule_id: str = "E002", prefix: str = "trip_id 277716 stop_sequence 4"):
    return Occurrence(rule_id=rule_id, prefix=prefix, context={"tripId": "277716"})


def test_the_prefix_is_stored_and_the_suffix_is_not():
    occ = an_occurrence()
    assert occ.rule_id == "E002"
    assert occ.prefix == "trip_id 277716 stop_sequence 4"
    assert occ.context == {"tripId": "277716"}


def test_no_field_holds_the_joined_message():
    """The concatenation trap. The join is how a human reads it, not a field."""
    occ = an_occurrence()
    joined = f"{occ.prefix} {E002_SUFFIX}"

    serialised = dataclasses.asdict(occ)
    assert joined not in serialised.values()
    for value in serialised.values():
        assert E002_SUFFIX not in repr(value)
    assert E002_SUFFIX not in repr(occ)
    assert not any(E002_SUFFIX in repr(getattr(occ, name)) for name in dir(occ))


def test_context_carries_the_source_file_and_the_entity_path():
    """A run spans many messages, so a sample has to say which one it came from."""
    occ = Occurrence(
        rule_id="E022",
        prefix="trip_id 277716",
        context={
            SOURCE_FILE_KEY: "archive/2026-08-14T10:00:00Z.pb",
            ENTITY_PATH_KEY: "entity[3].trip_update.stop_time_update[1]",
            "stopSequence": 4,
        },
    )
    assert occ.context[SOURCE_FILE_KEY].endswith(".pb")
    assert occ.context[ENTITY_PATH_KEY].startswith("entity[3]")


def test_adding_never_raises_whatever_the_occurrence_holds():
    """Notices are data. A malformed feed is the input, not an error condition."""
    recursive: dict[str, object] = {}
    recursive["self"] = recursive
    container = NoticeContainer()
    container.add(Occurrence("", "", {}))
    container.add(Occurrence("E002", "\x00퟿ bad prefix", {"bytes": b"\xff", "n": None}))
    container.add(Occurrence("W003", "", recursive))
    assert len(container.in_order()) == 3


def test_ordering_within_a_rule_is_insertion_order():
    container = NoticeContainer()
    prefixes = [f"trip_id {n}" for n in range(20)]
    for prefix in prefixes:
        container.add(Occurrence("E002", prefix, {}))
    assert [occ.prefix for occ in container.grouped()["E002"]] == prefixes


def test_interleaved_rules_keep_both_their_own_and_the_global_order():
    container = NoticeContainer()
    order = ["E002", "W003", "E002", "E022", "W003", "E002"]
    for index, rule_id in enumerate(order):
        container.add(Occurrence(rule_id, str(index), {}))

    assert [occ.rule_id for occ in container.in_order()] == order
    grouped = container.grouped()
    assert [occ.prefix for occ in grouped["E002"]] == ["0", "2", "5"]
    assert [occ.prefix for occ in grouped["W003"]] == ["1", "4"]


def test_grouped_keys_are_sorted_like_the_siblings():
    """The sibling sorts its grouping keys; compat output order is upstream's
    validator registration order, set in `report/compat.py`, not this."""
    container = NoticeContainer()
    for rule_id in ("W003", "E022", "E002"):
        container.add(Occurrence(rule_id, "", {}))
    assert list(container.grouped()) == ["E002", "E022", "W003"]


def test_the_total_survives_capping():
    """A report saying 14 while holding 3 samples is the whole point of the shape."""
    container = NoticeContainer(max_per_rule=3)
    for n in range(14):
        container.add(Occurrence("E002", f"trip_id {n}", {}))

    assert container.count_for("E002") == 14
    assert container.retained_for("E002") == 3
    assert container.dropped_for("E002") == 11
    assert [occ.prefix for occ in container.grouped()["E002"]] == [
        "trip_id 0",
        "trip_id 1",
        "trip_id 2",
    ]


def test_the_total_cap_stops_retention_without_stopping_the_count():
    container = NoticeContainer(max_total=2)
    for n in range(5):
        container.add(Occurrence("E002", str(n), {}))
    for n in range(3):
        container.add(Occurrence("W003", str(n), {}))

    assert len(container.in_order()) == 2
    assert container.count_for("E002") == 5
    assert container.count_for("W003") == 3
    assert container.dropped_for("W003") == 3


def test_observe_dropped_moves_the_count_without_retaining():
    container = NoticeContainer()
    container.add(Occurrence("E002", "kept", {}))
    container.observe_dropped("E002", count=13)

    assert container.count_for("E002") == 14
    assert container.retained_for("E002") == 1
    assert [occ.prefix for occ in container.in_order()] == ["kept"]


def test_merge_sums_the_counts_rather_than_recomputing_them():
    """Sibling parity: forwarding only retained occurrences would undercount."""
    worker = NoticeContainer(max_per_rule=1)
    for n in range(9):
        worker.add(Occurrence("E002", str(n), {}))

    container = NoticeContainer()
    container.add(Occurrence("E002", "first", {}))
    container.merge(worker)

    assert container.count_for("E002") == 10
    assert [occ.prefix for occ in container.in_order()] == ["first", "0"]


def test_count_for_a_rule_that_never_fired_is_zero():
    container = NoticeContainer()
    assert container.count_for("E002") == 0
    assert container.retained_for("E002") == 0
    assert container.dropped_for("E002") == 0
    assert container.grouped() == {}


def test_samples_are_capped_separately_from_retention():
    container = NoticeContainer(max_exports_per_rule=2)
    for n in range(6):
        container.add(Occurrence("E002", str(n), {}))

    assert [occ.prefix for occ in container.samples_for("E002")] == ["0", "1"]
    assert container.retained_for("E002") == 6
    assert container.count_for("E002") == 6


def test_add_all_is_add_repeated():
    container = NoticeContainer(max_per_rule=2)
    container.add_all(Occurrence("E002", str(n), {}) for n in range(4))
    assert container.count_for("E002") == 4
    assert container.retained_for("E002") == 2


def test_the_caps_are_the_siblings_numbers():
    container = NoticeContainer()
    assert (MAX_TOTAL_OCCURRENCES, MAX_OCCURRENCES_PER_RULE, MAX_EXPORTS_PER_RULE) == (
        10_000_000,
        100_000,
        1_000,
    )
    assert container.max_total == MAX_TOTAL_OCCURRENCES
    assert container.max_per_rule == MAX_OCCURRENCES_PER_RULE
    assert container.max_exports_per_rule == MAX_EXPORTS_PER_RULE


def test_rule_ids_are_reported_even_when_nothing_was_retained():
    container = NoticeContainer(max_total=0)
    container.add(Occurrence("E002", "", {}))
    assert container.rule_ids() == ("E002",)
    assert container.in_order() == ()
