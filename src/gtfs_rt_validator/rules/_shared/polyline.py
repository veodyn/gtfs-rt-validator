"""Google's Encoded Polyline Algorithm Format, decoded. Read by S040 and P015.

The pinned proto declares `Shape.encoded_polyline` and says at `:1110` that it
"must contain at least two points", which cannot be checked without decoding it.
The format is documented and self-contained, so this is the one new algorithm
the spec tier needs:

  https://developers.google.com/maps/documentation/utilities/polylinealgorithm

A value is multiplied by 1e5 and rounded, zigzag-encoded so the sign lands in
the low bit, then split into five-bit groups, low group first, with 0x20 set on
every group but the last and 63 added to each. Values are deltas from the
previous point, and the first point's delta is from zero. Decoding is that
backwards, and the accumulation is in integers rather than floats: adding
`0.00001` steps in binary floating point drifts, and adding hundred-thousandths
as integers and dividing once does not.

**A broken polyline is a finding, never an exception.** Feeds are expected to be
malformed, so this answers a `Polyline` carrying whatever decoded plus the
reason it stopped, and S040 turns that into an occurrence. `error` is diagnostic
detail for a rule to use or ignore; the occurrence text belongs to the rule.

**The memo is keyed on the encoded string**, not on the message, because a feed
may carry many `Shape` entities and two rules read each of them. `memoised`
takes the string in the message's place and repeats it as the scope, which is
what keeps the second shape from being handed the first one's points.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from gtfs_rt_validator.rules._shared.memo import memoised

if TYPE_CHECKING:  # Type-only: nothing under `rules/` may import the runner at
    # run time, because it reaches the static layer and so the sibling.
    from gtfs_rt_validator.runner.context import RuleContext

__all__ = ["Polyline", "decode_polyline", "polyline"]

#: What the format adds to every five-bit group, so that the result is a
#: printable ASCII character.
OFFSET = 63

#: Set on every group but the last of a value.
CONTINUATION = 0x20

#: The largest value a valid encoded character carries. Six bits, so `?` (63)
#: through `~` (126) once `OFFSET` is added back.
HIGHEST = 0x3F

#: Hundred-thousandths: the format's fixed precision, and the reason a decoded
#: coordinate is not the producer's original number to more places than this.
SCALE = 100_000


@dataclass(frozen=True, slots=True)
class Polyline:
    """The points that decoded, and why decoding stopped if it did.

    `points` holds what was read before the failure rather than nothing, so a
    rule can say how far a broken string got. `error` is `None` for a string
    that decoded whole, including the empty string, which is zero points and no
    defect: an absent `encoded_polyline` is S039's finding and a short one is
    S040's, and neither is this module's.
    """

    points: tuple[tuple[float, float], ...]
    error: str | None = None


def polyline(encoded: str, ctx: RuleContext) -> Polyline:
    """`encoded`, decoded at most once per context however many rules read it."""
    return memoised(_build, encoded, ctx, scope=encoded)


def _build(encoded: str, ctx: RuleContext) -> Polyline:
    return decode_polyline(encoded)


def decode_polyline(encoded: str) -> Polyline:
    """Every `(latitude, longitude)` the string carries, in order."""
    points: list[tuple[float, float]] = []
    latitude = longitude = 0
    position = 0
    while position < len(encoded):
        latitude_delta, position, error = _value(encoded, position)
        if error is not None:
            return Polyline(tuple(points), error)
        if position >= len(encoded):
            return Polyline(tuple(points), "a latitude with no longitude after it")
        longitude_delta, position, error = _value(encoded, position)
        if error is not None:
            return Polyline(tuple(points), error)
        latitude += latitude_delta
        longitude += longitude_delta
        points.append((latitude / SCALE, longitude / SCALE))
    return Polyline(tuple(points))


def _value(encoded: str, position: int) -> tuple[int, int, str | None]:
    """One zigzag-encoded delta, in hundred-thousandths, and where it ended."""
    result = shift = 0
    while position < len(encoded):
        group = ord(encoded[position]) - OFFSET
        position += 1
        # Both ends, and the upper one is not decoration. The algorithm adds 63
        # to a six-bit value, so a valid character is ASCII 63 to 126, `?` to
        # `~`. Checking only the lower end let anything above `~` through, where
        # `group & 0x1f` quietly discarded the high bits: `chr(127)` decoded as
        # a clean 0 and `(chr(127) + "?") * 2` answered as a valid two-point
        # polyline at the origin, which is exactly the shape a minimum-points
        # rule is looking for. Found by a codex audit.
        if not 0 <= group <= HIGHEST:
            return 0, position, f"character {encoded[position - 1]!r} is not part of the encoding"
        result |= (group & (CONTINUATION - 1)) << shift
        shift += 5
        if not group & CONTINUATION:
            # The low bit is the sign, which is why a negative value is
            # complemented rather than negated: -1 encodes as 1, not as -2.
            return (~(result >> 1) if result & 1 else result >> 1), position, None
    return 0, position, "a value ran off the end of the string"
