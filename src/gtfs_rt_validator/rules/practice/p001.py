"""P001: `header.gtfs_realtime_version` declares a version below 2.0.

`:34`. GTFS-Realtime v1.0 predates most of the fields a feed needs to describe
a real service change, so a producer still declaring it is telling consumers to
expect a feed that cannot say what it means. Nothing in the 56 asks a feed to be
v2, and the three upstream rules that touch this field were read rather than
assumed before this one was written:

* `rules/upstream/e038.py` reports a version that is present and is neither
  `"1.0"` nor `"2.0"`, by string equality through
  `_shared/versions.is_valid_version`. `"1.0"` is a *valid* version, so E038 is
  silent on exactly the feed this rule exists to report.
* `rules/upstream/e049.py` reports a header with no `incrementality` **when** the
  version parses to 2.0 or more. It gates on v2 and swallows the parse failure;
  it never asks for v2.
* `rules/upstream/e048.py` reports a header with no timestamp when the version is
  v2-or-higher or does not parse at all, its flag being pre-initialised to true.
  It gates on v2 as well.

**A version E038 rejects is E038's, and this rule says nothing about it.** That
is the answer to "numerically below 2.0" for a value that is not a number: the
question is never asked. `is_valid_version` runs first, so `"1.00"`, `"0.9"`,
`" 1.0"` and `"abc"` are all silent here even though the first three are
numerically below 2.0 and the last is not a number at all. Every one of them is
already reported once, against this same field, and reporting it twice for the
same reason would be a finding about this validator rather than about the feed.

Two consequences of that ordering, both deliberate. `is_v2_or_higher` can only
be reached with `"1.0"` or `"2.0"`, neither of which raises, so there is no
`except ValueError` here and no dead branch pretending there might be. And the
test is still numeric rather than `version == GTFS_RT_V1`, so a later pin that
widens the valid set gets the right answer without an edit here.

That helper's Java-float behaviour (float32 narrowing, a trailing `f` suffix,
`String.trim`) is compat's business and not a modern rule's. It is immaterial
for the reason above, and reusing the module that owns this field beats putting
a second parse of it next door.

**An absent version is unreachable**, since `gtfs_realtime_version` is
`required` at both pins and `proto/decode.py` refuses a header without it, as
`e038.py` and `e048.py` both record. The presence test stays because
`is_v2_or_higher` raises on an absent field, and the guard is what says why that
cannot happen here.

**Under a 2015 decode this fixture is fully visible**, the field being required
in that schema too. What makes this rule new is that no validator in the 56 asks
a feed to be v2, not that the jar cannot see the bytes.

At most one occurrence per message: the header is one field, not a list.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from gtfs_rt_validator.report import manifest
from gtfs_rt_validator.report.occurrence import ENTITY_PATH_KEY, Occurrence
from gtfs_rt_validator.rules._shared.versions import is_v2_or_higher, is_valid_version
from gtfs_rt_validator.rules.registry import rule

if TYPE_CHECKING:  # Type-only: `runner.context` reaches the static layer and so
    # the sibling, which nothing under `rules/` may import at run time.
    from gtfs_rt_validator.proto.decode import Msg
    from gtfs_rt_validator.runner.context import RuleContext, RuleResult

RULE_ID = "P001"

CLAUSE = (
    'All GTFS Realtime feeds should be "2.0" or higher, as early version of GTFS Realtime did '
    "not require all fields needed to represent various transit situations adequately."
)

#: Spelled once, and the same spelling E038 reports with: the proto field name
#: rather than the Java getter.
VERSION_FIELD = "gtfs_realtime_version"

#: The version the document asks for, as text, for the occurrence prefix. The
#: comparison itself is numeric and lives in `_shared/versions.py`.
RECOMMENDED = "2.0"

BELOW = f"header.{VERSION_FIELD} of {{version}} is below the {RECOMMENDED} the practice recommends"


@rule(RULE_ID, source=f"practice: {CLAUSE}", severity=manifest.Severity.WARNING)
def check(message: Msg, ctx: RuleContext) -> RuleResult:
    """One occurrence when the header states a valid version below 2.0."""
    header = message.get("header")
    if not header.has(VERSION_FIELD) or not is_valid_version(header) or is_v2_or_higher(header):
        return None
    version = header.get(VERSION_FIELD)
    return [
        Occurrence(
            RULE_ID,
            BELOW.format(version=version),
            {ENTITY_PATH_KEY: "header", "gtfsRealtimeVersion": version},
        )
    ]
