# gtfs-rt-validator (Python)

A GTFS-Realtime validator in pure Python. No JVM, and one runtime dependency:
this project's own sibling, which itself has none.

By default it validates against the current GTFS-Realtime spec, with 121 rules.
Under `--compat` it runs the 56 rules
[MobilityData's Java gtfs-realtime-validator][upstream] can reach and reproduces
its output byte for byte.

This project reimplements that one and is not affiliated with it. Below,
"upstream" always means that project.

## Install

Python 3.11 or newer.

```bash
python -m pip install .          # or -e ".[dev]" to work on it
gtfs-rt-validator --version
```

The only runtime dependency is [`gtfs-validator`][sibling], this project's
sibling, which reads the static feed. Its published 0.1.2 declares no
dependencies of its own, so a fresh install pulls in nothing else.
`gtfs-realtime-bindings` is a development-only oracle.

Two limits on that guarantee. `tests/test_no_runtime_dependency.py` scans source
imports and permits `gtfs_validator`; it does not read package metadata, so a
future sibling release that grew a dependency would not fail the build. And the
sibling is a lower bound rather than a pin, so that a fix there reaches here
without a release on this side.

## Run

Modern mode, the default:

```bash
gtfs-rt-validator -gtfs feed.zip -rt archive/ --out reports/
```

`-rt` takes a single message, a directory to replay, or an `http(s)` URL. `-tu`,
`-vp` and `-sa` name TripUpdates, VehiclePositions and Alerts under their own
feed roles, which lets cross-feed rules see one cycle rather than whichever
message happened to be read last. `--at` pins the clock for a reproducible run,
`--sort` chooses replay order, and `--fail-on-error` exits 1 when an
error-severity rule fired.

Two files land in `--out`. `report.json` holds the findings, and
`system_errors.json` holds any input the run could not turn into findings,
whether the bytes were unreadable or they decoded and then failed on a required
field.

Compat mode takes upstream's six options instead, plus one of this project's own:

```bash
gtfs-rt-validator --compat -gtfs feed.zip -gtfsRealtimePath archive/
```

Output goes beside each input as `<name>.results.json`, because that is where
upstream puts it. Two of upstream's argument parsing bugs are part of that
surface and are reproduced: `-ignoreShapes false` enables it, and a bare
`-ignoreShapes` fails the run with `Missing argument for option: ignoreShapes`
rather than doing nothing. Modern mode reproduces neither. `-plainText` and
`-stats` are not implemented, and say why rather than being silently ignored.

The extra flag is `--upstream-equal-message-abort`, stripped before upstream's
parser sees it so a wrapper written against the jar still works. See "Known
divergences" for what it does and why it is off by default.

## Status

Version 0.1.0, not yet published to PyPI.

| | rules |
|---|---|
| default (modern) mode | 121: upstream's 56, plus 51 cited against the pinned `gtfs-realtime.proto`, plus 14 cited against the pinned Best Practices |
| `--compat` | exactly 56, the ones upstream's batch CLI can reach |

The compat differential over the committed crafted corpus reports 0 divergences.
Over real recorded agency feeds it is green for three of the four agencies and
red for the fourth, which is a finding rather than a defect: the jar refuses the
MBTA's archive outright. With that one archive file removed, the jar validates
the same feeds and the two agree on every byte of 13,177 occurrences under name
sort and 22,169 under date sort. That run is recorded as a diagnostic rather than
as parity.

The suite collects 3,360 tests: 3,356 pass, and 4 are known divergences pinned as
`xfail`.

## What it checks

Three tiers, in three directories. Which one a rule is in comes from where its
file lives rather than from an argument.

`rules/upstream/` holds 56 rules, one module per reported id, ported from the
pinned Java. These run in both modes. Under `--compat` a check that looks wrong
is almost always faithful, and the port says so in a comment beside the code it
explains.

`rules/spec/` holds 51 rules, each citing a clause of the pinned
`gtfs-realtime.proto` verbatim. They cover the surface upstream cannot see at
all: `TripModifications`, `Shape`, `Stop`, `TripProperties`, translated images,
carriage details, and the five `ScheduleRelationship` members added since 2015
(four on `TripDescriptor`, one on `StopTimeUpdate`).

`rules/practice/` holds 14 rules, each citing a statement of the pinned GTFS
Realtime Best Practices verbatim. The document holds 62 distinct normative
statements, measured by `tools/scan_clauses.py` rather than counted by hand.
Every one carries a verdict, and 46 are rejected with a reason.

A rule outside `rules/upstream/` cites the sentence it enforces or does not
register. The citation is compared byte for byte against a generated index of the
source document, so a paraphrase fails the build.

A rule is also retired when it turns out to detect nothing an upstream rule
already catches, which is why there is a gap at `S022` and at `P014`.
`tests/writtenrules.py` records what each of them was for and which upstream rule
made it redundant, beside the counts it ratchets.

`tests/test_tier_overlap.py` is what caught `S022`. It runs every rule over the
corpus and asserts that no cited rule has every one of its subjects also carrying
the same undeclared upstream occurrence. The stronger invariant, "no cited
occurrence beside an undeclared upstream one", was written down first and is
false on real feeds. 169 distinct pairs share a subject over the corpus as
recorded today, almost all of them two independent defects on one broken trip.
That figure moves with the corpus and nothing ratchets it.

## Why the two modes

Upstream's rule set has not changed since 2020 and its schema view has not
changed since 2015, while the spec has. A straight clone would inherit both. A
straight modernisation would lose the one property that makes a reimplementation
checkable: that it can be held against the original and differ nowhere.

So the parity is kept as a mode. Mode picks the descriptor, the registry and the
writer, and never a branch inside a rule. Compat decodes with the 2015 schema
rather than decoding with the current one and masking afterwards, because masking
cannot reproduce duplicate-field or required-field semantics.

Upstream compiles against protobuf bindings published in February 2015, so 13
message types and 77 field definitions in today's spec arrive in the bytes and
are dropped as unknown fields before any rule can see them. In proto2 an
unrecognised enum value goes the same way, which is why a feed marking a trip
`DUPLICATED` makes upstream's `hasScheduleRelationship()` answer false and
several of its rules treat that trip as plain `SCHEDULED`.

## Known divergences

Each is pinned as an `xfail` or as a red differential rather than a weakened
assertion. Three of the four `xfail`s are strict and fail the suite if they
quietly start passing; the fourth reports `XPASS`, and `-ra` prints all of them
on every run. Two of the entries below are red differentials rather than
`xfail`s, so this list is the inventory and the four `xfail`s are not.

The ones that would affect a real feed:

**An archive the jar refuses and this project accepts.** MBTA's `areas.txt` has
header `area_id,area_name`. The onebusaway reader upstream bundles models
`Area.wkt` as required, modelling an obsolete GTFS-Flex draft, so `GtfsReader`
throws and the jar exits 1 having validated nothing. This project's compat loader
reads seven tables and never opens `areas.txt`, so it validates the whole feed.
`GtfsReader` does parse an `Area`, which is why it throws; what never reads one is
any validator or metadata builder in `gtfs-realtime-validator-lib`, so the archive
is refused over a file that could not have changed a single finding. Closing this
means teaching the compat loader the required fields of every file `GtfsReader`
parses and this project does not, which is a design change rather than a fix.

**The equal-message abort, off by default.** Upstream stops the whole batch when
two consecutive messages are byte-identical, writing nothing for that file or any
after it. Reproducing that by default would let a routine feed shape destroy a
run's output, so it sits behind `--upstream-equal-message-abort`. With the flag,
the abort matches.

**`headway_secs = 0` on an `exact_times = 1` period.** The jar spins forever
inside `FrequencyTypeOneValidator`, but only for a trip a realtime message names,
so it validates such an archive to completion when nothing names it. Compat
cannot reproduce an infinite loop and refuses on the archive alone, so it writes
nothing where the jar writes everything.

**Argument-error ordering.** Given both a broken GTFS feed and an unreadable
realtime path, upstream loads the static feed first and exits nonzero; this
project resolves the realtime path first and exits 0.

The rest are numeric and environmental: one buffered longitude two ulps off
because Python's libm and Java's fdlibm differ, and two timezone edges where
`java.util.TimeZone` and `zoneinfo` disagree before a zone's first transition and
past year 9999. JDK 19 also rewrote `Float.toString`, so goldens regenerated on 19
or later differ from these in E026, E027, E028, E029 and W004 occurrence text, and
neither result is wrong. The differential refuses anything but JDK 17 for that
reason.

## Working on it

```bash
python -m pip install -e ".[dev]"
python -m pytest
ruff check --no-cache . && ruff format --check .
```

Use `--no-cache`. A warm ruff cache has returned a stale pass in this repository,
on a tree that had nine real errors in it.

The suite runs clean without a JDK. Everything needing a jar skips and names what
is missing. To run those, build the jar from the pinned commit with
`tools/build_jar.py` (JDK 17), then:

```bash
python tools/diff_compat_against_jar.py     # the crafted corpus, tests/fixtures/jar
python tools/diff_agency_against_jar.py     # four real agencies' recorded feeds
```

The first is green. The second exits 1 on the MBTA archive above, which is the
intended state, and its own docstring records what it found. Pass
`--drop-static-file areas.txt` to watch the jar validate the same feeds and agree
byte for byte.

Upstream publishes no tag, no GitHub release and no Maven Central artifact, so
the jar has to be built from source. It does publish a container image, which
this project does not use, because a differential needs the jar's own classpath
and JDK pinned rather than an image's.

With the recorded feed bytes but no JDK, `tests/test_agency_goldens.py` still
checks that tier. `tests/fixtures/agencies/jar-goldens.json` commits a SHA-256, a
byte length and a rule census for every results file the jar wrote, across four
agencies and both sort regimes, and the test recomputes this project's side and
compares. The jar's bytes are not committed: the MBTA alone is 1.7 MB of them
under name sort and 3.4 MB under date sort, against 53 KB for the whole golden
across all ten regimes. Regenerate with `tools/gen_agency_goldens.py`, which
needs a jar.

The recorded bytes themselves are gitignored, and they cannot be recovered.
`tools/fetch_corpus.py` records a fresh corpus from live feeds and rewrites the
manifest; the feeds behind the committed digests have moved on. A contributor
without those bytes regenerates both the corpus and the goldens rather than
reproducing these, so the committed numbers measure one recording rather than a
fixture anyone can obtain again.

Generated files are not hand-edited.
`src/gtfs_rt_validator/proto/schema_*.py`,
`src/gtfs_rt_validator/data/rules.json` and the clause indexes under `upstream/`
come from `tools/`. Fix the generator and re-run it, or the drift tests start
lying.

CI is written but not enabled: `.github/workflows/` runs on `workflow_dispatch`
only until this repository is public.

## Relationship to upstream

An independent reimplementation, not an official port, not affiliated with
MobilityData and not endorsed by them. Rule ids, severities, titles and
occurrence text come from their Apache-2.0 project; [`NOTICE`](NOTICE) names what
is copied rather than derived.

Where upstream and intuition disagree, upstream wins: under `--compat` a check
that looks wrong is almost always faithful, and a red differential is the
deliverable rather than an obstacle.

| What | Pin |
|---|---|
| `MobilityData/gtfs-realtime-validator` | `7041fa3` (2026-04-14) |
| `gtfs-realtime.proto` | `68158bd` (2026-06-30) |
| GTFS Realtime Best Practices | `5a495db` (2025-06-05) |
| Java bindings compat targets | `0.0.4` (2015-02-27) |

Upstream is pinned by commit because it has no tags, no releases and no Maven
Central artifact.

Each pin is watched, though not all by the same mechanism. The Java rule manifest
and the Best Practices document each have a committed copy, a hand-kept `.sha256`
beside it and a drift test. The proto has a committed copy and is watched through
the two schemas generated from it rather than through a digest of its own. The
2015 bindings are not vendored; what pins them is `proto/schema_2015.py`,
generated from the descriptor extracted from that artifact.

## License

MIT; see [`LICENSE`](LICENSE).

[upstream]: https://github.com/MobilityData/gtfs-realtime-validator
[sibling]: https://github.com/veodyn/gtfs-validator
