"""Polling a live producer until it has published something new, and measuring how

long that took.

Split out of `fetch_corpus.py`, which owns the picks, the static archive and the
manifest; this module owns one question, which is what a recorded round *is*.

**A round is one distinct producer message per role, not one poll.** This is the
whole of the cadence decision, and it is what makes P004 and W007 measurable
rather than manufactured. Both rules are about how often the *producer*
refreshes, which a recorder only ever sees through its own polling, so a fixed
poll interval writes the recorder's number into the corpus and the counts then
report it back: polling every 33 seconds would put every consecutive pair inside
P004's `30 < interval <= 35` band and would say nothing whatever about an agency
that refreshes every 3 seconds. So this poller runs well below any cadence either
rule can report, and keeps a message only when its `header.timestamp` has
advanced. The intervals it records are then differences between producer
timestamps, which is exactly the quantity P004 and W007 compare.

**"Distinct" means the header timestamp advanced**, which is upstream's own key:
`TimestampValidator.java:123-133` is an if/else-if chain reporting E017 when it
is equal and E018 when it decreased, and reaching W007's 35-second floor only
when it strictly increased. So a re-serialised message carrying the timestamp it
already had is not a new interval to any of the three, and it is not a new round
here. `agencycorpus.header_timestamp` holds the read, so the recorder and the
replay cannot disagree about what a message is.

**Measured before it was chosen.** Probing ten endpoints every 3 seconds for 96
seconds on 2026-08-15 found MBTA TripUpdates and VehiclePositions refreshing
every 2 to 4 seconds, MBTA Alerts every 59 to 60, Clovis Transit every 5 to 8,
and Whatcom and Valley Transit every 29 to 31. Three conclusions, all of them
load-bearing here: the default interval has to be a few seconds rather than tens
of them; a real agency does sit inside P004's band, so the band is reachable
without contriving it; and a feed can refresh faster than any polite poll, which
is why `may_be_faster_than_recorded` is stated per role rather than assumed away.
"""

from __future__ import annotations

import hashlib
import itertools
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from agencycorpus import ROLES, header_timestamp

from gtfs_rt_validator.proto.decode import DecodeError

ROOT = Path(__file__).resolve().parent.parent

#: Seconds between polls of one role. Well below P004's lower edge of 30 and
#: W007's floor of 35, so every interval either rule can report is resolved to
#: the second: what is recorded is the difference between two producer
#: timestamps, and a poll rate below the cadence cannot inflate one. A producer
#: faster than this is recorded as an upper bound and says so in the manifest.
POLL_INTERVAL_SECONDS = 5.0

#: Distinct messages to keep per role. Six, because the cross-message rules need
#: a sequence rather than a pair, and because a slow role costs `6 x cadence`
#: seconds of polling: MBTA's Alerts feed, a minute apart, is six minutes.
DISTINCT_MESSAGES = 6

#: Polls allowed per message wanted, before giving up on a role. At the default
#: interval this waits two minutes for a producer to publish something new, and a
#: producer slower than that is outside both P004's band and W007's floor anyway,
#: so waiting longer buys the cadence question nothing.
MAX_POLLS_PER_MESSAGE = 24

#: A courtesy to agencies whose endpoints are small municipal servers, and a
#: requirement for reproducibility: a hung fetch must fail rather than wedge.
TIMEOUT_SECONDS = 60.0

#: Named so an operator reading an agency's access log can tell what this was.
USER_AGENT = "gtfs-rt-validator-corpus/1.0 (conformance testing; one-time snapshot)"


def fetch(url: str) -> bytes:
    """One GET, with a timeout and an honest user agent."""
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})  # noqa: S310
    with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:  # noqa: S310
        return response.read()


def digest(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def record(path: Path, payload: bytes) -> dict[str, Any]:
    """Write one recorded file and describe it the way the manifest does."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)
    return {
        "path": str(path.relative_to(ROOT)),
        "bytes": len(payload),
        "sha256": digest(payload),
    }


def roles_of(agency: dict[str, Any]) -> tuple[str, ...]:
    """The roles this pick declares, in `ROLE_ORDER`, then anything unnamed.

    Order matters only for readability here; what it must not do is drop a role
    a pick declares, so an unknown one sorts last rather than disappearing.
    """
    declared = set(agency["realtime"])
    known = [role for role in ROLES if role in declared]
    return tuple(known + sorted(declared - set(known)))


def gather(agency: dict[str, Any], out: Path, wanted: int, interval: float) -> dict[str, Any]:
    """Poll every role until each has `wanted` distinct messages, or run out.

    Returns the kept messages per role, the intervals between their header
    timestamps, and every failure seen on the way. A role that fails a poll is
    polled again rather than abandoned: a real agency endpoint returns a 502
    sometimes, and a recording that aborted on the first one would never finish.
    A role that answers without a header timestamp is abandoned, because that is
    not a failure to retry: it is a feed with no cadence to observe and no clock
    to stage, which `agencycorpus.stage` refuses for the same reason.
    """
    roles = roles_of(agency)
    kept: dict[str, list[dict[str, Any]]] = {role: [] for role in roles}
    clock: dict[str, int] = {}
    stalled: set[str] = set()
    failures: list[dict[str, Any]] = []
    for attempt in range(wanted * MAX_POLLS_PER_MESSAGE):
        pending = [r for r in roles if len(kept[r]) < wanted and r not in stalled]
        if not pending:
            break
        if attempt:
            time.sleep(interval)
        for role in pending:
            url = agency["realtime"][role]["producer_url"]
            try:
                payload = fetch(url)
                stamp = header_timestamp(payload)
            except (urllib.error.URLError, TimeoutError, OSError, DecodeError) as failure:
                failures.append({"role": role, "url": url, "poll": attempt, "error": str(failure)})
                print(f"    poll {attempt} {role}: FAILED {failure}")
                continue
            if stamp == 0:
                stalled.add(role)
                failures.append(
                    {
                        "role": role,
                        "url": url,
                        "poll": attempt,
                        "error": "declares no header.timestamp, so it has no cadence to observe",
                    }
                )
                print(f"    poll {attempt} {role}: no header.timestamp, giving up on this role")
                continue
            if stamp <= clock.get(role, 0):
                continue
            clock[role] = stamp
            written = record(out / f"round-{len(kept[role]):02d}" / f"{role}.pb", payload)
            written |= {"url": url, "header_timestamp": stamp, "poll": attempt}
            kept[role].append(written)
            print(
                f"    message {len(kept[role]) - 1} {role}: {written['bytes']} bytes "
                f"{written['sha256'][:12]} stamped {stamp} on poll {attempt}"
            )
    return {"kept": kept, "failures": failures, "refresh": refresh(kept, interval)}


def refresh(kept: dict[str, list[dict[str, Any]]], interval: float) -> dict[str, Any]:
    """The producer's own cadence per role: gaps between header timestamps.

    `may_be_faster_than_recorded` is an honest caveat and not a warning about the
    run. A gap no wider than the poll interval means a message could have been
    published and replaced between two polls, so the gaps are an upper bound on
    the producer's cadence. A gap wider than the interval was resolved exactly,
    because the recorder looked in between and the producer had published
    nothing.
    """
    found: dict[str, Any] = {}
    for role, messages in kept.items():
        stamps = [message["header_timestamp"] for message in messages]
        gaps = [later - earlier for earlier, later in itertools.pairwise(stamps)]
        found[role] = {
            "intervals_seconds": gaps,
            "may_be_faster_than_recorded": bool(gaps) and min(gaps) <= interval,
        }
    return found


def rounds_of(kept: dict[str, list[dict[str, Any]]]) -> list[dict[str, Any]]:
    """Zip each role's distinct messages into rounds, positionally.

    Positional is the alignment `runner/context.py` settled on for a cycle, and
    its reason applies here too: aligning the roles by header timestamp would
    align them on a value this project is simultaneously validating. Roles
    refresh at their own rates, so the k-th Alerts message can be minutes from
    the k-th TripUpdates one; that is what a consumer polling each feed at its
    own cadence sees, and no tolerance was invented to hide it.
    """
    if not kept:
        return []
    depth = min(len(messages) for messages in kept.values())
    return [
        {"round": index, "files": {role: kept[role][index] for role in sorted(kept)}}
        for index in range(depth)
    ]
