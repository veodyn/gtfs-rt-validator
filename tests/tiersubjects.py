"""What counts as "the same thing" when two rules both report.

Split out of `tieroverlap.py`, which owns the other half of that module's job,
the corpus. The seam is the one the two halves already had: this decides the
join key, that decides which messages are joined.

## The subject

**A subject is the narrowest identity an occurrence names, inside one message.**
Both tiers spell that identity the same way, and not by accident: `prefix` is
upstream's occurrence prefix, built by `rules/_shared/ids.py`, which is a port
of `util/GtfsUtils.java`, and the cited tiers write their prefixes in the same
vocabulary. So `trip_id 76329436`, `vehicle.id y1340`, `vehicle_id y1340`,
`entity ID empty` and `alert ID no-informed-entity` are the five spellings, and
they are what this module parses.

Reading the identity out of the prefix rather than out of `context` is a
deliberate choice with one reason: `ENTITY_PATH_KEY` is set by 3 of the 56
upstream rule modules (E038, E039 and E049) and by every cited-tier one, so a
context-based key would be unjoinable on the upstream side. The prefix is the
only vocabulary both tiers share.

The subject is scoped by source file, so two occurrences about the same trip in
two different messages are two subjects. `SOURCE_FILE_KEY` is stamped on every
occurrence by `runner/context.py`, so this needs no cooperation from a rule.
"""

from __future__ import annotations

import re

from gtfs_rt_validator.report.occurrence import SOURCE_FILE_KEY, NoticeContainer

__all__ = ["MESSAGE", "subject_of", "subjects"]

#: Five spellings, one vocabulary. `vehicle[._]id` covers both `vehicle.id`,
#: which `GtfsUtils.java:226` spells with a dot, and `vehicle_id`, which the
#: cross-feed rules spell with an underscore.
_TRIP = re.compile(r"\btrip_id (\S+)")
_VEHICLE = re.compile(r"\bvehicle[._]id \"?([^\"\s]+)")
_ENTITY = re.compile(r"\b(?:entity ID|alert ID) (\S+)")

#: What an occurrence naming no trip, vehicle or entity is about: the message
#: itself. Every header rule lands here, P004 and W007 included, which is what
#: makes the band assertion joinable at all.
MESSAGE = ("message",)


def subject_of(prefix: str) -> tuple[str, ...]:
    """The narrowest identity `prefix` names, or `MESSAGE` if it names none.

    Narrowest first: a trip beats a vehicle, because an occurrence naming both
    (E047's `vehicle_id X and trip_id Y pairing`) is about the trip instance.
    An identifier that is present but empty produces two spaces and matches
    nothing here, which is correct: `vehicle_id  trip_id ` names no subject.
    """
    trip = _TRIP.search(prefix)
    if trip:
        return ("trip", trip.group(1))
    vehicle = _VEHICLE.search(prefix)
    if vehicle:
        return ("vehicle", vehicle.group(1))
    entity = _ENTITY.search(prefix)
    if entity:
        return ("entity", entity.group(1))
    return MESSAGE


def subjects(notices: NoticeContainer) -> dict[str, set[tuple[str, ...]]]:
    """`{rule_id: the subjects it fired on}` for one run.

    Keyed by `(source file, identity)`, so the same trip in two messages is two
    subjects and a rule that fires on every message of a replay does not thereby
    dominate one that fires on a single entity of one.
    """
    found: dict[str, set[tuple[str, ...]]] = {}
    for rule_id, occurrences in notices.grouped().items():
        found[rule_id] = {
            (str(occurrence.context.get(SOURCE_FILE_KEY, "?")), *subject_of(occurrence.prefix))
            for occurrence in occurrences
        }
    return found
