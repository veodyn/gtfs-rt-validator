"""The three `TripProperties` fields a DUPLICATED trip must carry, in one place.

S013 and S014 are the two directions of one sentence, which the proto writes
three times, once on each field: "Required if schedule_relationship=DUPLICATED,
otherwise this field must not be populated and will be ignored by consumers."
S013 reports the fields a DUPLICATED trip left out and S014 the fields a trip
that is not DUPLICATED filled in, so both need the same three names and the same
presence test over the same message. That is what lives here.

The order is the fields' own declaration order (`:392`, `:395`, `:409`), so two
rules reporting on one trip name them the same way round.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from gtfs_rt_validator.proto.decode import Msg
    from gtfs_rt_validator.rules._shared.schedule_relationship import TripRelationship

__all__ = ["FIELDS", "MESSAGE", "missing", "path", "populated", "properties"]

#: `TripUpdate.trip_properties`, the message both rules read.
MESSAGE = "trip_properties"

#: The three fields the sentence is written on, in declaration order.
FIELDS = ("trip_id", "start_date", "start_time")


def properties(record: TripRelationship) -> Msg:
    """This trip's `TripProperties`, or the default instance for none at all.

    An absent submessage answers a default instance whose every field is absent,
    which is the right answer for both readers: a DUPLICATED trip with no
    `trip_properties` at all is missing all three, and a trip that is not
    DUPLICATED has populated none.
    """
    return record.owner.get(MESSAGE)


def path(record: TripRelationship) -> str:
    """Where the `trip_properties` sit, for an occurrence's `entityPath`.

    The walk's own path ends at the descriptor, since that is what it walked, so
    the last segment comes off and this one goes on. Both rules report against
    the properties rather than the descriptor, because that is the message the
    field they name lives in.
    """
    return f"{record.path.removesuffix('.trip')}.{MESSAGE}"


def populated(record: TripRelationship) -> tuple[str, ...]:
    """Which of the three this trip states, in declaration order."""
    declared = properties(record)
    return tuple(name for name in FIELDS if declared.has(name))


def missing(record: TripRelationship) -> tuple[str, ...]:
    """Which of the three this trip omits, in declaration order."""
    declared = properties(record)
    return tuple(name for name in FIELDS if not declared.has(name))
