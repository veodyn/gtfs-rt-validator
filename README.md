# gtfs-rt-validator

[![CI](https://github.com/veodyn/gtfs-rt-validator/actions/workflows/ci.yml/badge.svg)](https://github.com/veodyn/gtfs-rt-validator/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/gtfs-rt-validator)](https://pypi.org/project/gtfs-rt-validator/)
[![Python versions](https://img.shields.io/pypi/pyversions/gtfs-rt-validator)](https://pypi.org/project/gtfs-rt-validator/)
[![License](https://img.shields.io/pypi/l/gtfs-rt-validator)](https://github.com/veodyn/gtfs-rt-validator/blob/main/LICENSE)

Validate GTFS-Realtime feeds from Python. No JVM, and one dependency.

The only maintained GTFS-Realtime rule validator is
[MobilityData's][upstream], written in Java and compiled against protobuf
bindings published in 2015. Using it from Python means shelling out to a JVM and
accepting a decade-old view of the spec. This validates the current spec in
process, and can still reproduce that Java tool byte for byte when you need the
old answers.

```bash
pip install gtfs-rt-validator
gtfs-rt-validator -gtfs feed.zip -rt TripUpdates.pb --out reports/
```

Python 3.11 or newer.

## What you get

`reports/report.json` holds a summary and one entry per rule that fired, each
carrying its severity, a total, and samples that name the entity:

```json
{
  "summary": {
    "validatorVersion": "0.1.0",
    "validatedAt": "2026-08-16T15:51:39Z",
    "gtfsInput": "bullrunner-gtfs.zip",
    "gtfsRealtimeInputs": ["TripUpdates.pb"],
    "feedRoles": {"rt": "TripUpdates.pb"},
    "messagesValidated": 1,
    "filesSkipped": 0,
    "validationTimeSeconds": 0.076
  },
  "notices": [
    {
      "code": "E003",
      "severity": "ERROR",
      "totalNotices": 1,
      "sampleNotices": [
        {
          "prefix": "trip_id not-in-gtfs",
          "sourceFile": "TripUpdates.pb",
          "entityPath": "entity[0].trip_update.trip"
        }
      ]
    }
  ]
}
```

`entityPath` points at the exact field inside the message, so a finding is
actionable without opening the feed by hand.

`reports/system_errors.json` holds anything the run could not turn into
findings, whether the bytes were unreadable or they decoded and then failed on a
required field. It is written even when empty, so its absence means the run did
not finish.

Severity is `ERROR` or `WARNING`. The process exits 0 whether or not rules fired.
Add `--fail-on-error` to exit 1 when an `ERROR` fired, which is what you want in
CI. A usage mistake exits 1 and a tool failure exits 255.

## Running it

```bash
gtfs-rt-validator -gtfs feed.zip -rt TripUpdates.pb --out reports/
```

`-rt` takes a single message, a directory to replay in order, or an `http(s)`
URL it will fetch once.

Feeds published as separate files should be named by role, so that rules
comparing TripUpdates against VehiclePositions see one moment rather than
whichever file happened to be read last:

```bash
gtfs-rt-validator -gtfs feed.zip \
  -tu TripUpdates.pb -vp VehiclePositions.pb -sa Alerts.pb \
  --out reports/
```

`--at` pins the validation clock to a fixed instant, which makes a run over
archived messages reproducible instead of depending on when you ran it. `--sort`
chooses replay order for a directory, by `name` or by `date`.

## From Python

```python
from pathlib import Path
from gtfs_rt_validator.api import Mode, Request, resolve, validate

result = validate(Request(
    mode=Mode.MODERN,
    gtfs=Path("feed.zip"),
    inputs=resolve("TripUpdates.pb"),
))

result.has_errors()   # True
result.error_ids()    # ('E003', 'E004', 'E011')
result.write(Path("reports/"))
```

`resolve` takes the same targets as `-rt`, including a URL. `resolve_roles`
takes a mapping such as `{"tu": ..., "vp": ...}` for the named-role form.
Nothing is written to disk unless you call `write`.

## What it checks

121 rules, in three groups.

**56 ported from upstream**, one module per reported id, keeping their `E` and
`W` codes so a code in a report stays lookup-able against upstream's own
documentation.

**51 checking the current spec**, coded `S`. These cover what a 2015 view cannot
see at all: `TripModifications`, `Shape`, `Stop`, `TripProperties`, translated
images, carriage details, and the five `ScheduleRelationship` members added
since 2015. Each one quotes the clause of `gtfs-realtime.proto` it enforces.

**14 checking published best practice**, coded `P`. Things a feed can do that
are valid but unhelpful: identifiers that change mid-trip, vehicle positions
older than 90 seconds, an alert naming every stop of a route instead of naming
the route, a trip whose every update is skipped rather than being marked
cancelled. Each quotes the statement of the GTFS Realtime Best Practices it
enforces.

A rule outside the ported set cites its sentence or does not register, and the
citation is compared byte for byte against a generated index of the source
document, so a paraphrase fails the build. A rule that turns out to detect
nothing an upstream rule already catches is retired rather than shipped, which
is why the ids skip `S022` and `P014`.

## Matching the Java validator

`--compat` runs exactly the 56 rules upstream's batch CLI reaches, decoding with
the 2015 schema it compiles against, and writes `<name>.results.json` beside each
input the way upstream does:

```bash
gtfs-rt-validator --compat -gtfs feed.zip -gtfsRealtimePath archive/
```

The flags are upstream's, including two argument-parsing bugs that are part of
its surface: `-ignoreShapes false` enables it, and a bare `-ignoreShapes` fails
the run. `-plainText` and `-stats` are not implemented and say why.

Output is byte-identical to a jar built from the pinned commit, checked two ways:
0 divergences over a crafted corpus, and agreement on every byte of 13,177
occurrences over recorded feeds from four transit agencies.

Four differences are known and deliberate. Three concern feeds you are unlikely
to have: an infinite loop upstream enters on a zero `headway_secs`, which this
refuses instead; the order two argument errors are reported in; and floating
point and timezone edges where Python and Java disagree by one ulp or at year
9999.

The fourth may affect you. Upstream stops an entire batch when two consecutive
messages are byte-identical, writing nothing for that file or any after it. A
feed that republishes an unchanged message is ordinary, so reproducing that by
default would let it destroy a run's output. It is behind
`--upstream-equal-message-abort` if you need the exact behaviour.

There is also one case where this validator is more useful than the original.
Upstream's bundled GTFS reader requires a `wkt` column in `areas.txt`, modelling
an obsolete draft, so it refuses any archive with a modern `areas.txt` and
validates none of the feed. The MBTA publishes one. This project reads seven
tables, never opens `areas.txt`, and validates normally.

## Working on it

```bash
python -m pip install -e ".[dev]"
python -m pytest
ruff check --no-cache . && ruff format --check .
```

Use `--no-cache`. A warm ruff cache has returned a stale pass in this
repository, on a tree that had nine real errors in it.

The suite is 3,360 tests and runs clean without a JDK. Everything needing a jar
skips and names what is missing. To run those, build the jar from the pinned
commit with `tools/build_jar.py` (JDK 17), then:

```bash
python tools/diff_compat_against_jar.py     # the crafted corpus
python tools/diff_agency_against_jar.py     # four agencies' recorded feeds
```

The first is green. The second exits 1 on the MBTA archive described above,
which is the intended state; pass `--drop-static-file areas.txt` to watch the
jar validate the same feeds and agree byte for byte.

With recorded feed bytes but no JDK, `tests/test_agency_goldens.py` still checks
that tier against `tests/fixtures/agencies/jar-goldens.json`, which commits a
SHA-256, a byte length and a rule census for every results file the jar wrote.
The jar's bytes are not committed. Neither is the corpus, and it cannot be
recovered: `tools/fetch_corpus.py` records a fresh one from live feeds, and the
feeds behind the committed digests have moved on.

Generated files are not hand-edited. The two protobuf schemas, the rule manifest
and the clause indexes come from `tools/`. Fix the generator and re-run it, or
the drift tests start lying.

CI runs on `workflow_dispatch` only until this repository is public.

## Relationship to upstream

An independent reimplementation, not an official port, not affiliated with
MobilityData and not endorsed by them. Rule ids, severities, titles and
occurrence text come from their Apache-2.0 project; [`NOTICE`](https://github.com/veodyn/gtfs-rt-validator/blob/main/NOTICE) names what
is copied rather than derived.

Where upstream and this project's intuition disagree, upstream wins: under
`--compat` a check that looks wrong is almost always faithful, and a red
differential is the deliverable rather than an obstacle.

| What | Pin |
|---|---|
| `MobilityData/gtfs-realtime-validator` | `7041fa3` (2026-04-14) |
| `gtfs-realtime.proto` | `68158bd` (2026-06-30) |
| GTFS Realtime Best Practices | `5a495db` (2025-06-05) |
| Java bindings compat targets | `0.0.4` (2015-02-27) |

Upstream is pinned by commit because it has no tags, no releases and no Maven
Central artifact.

The only runtime dependency is [`gtfs-validator`][sibling], this project's
sibling, which reads the static feed and declares no dependencies of its own.
`gtfs-realtime-bindings` is used in development as an oracle and never at run
time.

## License

MIT; see [`LICENSE`](https://github.com/veodyn/gtfs-rt-validator/blob/main/LICENSE).

[upstream]: https://github.com/MobilityData/gtfs-realtime-validator
[sibling]: https://github.com/veodyn/gtfs-validator
