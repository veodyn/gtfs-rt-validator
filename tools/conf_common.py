"""What every tier 1 feed against `bullrunner-gtfs.zip` shares.

**The timeline is the point of the sequence, not decoration.** Upstream stamps
input `i` with mtime `MTIME_BASE + i` and reads that mtime as the validation
clock, so every header timestamp in the corpus is written here as an offset from
`MTIME_BASE` and the *age* it implies is what W008, E050 and W007 see. The safe
window is `[mtime - 65, mtime + 60]`: older is W008, further ahead is E050.
Feeds that are not about timestamps sit 30 seconds old, in the middle of it, so
they say nothing about the clock.

**Why `bullrunner-gtfs.zip`.** It is upstream's own Apache-2.0 test archive and
the only vendored feed with real geometry, 1,522 shape points across six routes,
which is what makes E028 and E029 more than a two-point toy. Two of its
properties are load-bearing:

- trip `1` visits stop_id `222` at stop_sequence 1 **and** 25, which is the only
  reason E009 is reachable at all, and
- every one of its 15 trips is in `frequencies.txt` with `exact_times = 0`, so
  `FrequencyTypeZeroValidator` runs for every feed in the group. That is why
  `QUIET` carries a start_date, a start_time and `UNSCHEDULED`: without them
  every file would also carry E006, E013 and W005, and no file would be about
  one thing.

Its `frequencies.txt` has `headway_secs` of 540 to 720 and `exact_times = 0`
throughout, so nothing in this group can reach `FrequencyTypeOneValidator`'s
measured infinite spin, which needs `exact_times = 1` with `headway_secs = 0`.
"""

from __future__ import annotations

from feedbuild import trip
from run_jar import MTIME_BASE

#: A descriptor that says nothing the file it is in is not about: in GTFS,
#: frequency fields populated, UNSCHEDULED so E013 stays quiet.
QUIET: dict[str, object] = {
    "start_time": "07:00:00",
    "start_date": "20160101",
    "schedule_relationship": 2,
}

#: An arrival that carries a delay, so E043 and E044 stay quiet.
DELAYED: dict[str, object] = {"delay": 60}

#: `TripDescriptor.ScheduleRelationship`, spelled out because a bare 1 in a
#: feed body reads as a stop_sequence.
SCHEDULED, ADDED, UNSCHEDULED, CANCELED = 0, 1, 2, 3

#: `StopTimeUpdate.ScheduleRelationship`. `NO_DATA` with an arrival is E042.
STU_SCHEDULED, STU_SKIPPED, STU_NO_DATA = 0, 1, 2


def clock(offset: int) -> int:
    """A header or entity timestamp, as seconds from the first file's mtime."""
    return MTIME_BASE + offset


def quiet_trip(trip_id: str, **override: object) -> dict[str, object]:
    """A `TripDescriptor` for a bullrunner trip, quiet unless told otherwise."""
    return trip(trip_id, **{**QUIET, **override})  # type: ignore[arg-type]
