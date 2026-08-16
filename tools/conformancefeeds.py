"""The tier 1 conformance corpus: four groups of crafted feeds, and what they aim at.

`tools/goldenfeeds.py` pins the *output contract* with eight feeds chosen for
properties of the writer. This corpus is the other half: it is aimed at
**coverage**, and its acceptance criterion is that every one of the 56
batch-reachable rules fires at least once against the real jar.
`tests/test_rule_coverage.py` is where that number is committed.

**A group is one jar invocation**, because `-gtfs` takes a single archive and
`-ignoreShapes` applies to the whole run. Within a group the order below is the
order `run_jar.plan` stamps mtimes in, and upstream reads those mtimes as both
the sort key and the validation clock, so the order is part of the input.

**The corpus does not restate the jar corpus's format, it reuses it.**
`run_jar.stage` stages and stamps, `run_jar.collect` reads results back, and
each group's manifest section records names, order, mtimes and checksums the
same way `tests/fixtures/jar/manifest.json` already does.

Three things single crafted feeds structurally cannot reach, and where they are:

- **many occurrences per rule**, so Java hash iteration order is observable at
  all: `bullrunner/22-crossfeed-many.pb`, which `tools/conf_vehicles.py`
  explains at length.
- **long file sequences**, interleaving `prevHash` dedupe skips with decode
  failures and an E017 chain that has to survive them: the `bullrunner` group is
  27 files with two duplicates and two undecodable inputs among them.
- **E028 and E029 at real geometry scale, with and without `-ignoreShapes`**:
  the `bullrunner` and `bullrunner-ignoring-shapes` groups over the same
  1,522-point `shapes.txt`.

The fourth, **the retention caps**, is not here and cannot be. They are
100,000 occurrences per rule and 10,000,000 in total, they are this project's
(taken from the sibling's `NoticeContainer`) rather than upstream's, and the jar
has no cap at all. Exceeding one would need a golden of roughly 13 MB for a
single rule, against a corpus budget of 5 MB, so the case is recorded as a known
divergence rather than exercised.
"""

from __future__ import annotations

from dataclasses import dataclass

from conf_archives import IGNORING_SHAPES_FEEDS, TESTAGENCY2_FEEDS, TIMEPOINTS_FEEDS
from conf_stoptimes import STOP_TIME_FEEDS
from conf_trips import ALERT_FEEDS, TRIP_FEEDS
from conf_vehicles import VEHICLE_FEEDS
from feedbuild import Feed


@dataclass(frozen=True)
class Group:
    """One jar invocation: a static archive, a shapes mode, and its feeds.

    There used to be a `patch_direction_id` flag here, recording that an archive
    spells a `direction_id` as a letter and so could not be loaded as it stands.
    Compat reads the static feed as onebusaway's reader does now, so every group
    validates the committed bytes and the flag has nothing left to say.
    """

    name: str
    gtfs: str
    why: str
    feeds: tuple[Feed, ...]
    ignore_shapes: bool = False


BULLRUNNER = "bullrunner-gtfs.zip"

GROUPS: tuple[Group, ...] = (
    Group(
        name="bullrunner",
        gtfs=BULLRUNNER,
        why="the long sequence: 27 files, two dedupe skips, two decode failures",
        feeds=TRIP_FEEDS + STOP_TIME_FEEDS + ALERT_FEEDS + VEHICLE_FEEDS,
    ),
    Group(
        name="bullrunner-ignoring-shapes",
        gtfs=BULLRUNNER,
        why="the same geometry with -ignoreShapes, which is the other half of E028",
        feeds=IGNORING_SHAPES_FEEDS,
        ignore_shapes=True,
    ),
    Group(
        name="testagency2",
        gtfs="testagency2.zip",
        why="location_type, agency_id, direction_id and exact_times = 1",
        feeds=TESTAGENCY2_FEEDS,
    ),
    Group(
        name="timepoints",
        gtfs="bullrunner-gtfs-timepoints-only-legacy-exact-times-1.zip",
        why="stop_times.txt rows with no arrival_time and no departure_time",
        feeds=TIMEPOINTS_FEEDS,
    ),
)

#: Every static archive the corpus validates against, in group order.
ARCHIVES: tuple[str, ...] = tuple(dict.fromkeys(group.gtfs for group in GROUPS))


def group(name: str) -> Group:
    return next(each for each in GROUPS if each.name == name)
