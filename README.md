# gtfs-rt-validator (Python)

A GTFS-Realtime validator in pure Python. No JVM, and one runtime dependency:
this project's own sibling, which itself has none.

It does two things that are usually a choice between. By default it validates
against the **current** GTFS-Realtime spec, with 121 rules. Under `--compat` it
reproduces [MobilityData's Java gtfs-realtime-validator][upstream] **byte for
byte**, including its bugs, with the one deliberate exception named under
"Known divergences": upstream aborts a whole run on two consecutive identical
messages, and this project does that only behind
`--upstream-equal-message-abort`.

This project reimplements that one and is not affiliated with it. Below,
"upstream" always means that project.

## Status

Version 0.1.0. Built and checked; **not yet published to PyPI**.

| | rules |
|---|---|
| default (modern) mode | **121**: upstream's 56, plus 51 cited against the pinned `gtfs-realtime.proto`, plus 14 cited against the pinned Best Practices |
| `--compat` | **exactly 56**, the ones upstream's batch CLI can reach |

The compat differential over the committed crafted corpus is **0 divergences**.
Over real recorded agency feeds it is **green for three of the four agencies**
and red for the fourth, which is a finding rather than a defect: the jar refuses
the MBTA's archive outright (see "Known divergences"). With that one archive
file removed, the jar validates the same feeds and the two agree on every byte
of **13,177 occurrences** under name sort and 22,169 under date sort. That
diagnostic run is labelled as a non-parity result wherever it is recorded.

The suite collects **3,360 tests**: 3,356 pass and 4 are known divergences
pinned as `xfail`, three of them strict. The fourth is a one-ulp libm
difference that is not stable enough to be strict, and says so.

Every number on this page is a measurement taken on 2026-08-16 and typed in by
hand. The rule counts are ratcheted by `tests/test_completeness.py` and the pins
by `upstream/pins.json`, so those cannot drift unnoticed in the code; the prose
here can, and has. Where a figure matters, the command that produces it is named
beside it.

## Install

Python 3.11 or newer.

```bash
python -m pip install .          # or -e ".[dev]" to work on it
gtfs-rt-validator --version
```

The only runtime dependency is [`gtfs-validator`][sibling], this project's
sibling, which reads the static feed. Its published 0.1.2 declares no
dependencies of its own, so a fresh install pulls in nothing else.

Two caveats, because the guarantee is narrower than it looks.
`tests/test_no_runtime_dependency.py` scans **source imports** and permits
`gtfs_validator`; it does not read package metadata, so a future sibling release
that grew a dependency would not fail this build. And the sibling is a lower
bound rather than a pin, deliberately, so that a fix there reaches here without a
release on this side. `gtfs-realtime-bindings` is a development-only oracle and
that same test is what keeps it out of the runtime.

## Run

Modern mode, the default:

```bash
gtfs-rt-validator -gtfs feed.zip -rt archive/ --out reports/
```

`-rt` takes a single message, a directory to replay, or an `http(s)` URL. `-tu`,
`-vp` and `-sa` name TripUpdates, VehiclePositions and Alerts under their own
feed roles, which is what lets cross-feed rules see one cycle rather than
whichever message happened to be read last. `--at` pins the clock for a
reproducible run, `--sort` chooses replay order, and `--fail-on-error` exits 1
when an error-severity rule fired. Two files land in `--out`: `report.json`, and
`system_errors.json` for an input the run could not turn into findings, whether
because the bytes were unreadable or because they decoded and then failed on a
required field.

Compat mode swaps the flag surface for upstream's six options, plus exactly one
of this project's own (`--upstream-equal-message-abort`, stripped before
upstream's parser ever sees it, so a wrapper written against the jar still
works):

```bash
gtfs-rt-validator --compat -gtfs feed.zip -gtfsRealtimePath archive/
```

Output goes beside each input as `<name>.results.json`, not into an output
directory, because that is where upstream puts it. **Two of upstream's argument
parsing bugs are compat surface and are reproduced**: `-ignoreShapes false`
enables it, and a bare `-ignoreShapes` fails the run with
`Missing argument for option: ignoreShapes` rather than being a no-op. Modern
mode reproduces neither. `-plainText` and `-stats` are deliberately not
implemented and say so, with the reason, rather than being silently ignored.

## What it checks

Three tiers, in three directories, and which one a rule is in comes from where
its file lives rather than from an argument.

**`rules/upstream/`, 56 rules.** One module per reported id, ported from the
pinned Java. These run in both modes. Under `--compat` a check that looks wrong
is almost always faithful, and the port says so in a comment next to the code it
explains.

**`rules/spec/`, 51 rules.** Each cites a clause of the pinned
`gtfs-realtime.proto`, verbatim. These cover the surface upstream cannot see at
all: `TripModifications`, `Shape`, `Stop`, `TripProperties`, translated images,
carriage details, and the five `ScheduleRelationship` members added since 2015
(four on `TripDescriptor`, one on `StopTimeUpdate`).

**`rules/practice/`, 14 rules.** Each cites a statement of the pinned GTFS
Realtime Best Practices, verbatim. The document holds 62 distinct normative
statements, measured by `tools/scan_clauses.py` rather than counted by hand;
every one of them carries a verdict, and 46 are rejected with a reason.

### How a rule earns its place, and loses it

A rule outside `rules/upstream/` **cites the sentence it enforces or does not
register**. The citation is compared byte for byte against a generated index of
the source document, so a paraphrase fails the build.

A rule is also **retired when it turns out to detect nothing new**. Two were,
during the build, and both were found by measurement rather than review. Only
one of them ever reached a commit: P014 was killed before landing, S022 shipped
in `3fb86bd` and was removed in `72c6274`.

- **P014** would have reported a frequency-based trip with no
  `schedule_relationship`. Its band against E013 was real, but W009 fires on
  `!hasScheduleRelationship()` for *any* TripDescriptor, so its trigger was a
  strict subset and no feed shape escaped it.
- **S022** reported duplicating a frequency-based trip. Its docstring said
  "nothing in the 56 reads `DUPLICATED` at all". True in the sense that no
  upstream rule tests for that member, and beside the point: E013 fires on a
  `schedule_relationship` that is **present and not `UNSCHEDULED`**, which
  `DUPLICATED` satisfies without being named. In modern mode E013 even prints
  the word, since it renders from the current schema's enum table. Under compat
  the member is dropped by the 2015 decoder, so E013 stays silent there and W009
  fires instead, which is why no differential could have surfaced this.

`tests/test_tier_overlap.py` is what caught the second one. It runs every rule
over the whole corpus and asserts that no cited rule has *every* one of its
subjects also carrying the same undeclared upstream occurrence. The stronger
invariant, "no cited occurrence beside an undeclared upstream one", was written
down first and is simply false on real feeds: 169 distinct pairs share a subject
over the corpus as recorded today, almost all of them two independent defects on
one broken trip. That figure moves with the corpus and is a measurement rather
than an assertion; the test does not ratchet it.

## Why the two modes

Upstream's rule set has not changed since 2020 and its schema view has not
changed since 2015, while the spec has. A straight clone would inherit both. A
straight modernisation would lose the one property that makes a reimplementation
checkable: that it can be held against the original and differ nowhere.

So the parity is kept as a mode. **Mode picks the descriptor, the registry and
the writer, and never a branch inside a rule.** Compat decodes with the 2015
schema rather than decoding with the current one and masking afterwards, because
masking cannot reproduce duplicate-field or required-field semantics.

That difference is not cosmetic. Upstream compiles against protobuf bindings
published in February 2015, so 13 message types and 77 field definitions in
today's spec arrive in the bytes and are dropped as unknown fields before any
rule can see them. In proto2 an unrecognised enum value goes the same way, which
is why a feed marking a trip `DUPLICATED` makes upstream's
`hasScheduleRelationship()` answer false and several of its rules treat that trip
as plain `SCHEDULED`.

## Known divergences

Measured, and each pinned as an `xfail` or as a red differential rather than a
weakened assertion. The three strict `xfail`s fail the suite if they quietly
start passing; the non-strict one reports `XPASS` instead, which `-ra` prints
along with every `xfail` on each run. **This list is the divergence inventory; the
four `xfail`s are not.** Two of the entries below are red differentials rather
than `xfail`s, and the equal-message behaviour is a third kind again, a
deliberate default this project does not reproduce unless asked. The ones that
would affect a real feed:

- **An archive the jar refuses and this project accepts.** MBTA's `areas.txt`
  has header `area_id,area_name`; the onebusaway reader upstream bundles models
  `Area.wkt` as required, modelling an obsolete GTFS-Flex draft, so `GtfsReader`
  throws and the jar exits 1 having validated nothing. This project's compat
  loader reads seven tables and never opens `areas.txt`, so it validates the
  whole feed. `GtfsReader` does parse an `Area`, which is exactly why it
  throws; what never reads one is any validator or metadata builder in
  `gtfs-realtime-validator-lib`, so the archive is refused over a file that
  could not have changed a single finding. Closing this means
  teaching the compat loader the required fields of every file `GtfsReader`
  parses and this project does not, which is a design change rather than a fix.
- **The equal-message abort, off by default.** Upstream stops the whole batch
  when two consecutive messages are byte-identical, writing nothing for that
  file or any after it. Reproducing that by default would make a routine feed
  shape destroy a run's output, so it is behind
  `--upstream-equal-message-abort`, which is the one flag this project adds to
  the compat surface. With the flag, the abort matches.
- **`headway_secs = 0` on an `exact_times = 1` period.** The jar spins forever
  inside `FrequencyTypeOneValidator`, but only for a trip a realtime message
  names, so it validates such an archive to completion when nothing names it.
  Compat cannot reproduce an infinite loop and refuses on the archive alone, so
  it writes nothing where the jar writes everything.
- **Argument-error ordering.** Given both a broken GTFS feed and an unreadable
  realtime path, upstream loads the static feed first and exits nonzero; this
  project resolves the realtime path first and exits 0.

The rest are numeric and environmental: one buffered longitude two ulps off
because Python's libm and Java's fdlibm differ, and two timezone edges where
`java.util.TimeZone` and `zoneinfo` disagree before a zone's first transition and
past year 9999. Note also that **JDK 19 rewrote `Float.toString`**, so goldens
regenerated on 19 or later differ from these in E026, E027, E028, E029 and W004
occurrence text, and neither result is wrong. That is why the differential
refuses anything but JDK 17.

## Working on it

```bash
python -m pip install -e ".[dev]"
python -m pytest
ruff check --no-cache . && ruff format --check .
```

`--no-cache` is not decoration: a warm ruff cache has returned a stale pass in
this repository, on a tree that had nine real errors in it.

The suite runs clean without a JDK. Everything needing a jar skips and names what
is missing, so a skip is never just a dot. To run those, build the jar from the
pinned commit with `tools/build_jar.py` (JDK 17), then:

```bash
python tools/diff_compat_against_jar.py     # the crafted corpus, tests/fixtures/jar
python tools/diff_agency_against_jar.py     # four real agencies' recorded feeds
```

The first is green. **The second exits 1**, on the MBTA archive above, and that
is the intended state, and `tools/diff_agency_against_jar.py`'s own docstring
records what it found. Use `--drop-static-file areas.txt` to see the jar
validate the same feeds and agree byte for byte.

Upstream publishes no tag, no GitHub release and no Maven Central artifact, so
the jar has to be built from source. It does publish a container image, which
this project does not use, because a differential needs the jar's own classpath
and JDK pinned rather than an image's.

**With the recorded feed bytes but no JDK**, `tests/test_agency_goldens.py`
still checks that tier. `tests/fixtures/agencies/jar-goldens.json` commits a
SHA-256, a byte length and a rule census for every results file the jar wrote,
across four agencies and both sort regimes, and the test recomputes this
project's side and compares. The jar's bytes are not committed: the MBTA alone
is 1.7 MB of them under name sort and 3.4 MB under date sort, against 53
KB for the whole golden across all ten regimes. Regenerate
with `tools/gen_agency_goldens.py`, which needs a jar. The recorded bytes
themselves are gitignored. `tools/fetch_corpus.py` **records a fresh corpus
from live feeds and rewrites the manifest**; it cannot recover the bytes the
committed digests pin, because those feeds have moved on. So a contributor
without the recorded bytes regenerates both the corpus and the goldens rather
than reproducing these, and the committed numbers are a measurement of one
recording rather than a fixture anyone can re-obtain.

**Generated files are not hand-edited.** `src/gtfs_rt_validator/proto/schema_*.py`,
`src/gtfs_rt_validator/data/rules.json` and the clause indexes under `upstream/`
come from `tools/`. Fix the generator and re-run it, or
the drift tests start lying.

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

Pins, each watched separately, though not all by the same mechanism. The Java
rule manifest and the Best Practices document each have a committed copy, a
hand-kept `.sha256` beside it and a drift test. The proto has a committed copy
and is watched through the two schemas generated from it rather than through a
digest of its own. The 2015 bindings are not vendored at all; what pins them is
`proto/schema_2015.py`, generated from the descriptor extracted from that
artifact.

| What | Pin |
|---|---|
| `MobilityData/gtfs-realtime-validator` | `7041fa3` (2026-04-14) |
| `gtfs-realtime.proto` | `68158bd` (2026-06-30) |
| GTFS Realtime Best Practices | `5a495db` (2025-06-05) |
| Java bindings compat targets | `0.0.4` (2015-02-27) |

Upstream is pinned by commit because it has no tags, no releases and no Maven
Central artifact.

## License

MIT; see [`LICENSE`](LICENSE).

[upstream]: https://github.com/MobilityData/gtfs-realtime-validator
[sibling]: https://github.com/veodyn/gtfs-validator
