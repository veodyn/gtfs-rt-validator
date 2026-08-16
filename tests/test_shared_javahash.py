"""Java hash iteration order, one test per measured row, plus the refusal.

Every expected value here was **measured**, not computed by hand: the hash codes
come from a four-line Java program run under the same OpenJDK 17.0.19 the rest
of this project pins, and every iteration order comes from `tools/DumpHashOrder.java`
run under that JDK. `tools/diff_hashorder_against_java.py` re-runs the same
comparison over 48 generated cases; what is pinned here is the handful that
explain why each piece of the simulation exists, so a regression names the Java
behaviour it broke rather than just a diff.

The JDK version is part of the contract for the same reason it is in
`test_shared_javafmt.py`: `HashMap`'s constants and its resize and treeify
behaviour are implementation detail that upstream's output nevertheless depends
on, through `CrossFeedDescriptorValidator` and nothing else.

Nothing upstream asserts any of this. Its own `CrossFeedDescriptorValidatorTest`
counts occurrences and never looks at their order, so every assertion in this
file is ours.
"""

from __future__ import annotations

import itertools

import pytest

from gtfs_rt_validator.rules._shared.javahash import (
    MIN_TREEIFY_CAPACITY,
    TREEIFY_THRESHOLD,
    capacity_for,
    iteration_order,
    java_string_hash,
    spread,
)
from gtfs_rt_validator.rules.errors import RuleContractError
from jarcorpus import import_tool

#: Strings whose `hashCode()` values collide completely: `"Aa"` and `"BB"` hash
#: equal, so every concatenation of those blocks at one length hashes equal to
#: every other. The only practical way to reach a deep bucket.
COLLIDING = ["".join(parts) for parts in itertools.product(["Aa", "BB"], repeat=4)]


def unsigned(value: int) -> int:
    """The 32-bit pattern Java prints as a signed `int`."""
    return value & 0xFFFFFFFF


# ---------------------------------------------------------------------------
# String.hashCode, measured
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "java_hash_code"),
    [
        ("", 0),
        ("a", 97),
        ("Aa", 2112),
        ("BB", 2112),
        ("1.1", 48564),
        ("45", 1665),
        ("100", 48625),
        ("trip_0", -865465706),
        # `Integer.MIN_VALUE` exactly, which is the case a simulation that
        # forgot to wrap gets wrong in the most invisible way.
        ("polygenelubricants", -2147483648),
        ("café", 3045921),
        ("\U0001f600emoji", -1233692477),
    ],
)
def test_the_hash_is_javas_own_over_utf16_code_units(text, java_hash_code):
    """Measured under JDK 17.0.19. The astral case is the point of the last row:
    `String.hashCode` runs over UTF-16 code *units*, so one emoji contributes
    its two surrogates separately and a port over code points differs."""
    assert java_string_hash(text) == unsigned(java_hash_code)


def test_two_blocks_that_java_hashes_alike_hash_alike_here():
    assert java_string_hash("Aa") == java_string_hash("BB")


@pytest.mark.parametrize(
    ("text", "java_spread"),
    [
        ("trip_0", -865417476),
        ("polygenelubricants", -2147450880),
        ("café", 3045903),
        ("\U0001f600emoji", -1233654092),
    ],
)
def test_the_spread_is_h_xor_h_unsigned_shifted_16(text, java_spread):
    """`HashMap.hash`, measured the same way. The unsigned shift is what makes
    a negative hash spread differently than an arithmetic shift would."""
    assert spread(java_string_hash(text)) == unsigned(java_spread)


# ---------------------------------------------------------------------------
# Iteration order, measured against a real HashMap and HashSet
# ---------------------------------------------------------------------------

#: Case to measured order, from `tools/DumpHashOrder.java` under JDK 17.0.19.
#: The `MAP` and `SET` lines were identical for every one of these, as they were
#: for all 48 cases the tool generates.
MEASURED = {
    # Upstream's own `CrossFeedDescriptorValidatorTest` builds this set: two
    # VehiclePositions with no trip_id, so W003 loop 4 iterates it.
    "two vehicle ids": (["45", "100"], ["45", "100"]),
    "two trip ids": (["1", "2"], ["1", "2"]),
    "two more vehicle ids": (["45", "46"], ["45", "46"]),
    "testagency trip ids": (["1.1", "1.2", "1.3"], ["1.1", "1.2", "1.3"]),
    # Reordered, and the reordering is the whole reason this module exists.
    "mixed ids in one bucket": (["100", "101", "44", "45"], ["44", "100", "45", "101"]),
    "thirteen keys, past the first resize": (
        [f"trip_{i}" for i in range(13)],
        [
            "trip_12",
            "trip_11",
            "trip_10",
            "trip_4",
            "trip_5",
            "trip_2",
            "trip_3",
            "trip_8",
            "trip_9",
            "trip_6",
            "trip_7",
            "trip_0",
            "trip_1",
        ],
    ),
    "non-BMP and accented": (
        ["café", "naïve", "日本語", "\U0001f600emoji", "trip_1"],
        ["\U0001f600emoji", "naïve", "日本語", "trip_1", "café"],
    ),
    # Eight and nine keys in one bucket still iterate in insertion order:
    # `treeifyBin` needs a ninth entry in the bin *and* a table of 64.
    "eight fully colliding keys": (COLLIDING[:8], COLLIDING[:8]),
    "nine fully colliding keys": (COLLIDING[:9], COLLIDING[:9]),
}


@pytest.mark.parametrize("case", sorted(MEASURED), ids=sorted(MEASURED))
def test_the_order_is_the_one_a_real_hashmap_produced(case):
    keys, expected = MEASURED[case]

    assert list(iteration_order(keys)) == expected


def test_a_repeated_key_keeps_the_position_of_its_first_insertion():
    """`put` on a key already present replaces the value and leaves the node
    where it is, so a duplicate cannot move anything."""
    assert iteration_order(["100", "101", "100", "44", "45"]) == ("44", "100", "45", "101")


def test_no_keys_is_no_order():
    assert iteration_order([]) == ()


# ---------------------------------------------------------------------------
# Capacity, including the resize `treeifyBin` forces
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("count", "capacity"),
    [(0, 16), (1, 16), (12, 16), (13, 32), (24, 32), (25, 64), (48, 64), (49, 128)],
)
def test_the_table_doubles_when_size_passes_three_quarters_of_it(count, capacity):
    """`if (++size > threshold) resize()`, threshold `capacity * 0.75`. Twelve
    keys fit in 16 and the thirteenth does not."""
    assert capacity_for([f"trip_{i}" for i in range(count)]) == capacity


def test_a_deep_bucket_resizes_the_table_below_the_treeify_capacity():
    """`treeifyBin` resizes *instead of* treeifying while the table is shorter
    than `MIN_TREEIFY_CAPACITY`, so nine colliding keys leave a table of 32
    where the size alone would have said 16. That is a second divergence source
    on top of the tree's own ordering, and it is why capacity cannot be
    computed from the key count."""
    assert capacity_for(COLLIDING[:8]) == 16
    assert capacity_for(COLLIDING[:9]) == 32


# ---------------------------------------------------------------------------
# The refusal
# ---------------------------------------------------------------------------


def test_a_bucket_that_java_would_treeify_is_refused_rather_than_guessed():
    """Sixteen fully colliding keys: the ninth entry in the bin resizes to 32,
    the tenth to 64, and the eleventh finds a table at `MIN_TREEIFY_CAPACITY`
    and builds a red-black tree. A real `HashMap` then iterates that bin by hash
    and `Comparable` order, which this project does not reproduce. Measured: the
    JVM returns `AaAaBBBB` first, and a chain simulation returns `AaAaAaAa`."""
    with pytest.raises(RuleContractError, match="red-black tree"):
        iteration_order(COLLIDING)


def test_the_refusal_names_the_bucket_and_the_depth_that_caused_it():
    with pytest.raises(RuleContractError) as raised:
        iteration_order(COLLIDING)

    assert "16 keys" in str(raised.value)
    assert f"capacity {MIN_TREEIFY_CAPACITY}" in str(raised.value)


def test_capacity_refuses_on_the_same_condition():
    with pytest.raises(RuleContractError):
        capacity_for(COLLIDING)


def test_the_threshold_is_javas_own_two_constants():
    assert (TREEIFY_THRESHOLD, MIN_TREEIFY_CAPACITY) == (8, 64)


def test_a_deep_bucket_in_a_long_table_is_refused_wherever_it_was_inserted():
    """The padded cases the tool generates: the colliding block first or last
    makes no difference, because the bin is what treeifies."""
    padding = [f"pad_{i}" for i in range(40)]
    for keys in (COLLIDING + padding, padding + COLLIDING):
        with pytest.raises(RuleContractError):
            iteration_order(keys)


# ---------------------------------------------------------------------------
# One implementation, not two
# ---------------------------------------------------------------------------


def test_the_differential_tool_uses_this_module_rather_than_its_own_copy():
    """The tool is the wide comparison against a running JVM; if it held its own
    simulation, the thing measured and the thing shipped could drift apart
    silently."""
    tool = import_tool("diff_hashorder_against_java")

    assert tool.iteration_order is iteration_order
