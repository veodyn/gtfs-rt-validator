"""The stop_time_update half of `TimestampValidator`'s pass: E001, E022, E025.

`TimestampValidator.java:172-265`, split out of `walk_timestamp.py` by the
file-size hook. The seam is a real one: everything here is about two values
carried between stops of one trip, and everything in the other half is about one
entity at a time.

**E022 is eight independent `if`s**, not four comparisons with a merged
less-than-or-equal. Four of them run when this stop_time_update carried an
arrival (`:193-213`) and four when it carried a departure (`:226-245`), and one
stop_time_update can fire all eight. Each block asks about its own field first
and the other field second, less-than before equal-to, which is what
`_comparisons` is.

**The carry-forward is conditional** (`:256-263`): `previousArrivalTime`
advances only when *this* stop_time_update had an arrival, and likewise for
departures. So "previous stop" means "the most recent stop that had this
field", and a comparison reaches back past a stop_time_update that carried only
the other one. Carrying both forward unconditionally, or merging the two
relations, changes several of the ten rows `TimestampValidatorTest.testE022`
pins, which is why `tests/test_rule_e022.py` ports all ten.

**E025 is within one stop**, never across two, and it is emitted after that
stop's four departure comparisons (`:246-253`).
"""

from __future__ import annotations

from collections.abc import Iterator

from gtfs_rt_validator.proto.decode import Msg
from gtfs_rt_validator.rules._shared.times import is_posix
from gtfs_rt_validator.rules._shared.timestamp_pass import Pass, at
from gtfs_rt_validator.rules._shared.timestamp_text import (
    EQUAL_TO,
    LESS_THAN,
    clock_and_value,
    departure_before_arrival,
    not_increasing,
    stop_description,
)
from gtfs_rt_validator.rules._shared.walks import Event

__all__ = ["ARRIVAL", "DEPARTURE", "stop_time_update_events"]

#: The two field names, as upstream spells them in occurrence text.
ARRIVAL = "arrival_time"
DEPARTURE = "departure_time"


def stop_time_update_events(
    trip_update: Msg, trip_id: str, index: int, run: Pass
) -> Iterator[Event]:
    """One TripUpdate's stop_time_updates, in list order. State resets per trip."""
    previous_arrival: int | None = None
    previous_departure: int | None = None
    for position, stop_time_update in enumerate(trip_update.get("stop_time_update")):
        where = trip_id + stop_description(stop_time_update)
        path = at(f"entity[{index}].trip_update.stop_time_update[{position}]")
        arrival = _event_time(stop_time_update, "arrival")
        departure = _event_time(stop_time_update, "departure")
        if arrival is not None:
            yield from _field_events(
                arrival, previous_arrival, previous_departure, ARRIVAL, DEPARTURE, where, path, run
            )
        if departure is not None:
            yield from _field_events(
                departure,
                previous_departure,
                previous_arrival,
                DEPARTURE,
                ARRIVAL,
                where,
                path,
                run,
            )
            if arrival is not None and departure < arrival:
                yield Event(
                    "E025",
                    departure_before_arrival(
                        where,
                        clock_and_value(departure, run.timezone),
                        clock_and_value(arrival, run.timezone),
                    ),
                    path,
                )
        # `:256-263`, after both blocks and only for the field this stop had.
        if arrival is not None:
            previous_arrival = arrival
        if departure is not None:
            previous_departure = departure


def _event_time(stop_time_update: Msg, name: str) -> int | None:
    """`hasArrival() && arrival.hasTime()`, as the `Long` upstream keeps.

    `None` stands for Java's `null`, and the difference between `None` and 0 is
    what makes the carry-forward conditional. A `StopTimeEvent` present but
    carrying only a delay leaves the value null, exactly as here.
    """
    if stop_time_update.has(name) and stop_time_update.get(name).has("time"):
        return stop_time_update.get(name).get("time")
    return None


def _field_events(
    value: int,
    same_previous: int | None,
    other_previous: int | None,
    field: str,
    other_field: str,
    where: str,
    path: dict[str, object],
    run: Pass,
) -> Iterator[Event]:
    """One E001 test then four E022 tests, for whichever of the two fields this is.

    The arrival block and the departure block are the same eight lines with the
    two carried values swapped, which is why they are written once. The order
    inside each is the Java's: own field less-than, own field equal-to, other
    field less-than, other field equal-to.
    """
    if not is_posix(value):
        yield Event("E001", f"{where} {field} {value}", path)
    moment = clock_and_value(value, run.timezone)
    for relation, previous_field, previous in _comparisons(
        value, same_previous, other_previous, field, other_field
    ):
        yield Event(
            "E022",
            not_increasing(
                where,
                field,
                moment,
                relation,
                previous_field,
                clock_and_value(previous, run.timezone),
            ),
            path,
        )


def _comparisons(
    value: int,
    same_previous: int | None,
    other_previous: int | None,
    field: str,
    other_field: str,
) -> Iterator[tuple[str, str, int]]:
    """The four E022 tests, in upstream's order, skipping the ones with no previous.

    Written as four separate tests rather than one three-way comparison because
    upstream writes four: `<` and `Objects.equals` are asked independently, and a
    merged `<=` would collapse two distinct occurrence texts into one.
    """
    if same_previous is not None and value < same_previous:
        yield LESS_THAN, field, same_previous
    if same_previous is not None and value == same_previous:
        yield EQUAL_TO, field, same_previous
    if other_previous is not None and value < other_previous:
        yield LESS_THAN, other_field, other_previous
    if other_previous is not None and value == other_previous:
        yield EQUAL_TO, other_field, other_previous
