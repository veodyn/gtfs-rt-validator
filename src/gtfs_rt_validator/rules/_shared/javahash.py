"""Java's `HashMap` iteration order, reproduced, and refused where it cannot be.

`CrossFeedDescriptorValidator` is the only validator whose *output bytes* depend
on the order a Java hash container iterates in, and upstream emits whatever
order it is handed. Everywhere else Java's hash structures are used for
membership only and their order never escapes.

**Four iteration sites, not six containers.** That validator constructs six
hash-backed containers at `CrossFeedDescriptorValidator.java:64-76`, and all six
look at first as though they need this. Only four are ever iterated, and only
those four reach output:

    tripUpdatesTripIdToVehicleId        :125   W003 loop 1, and E047's TU side
    vehiclePositionsVehicleIdToTripId   :138   W003 loop 2, and E047's VP side
    tripsWithoutVehicles                :151   W003 loop 3
    vehiclesWithoutTrips                :159   W003 loop 4

`tripUpdatesVehicleIdToTripId` and `vehiclePositionsTripIdToVehicleId` are
reached only through `containsKey` and `get` (`:126, :134, :139, :147, :152,
:160`), so their order is not observable and simulating it would be work with
no output to check it against.

**This is measured, not reasoned.** `tools/diff_hashorder_against_java.py` runs
this simulation against a real JVM through `tools/DumpHashOrder.java`, over 48
generated cases: realistic trip and vehicle ids at every size that crosses a
resize threshold up to 216 keys, non-BMP characters, and deliberate full-hash
collisions. Under OpenJDK 17.0.19 on arm64, 41 agree and 7 disagree, and the 7
are the large colliding sets. The orders themselves are pinned in
`tests/test_shared_javahash.py`. Two consequences worth knowing before touching
anything here:

- the simulation is exact for every realistic id set, to 216 keys and including
  non-BMP characters, and
- `HashMap` and `HashSet` iterated identically in every case, so one simulation
  serves both and the two maps and two sets above need no separate treatment. A
  `HashSet` *is* a `HashMap` with a shared dummy value, so this is what the
  source says too; the measurement is what makes it a fact here.

**The pieces.** `String.hashCode` is `h = 31*h + c` over UTF-16 code units;
`HashMap.hash` spreads it with `h ^ (h >>> 16)`; the bucket is `hash & (n-1)`;
the table starts at 16 and doubles when size passes `capacity * 0.75`. Iteration
walks the bucket array in index order and each bucket's chain in insertion
order, and `resize` preserves relative order within each split chain, so sorting
by `(bucket index at the final capacity, insertion index)` is equivalent to
replaying every resize.

**Why this refuses.** Once a bin holds nine entries and the table is at least
`MIN_TREEIFY_CAPACITY` long, `HashMap` converts that bin to a red-black tree and
iterates it by hash and then `Comparable` order instead of by insertion. Two
things then diverge at once, because `treeifyBin` *resizes instead of
treeifying* while the table is shorter than that, so the final capacity can also
exceed what the key count alone implies. Reproducing the tree is a large amount
of code whose only validation would be a hostile fixture, and a wrong order is
invisible in a unit test and fatal in a byte comparison. So `capacity_for`
follows `putVal` and `treeifyBin` closely enough to know when a bin would
actually become a tree, and raises there.

`RuleContractError` is the exception because this is not a finding about a feed
and not a decode failure: it says a container in this repository was handed a
key set it does not serve, which is the case `rules/errors.py` describes.

**The refusal surface is wider than "ids sharing a `hashCode`".** Java treeifies
on bin depth rather than on hash equality, so nine ids with nine *distinct*
spread hashes that happen to land in one bin of a 64-long table reach it too,
which was reproduced against OpenJDK 17. It takes an unlucky bin rather than a
hostile fixture. Real ids do not seem to find one: a snapshot of MBTA
TripUpdates and VehiclePositions with 2,006 vehicles drove 611 W003 and 3 E047
calls through `iteration_order` at capacity 1024, well past the 64 floor, and no
bin reached nine.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable

from gtfs_rt_validator.rules.errors import RuleContractError

__all__ = [
    "INITIAL_CAPACITY",
    "LOAD_FACTOR",
    "MIN_TREEIFY_CAPACITY",
    "TREEIFY_THRESHOLD",
    "capacity_for",
    "iteration_order",
    "java_string_hash",
    "spread",
]

#: 32-bit two's complement, which is what Java's `int` arithmetic wraps to.
MASK = 0xFFFFFFFF

#: `HashMap.DEFAULT_INITIAL_CAPACITY` and `DEFAULT_LOAD_FACTOR`. Every container
#: in `CrossFeedDescriptorValidator` is built with the no-argument constructor.
INITIAL_CAPACITY = 16
LOAD_FACTOR = 0.75

#: `HashMap.TREEIFY_THRESHOLD` and `MIN_TREEIFY_CAPACITY`.
TREEIFY_THRESHOLD = 8
MIN_TREEIFY_CAPACITY = 64


def java_string_hash(text: str) -> int:
    """`String.hashCode`: `h = 31*h + c`, as the unsigned 32-bit pattern.

    Over UTF-16 code *units*, not code points, so an astral character
    contributes its two surrogates separately. Returned unsigned because every
    caller here goes on to mask it; the value is the same bit pattern Java
    prints as a signed `int`.
    """
    result = 0
    utf16 = text.encode("utf-16-be")
    for index in range(0, len(utf16), 2):
        unit = (utf16[index] << 8) | utf16[index + 1]
        result = (31 * result + unit) & MASK
    return result


def spread(hashed: int) -> int:
    """`HashMap.hash`: `h ^ (h >>> 16)`, an unsigned shift.

    Java's table is a power of two, so without this only the low bits of a hash
    would ever pick a bucket. Python's `>>` on a non-negative int is already the
    unsigned shift `>>>` is, which is why `java_string_hash` returns unsigned.
    """
    return (hashed ^ (hashed >> 16)) & MASK


def _distinct(keys: Iterable[str]) -> tuple[str, ...]:
    """The keys a `HashMap` would hold, in the order it would hold them.

    `put` on a key already present replaces the value and leaves the node where
    it is, so a repeated key keeps the position of its first insertion. That is
    `dict.fromkeys`.
    """
    return tuple(dict.fromkeys(keys))


def capacity_for(keys: Iterable[str]) -> int:
    """The table length after inserting these keys, following `putVal`.

    Not `capacity from size alone`: `treeifyBin` calls `resize()` whenever a bin
    reaches nine entries while the table is shorter than `MIN_TREEIFY_CAPACITY`,
    so a colliding set can leave a table longer than its size implies. That
    forced resize is why this walks the insertions instead of dividing.

    Raises `RuleContractError` on the insertion that would build a red-black
    tree, because the order past that point is not this module's to state.
    """
    distinct = _distinct(keys)
    hashes = [spread(java_string_hash(key)) for key in distinct]
    capacity = INITIAL_CAPACITY
    depths: Counter[int] = Counter()
    for position, hashed in enumerate(hashes, start=1):
        index = hashed & (capacity - 1)
        depths[index] += 1
        # `putVal` appends, then treeifies when `binCount >= TREEIFY_THRESHOLD - 1`.
        # `binCount` counts the nodes walked past, so the bin holds nine.
        if depths[index] > TREEIFY_THRESHOLD:
            if capacity >= MIN_TREEIFY_CAPACITY:
                raise RuleContractError(
                    f"{len(distinct)} keys put {depths[index]} of themselves in bucket {index} of "
                    f"a table of capacity {capacity}, which is where java.util.HashMap converts "
                    f"that bucket to a red-black tree and stops iterating it in insertion order. "
                    f"This project simulates the chain and refuses the tree rather than emit a "
                    f"plausible wrong order; see rules/_shared/javahash.py"
                )
            capacity, depths = _resized(capacity, hashes[:position])
        if position > capacity * LOAD_FACTOR:
            capacity, depths = _resized(capacity, hashes[:position])
    return capacity


def _resized(capacity: int, hashes: list[int]) -> tuple[int, Counter[int]]:
    """`resize()`: double the table and rehash what is in it.

    Recomputing the depths is not how Java does it (it splits each chain in
    place, into a lo and a hi list) but it is the same partition, and only the
    depths matter here.
    """
    doubled = capacity * 2
    return doubled, Counter(hashed & (doubled - 1) for hashed in hashes)


def iteration_order(keys: Iterable[str]) -> tuple[str, ...]:
    """These keys in the order a `HashMap` or `HashSet` would iterate them.

    Bucket index at the final capacity, then insertion order within a bucket.
    Raises `RuleContractError` for a key set that would treeify a bin; see the
    module docstring for why refusing beats guessing.
    """
    distinct = _distinct(keys)
    capacity = capacity_for(distinct)
    ordered = sorted(
        (spread(java_string_hash(key)) & (capacity - 1), index, key)
        for index, key in enumerate(distinct)
    )
    return tuple(key for _, _, key in ordered)
