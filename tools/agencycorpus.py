"""The recorded agency corpus, verified and staged with a clock in each name.

Split out of `tier_counts.py`, which was the first thing to read the corpus at
all: that module owns what is counted, this one owns getting the bytes and
deciding what instant each message is validated at. The two questions read the
same manifest and share nothing else.

**Every file is checked against the checksum `tests/fixtures/agencies/manifest.json`
committed.** The bytes themselves are gitignored, so nothing else can tell a
re-recorded corpus from the recorded one, and a count taken over different bytes
under the manifest's provenance is worse than no count at all.

**The clock comes out of the bytes.** Each message is staged under a name whose
last twenty characters encode its own `header.timestamp`, which is what
`TimestampUtils.getTimestampFromFileName` reads under `-sort name`
(`BatchProcessor.java:220-232`, ported in `runner/clock.py`). A run over the
staged directory therefore validates every message at the instant its producer
stamped it: no wall clock, no mtime, and the same counts on any machine.

**Measured, because the alternative looked harmless.** One fixed instant for the
whole recording is the obvious way to make a replay reproducible, and over the
first MBTA recording it was wrong by the recording's own span: those six rounds
were 40 seconds apart, P005 reports a VehiclePosition older than 90 seconds, and
running every round against the last round's clock took P005 from 92 occurrences
to 985, which is 58 percent of every vehicle in that corpus reported stale for
having been recorded first. P008 moved 685 to 800 the same way. The three rules
that read no clock, P007, S006 and S024, did not move at all. Those figures are
that recording's; the reasoning is every recording's, and it is why a round is
now one distinct producer message rather than one poll.

The staged clock is also the fetch clock to within the fetch: it lands 1 to 2
seconds before each file's recorded mtime, which is network latency and not a
rule's business. And it is what the cited clauses mean. P005's sentence is
explicitly about "the age of VehiclePositions *within that feed*", so measuring
an entity against its own header is the clause's own comparison rather than a
convenience.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from gtfs_rt_validator.proto.decode import decode
from gtfs_rt_validator.proto.schema_current import SCHEMA
from gtfs_rt_validator.runner import Source

ROOT = Path(__file__).resolve().parent.parent
FIXTURES = ROOT / "tests" / "fixtures" / "agencies"
MANIFEST = FIXTURES / "manifest.json"

#: The roles `fetch_corpus.py` can record, in `runner/context.ROLE_ORDER`, which
#: is the CLI's own `-tu -vp -sa`. Not every agency publishes all three: an
#: agency's own roles come from its manifest entry, and this tuple only fixes the
#: order they are reported in. Repeated here rather than imported so that reading
#: the corpus needs no runner import.
ROLES = ("tu", "vp", "sa")


class CorpusMissing(Exception):
    """The recorded bytes are not here, or are not the bytes that were recorded.

    Never a finding about a feed. `corpus/` is gitignored, so a fresh checkout
    hits this, and the honest answer is to say so rather than to count nothing
    and call it zero.
    """


@dataclass(frozen=True, slots=True)
class Staged:
    """One agency, copied into a scratch directory and ready to validate.

    `cycles` is one cycle per round holding both roles, which is what makes a
    cross-message rule's "previous" the previous message *of the same role*.
    `runner/context.py` owns that reading, and P002, P003 and P004 all depend on
    it being right.
    """

    cycles: tuple[tuple[Source, ...], ...]
    archive: Path
    header_timestamps: dict[str, list[int]]
    entities: dict[str, int]


def manifest() -> dict[str, Any]:
    return json.loads(MANIFEST.read_text(encoding="utf-8"))


def digest(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def roles_of(agency: dict[str, Any]) -> tuple[str, ...]:
    """The roles this agency's recording actually holds, in `ROLES` order.

    Read from the rounds rather than declared, because a role whose endpoint
    failed for a whole recording is a role the corpus does not have, whatever
    `picks.json` says it publishes. A role missing from some rounds only is a
    recording bug rather than a shape to tolerate, and `stage` says so.
    """
    return tuple(role for role in ROLES if all(role in r["files"] for r in agency["rounds"]))


def header_timestamp(payload: bytes) -> int:
    """One message's own clock, which is what "a distinct message" is keyed on.

    `fetch_corpus.py` reads it to tell a producer's new message from the same
    message served again, and this module reads it to name the staged file. Both
    have to agree, so it is defined once, here, next to the naming.

    Keyed on the header timestamp and not on the bytes because that is the key
    upstream's own chain uses: `TimestampValidator.java:123-133` reports E017 for
    an equal timestamp, E018 for a decreased one, and only compares an interval
    against W007's 35-second floor when it strictly increased. A re-serialised
    message carrying the timestamp it already had is not a new interval to any of
    the three, so it is not a new one here either.
    """
    return decode(payload, SCHEMA).get("header").get("timestamp")


def staged_name(role: str, round_index: int, timestamp: int) -> str:
    """`<role>-<round>-YYYY-MM-DDTHH-MM-SSZ.pb`.

    The parse takes the twenty characters before the extension and leaves the
    prefix free, so the role and the round survive into the name for a human
    reading a system error while the clock is the tail. `runner/clock.py`
    enumerated exactly which twenty characters parse against a JDK run.
    """
    stamped = dt.datetime.fromtimestamp(timestamp, tz=dt.UTC).strftime("%Y-%m-%dT%H-%M-%SZ")
    return f"{role}-{round_index:02d}-{stamped}.pb"


def verified_bytes(record: dict[str, Any]) -> bytes:
    """One recorded file, checked against the checksum the manifest committed."""
    path = ROOT / record["path"]
    if not path.is_file():
        raise CorpusMissing(f"{record['path']} is not there; re-record with tools/fetch_corpus.py")
    data = path.read_bytes()
    found = digest(data)
    if found != record["sha256"]:
        raise CorpusMissing(
            f"{record['path']} is {found} and the manifest records {record['sha256']}; "
            f"these are not the bytes any committed count was taken over"
        )
    return data


def stage(agency: dict[str, Any], into: Path) -> Staged:
    """Copy an agency's whole recording into `into`, clock in every name."""
    cycles: list[tuple[Source, ...]] = []
    roles = roles_of(agency)
    if not roles:
        raise CorpusMissing(
            f"{agency['static_mdb_id']} has no role present in every round, so it has no cycle; "
            f"re-record it with tools/fetch_corpus.py"
        )
    timestamps: dict[str, list[int]] = {role: [] for role in roles}
    entities = dict.fromkeys(roles, 0)
    for entry in agency["rounds"]:
        sources: list[Source] = []
        for role in roles:
            record = entry["files"][role]
            data = verified_bytes(record)
            message = decode(data, SCHEMA)
            timestamp = message.get("header").get("timestamp")
            if timestamp == 0:
                raise CorpusMissing(
                    f"{record['path']} declares no header.timestamp, so it carries no clock of "
                    f"its own and a count over it would depend on the wall clock"
                )
            path = into / staged_name(role, entry["round"], timestamp)
            path.write_bytes(data)
            sources.append(Source(str(path), role, path))
            timestamps[role].append(timestamp)
            entities[role] += len(message.get("entity"))
        cycles.append(tuple(sources))
    archive = into / "static.zip"
    archive.write_bytes(verified_bytes(agency["static"]))
    return Staged(tuple(cycles), archive, timestamps, entities)
