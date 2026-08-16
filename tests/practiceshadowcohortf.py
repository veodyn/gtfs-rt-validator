"""Cohort F's jar fixtures: alert scope (P012) and vehicle geometry (P015).

Split out of `practiceshadowfeeds.py` for the reason that file was split out of
`practiceshadow.py`, so neither grows past the size hook. Same contract: every
`jar_ids` set here was **recorded from a real jar run** rather than predicted,
and `tests/test_practice_tier_does_not_shadow_the_jar.py`'s docstring says what
one entry has to carry.

**Both rules' claims are stronger here than a fixture usually gets, and for the
same reason: the jar cannot see either defect.**

- P012 declares no upstream overlap, and none of the 56 asks a route which stops
  it serves. Measured: the jar emits nothing over an Alert naming every stop of
  R1.
- P015 declares E029, which is the rule that would have answered. The violating
  fixture is a vehicle sitting on the shape `shapes.txt` carries whose trip has
  **published another one**, so E029 clears the position it can measure and
  cannot read the `Shape` entity at all: both `Shape` and `TripModifications`
  postdate the 2015 schema the jar decodes with. Measured: the jar emits nothing.
  Its `fires=False` twin is the converse and is the more interesting of the two,
  because the jar *does* emit E029 there and this rule stands down, which is "no
  vehicle is reported twice" as a measurement rather than as a paragraph.
"""

from __future__ import annotations

from p015fixtures import encode_polyline
from practiceshadow import CLOCK, Fixture, Message, as_vehicle

__all__ = ["P012_FIXTURES", "P015_FIXTURES"]

#: A shape 554 metres north of where the one trip's vehicle sits, encoded the way
#: a `Shape` entity carries one.
REPUBLISHED = encode_polyline([(27.955, -82.45), (27.956, -82.45)])

#: 735.6 metres from the trip shape and still inside the agency box, measured
#: rather than eyeballed. E029's own ground.
BEYOND_E029: dict[str, object] = {"latitude": 27.98, "longitude": -82.43}


def alerting(*stop_ids: str, route_id: str | None = None) -> tuple[Message, ...]:
    """One Alert naming stops, one selector each, and optionally their route."""
    selectors: list[dict[str, object]] = [{"stop_id": stop_id} for stop_id in stop_ids]
    if route_id is not None:
        selectors.insert(0, {"route_id": route_id})
    return (Message(CLOCK, [{"id": "alert", "alert": {"informed_entity": selectors}}]),)


def republished() -> tuple[Message, ...]:
    """A vehicle on `shapes.txt`'s shape whose trip published another one."""
    selected = {"selected_trips": [{"trip_ids": ["T1"], "shape_id": "RT1"}]}
    return (
        Message(
            CLOCK,
            [
                as_vehicle("a"),
                {"id": "b", "trip_modifications": selected},
                {"id": "c", "shape": {"shape_id": "RT1", "encoded_polyline": REPUBLISHED}},
            ],
        ),
    )


P012_FIXTURES = (
    Fixture("P012", "every stop of the route, one selector each", alerting("S1", "S2")),
    Fixture(
        "P012",
        "one stop short of the route",
        alerting("S1"),
        fires=False,
        note="the conformant twin, and the whole of the rule's threshold",
    ),
    Fixture(
        "P012",
        "every stop and the route as well",
        alerting("S1", "S2", route_id="R1"),
        fires=False,
        note="the shape the clause asks for instead",
    ),
)

P015_FIXTURES = (
    Fixture(
        "P015",
        "a realtime Shape the jar cannot read",
        republished(),
        not_emitted="E029",
        note="554 metres from the shape its own trip published and on the one shapes.txt "
        "carries, so E029 clears it and the jar says nothing at all",
    ),
    Fixture(
        "P015",
        "outside E029's own buffer",
        (Message(CLOCK, [as_vehicle("a", position=BEYOND_E029)]),),
        fires=False,
        jar_ids=frozenset({"E029"}),
        note="the converse case: the jar reports E029 and this rule stands down. "
        "`not_emitted` is None because E029 firing is this case's point rather than "
        "its refutation",
    ),
    Fixture("P015", "on the shape", (Message(CLOCK, [as_vehicle("a")]),), fires=False),
)
