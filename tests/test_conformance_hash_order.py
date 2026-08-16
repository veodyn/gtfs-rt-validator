"""What the hash-order golden proves, and the one boundary it does not reach.

`bullrunner/22-crossfeed-many.pb` exists because `CrossFeedDescriptorValidator`
is the only validator whose *output order* comes out of Java `HashMap`
iteration, and no golden before this corpus put more than one key in an iterated
container. `tools/conf_vehicles.py` builds it and explains the pairing; this
module asserts what the jar wrote for it, without needing a jar.

**Two claims, and the second is the one that matters.** The occurrence counts
are exact, so a regenerated corpus that lost occurrences fails here rather than
passing a lower bound. And the ids the second W003 loop printed are asserted to
be, in order, what `rules/_shared/javahash.iteration_order` produces for a table
of capacity 128: the jar's own output is the oracle for the simulation, above
`MIN_TREEIFY_CAPACITY` rather than below it.

**The refusal boundary is not covered by any differential, here or elsewhere.**
`javahash` raises `RuleContractError` rather than guessing once a bin would hold
nine entries and the table is at least `MIN_TREEIFY_CAPACITY` long, which needs
ids that collide completely under `String.hashCode`. The jar emits the
red-black tree's order for those and this project refuses, so a feed built to
reach it would be a permanent red diff rather than a passing comparison.
`tests/test_shared_javahash.py` is the only cover that branch has, and saying so
is the point of this paragraph: before the corpus grew, every container in this
file simulated to capacity 32, and a reader could reasonably have thought the
floor was exercised.
"""

from __future__ import annotations

import json

import conformancecorpus as corpus
from gtfs_rt_validator.rules._shared.javahash import (
    MIN_TREEIFY_CAPACITY,
    capacity_for,
    iteration_order,
)
from jarcorpus import import_tool

#: How many entities `22-crossfeed-many.pb` puts on each side, and so how many
#: keys the one iterated map that can grow against this archive holds.
CROSSFEED_ENTITIES = import_tool("conf_vehicles").CROSSFEED_ENTITIES

#: Exactly what the jar wrote for `22-crossfeed-many.pb`, counted from the
#: golden. Exact, because a lower bound accepts a corpus that lost occurrences.
CROSSFEED_OCCURRENCES = {"W003": 75, "E047": 15, "E029": 44, "E045": 52}


def _crossfeed_w003() -> list[str]:
    """The subject of every W003 occurrence in `22-crossfeed-many.pb`, in order.

    Upstream's message is `<field> <id> is in <feed> but not in <feed> feed`, so
    the second word is the key or value the loop was holding, and the order is
    the order the `HashMap` handed them over.
    """
    blob = corpus.goldens("bullrunner")["22-crossfeed-many.pb"]
    assert blob is not None
    entry = next(
        each
        for each in json.loads(blob)
        if each["errorMessage"]["validationRule"]["errorId"] == "W003"
    )
    return [occurrence["prefix"].split()[1] for occurrence in entry["occurrenceList"]]


def test_one_golden_carries_the_occurrences_hash_order_is_observable_in():
    """W003 and E047 come out of Java `HashMap` iteration, and no golden before
    this corpus put more than one key in an iterated container.

    Exact counts, not lower bounds. Bounds of 20 and 10 against a golden of 75
    and 15 would accept a regenerated corpus that had lost three quarters of its
    W003 occurrences, which is the one thing this check exists to catch.
    """
    counts = {
        entry["errorMessage"]["validationRule"]["errorId"]: len(entry["occurrenceList"])
        for entry in json.loads(corpus.goldens("bullrunner")["22-crossfeed-many.pb"])
    }
    assert counts == CROSSFEED_OCCURRENCES


def test_the_iterated_table_the_jar_walked_is_past_the_treeify_capacity():
    """The property the occurrence *count* alone does not pin.

    `javahash` behaves differently once the table reaches `MIN_TREEIFY_CAPACITY`:
    below it a deep bin resizes, at or above it the bin becomes a red-black tree
    and the module refuses. With 20 entities per half every container in this
    file simulated to capacity 32, so no golden here ever came from a table at or
    past that floor and the branch was covered by unit tests alone.

    The 60 vehicle ids the second W003 loop walks put the table at 128, and the
    order they come out in is the order `iteration_order` reproduces, so the
    simulation is checked against the jar above the floor rather than below it.
    """
    walked = _crossfeed_w003()
    from_trip_updates = [each for each in walked if each.startswith("tuVeh")]
    from_vehicle_positions = [each for each in walked if each.startswith("vpVeh")]

    assert len(from_vehicle_positions) == CROSSFEED_ENTITIES
    assert capacity_for(from_vehicle_positions) == 128 > MIN_TREEIFY_CAPACITY
    assert tuple(from_vehicle_positions) == iteration_order(
        [f"vpVeh{index}" for index in range(CROSSFEED_ENTITIES)]
    )
    # Loop 1 walks the trip-keyed map and prints its *values*. Fifteen keys is
    # every trip `bullrunner-gtfs.zip` defines, so that table stays at 32.
    trips = [str(number) for number in range(1, 16)]
    assert capacity_for(trips) == 32
    assert len(from_trip_updates) == len(trips)
