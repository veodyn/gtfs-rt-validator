"""The committed jar corpus, staged and run through this project's compat side.

`tests/test_compat_writer.py` byte-compares what this project writes against the
five `.results.json` files a real jar wrote for the same eight inputs. Getting the
two runs to be about the same thing needs three fixed conditions, and they are
here rather than in the test module because none of them is what that module is
asserting.

**The mtimes are the jar's.** Upstream reads a file's modification time as the
clock, so `W008` ("header timestamp is N minutes old") is arithmetic between the
feed's own header timestamp and the mtime the file was stamped with.
`tools/run_jar.stage` is what stamped them when the goldens were generated, so it
is what stamps them here; the manifest records the result and
`tests/test_jar_goldens.py` pins that the two agree.

**The static feed is the committed one, unmodified.** It used to be staged
through a copy with its two lettered `direction_id` cells blanked, because
compat read its static feed through the sibling's strict typed path and that
path refuses `testagency.zip` outright. Compat reads it as onebusaway's
`GtfsReader` does now, so the goldens are compared against the archive they were
measured against.

**Nothing is written into the committed corpus directory.** Upstream walks every
regular file with no extension filter, so a run that wrote its results beside the
committed inputs would leave a directory whose next run ingests its own output.
Everything below stages into a `tmp_path`.

The staging and the byte comparison themselves are `tools/diff_compat_against_jar.py`'s,
imported rather than restated: that tool runs the same compat path against a live
jar, and two copies of "how a compat run is staged" would be two things to keep
in step.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from gtfs_rt_validator.report import compat
from jarcorpus import INPUTS, import_tool, input_bytes

diff = import_tool("diff_compat_against_jar")

#: The archive the goldens were produced against, from the tool that owns where
#: it lives rather than from a path rebuilt here.
GOLDEN_GTFS = import_tool("jarenv").GOLDEN_GTFS

#: Re-exported so a test module imports one name from one place. The helper
#: itself lives beside the differential that needs it most.
first_difference = diff.first_difference


@dataclass(frozen=True)
class Staged:
    """One compat run over the corpus: where it ran and what it wrote."""

    directory: Path
    gtfs: Path
    written: dict[str, bytes]

    def results_for(self, name: str) -> bytes | None:
        """The bytes written beside one input, or `None` for a file we skipped."""
        return self.written.get(f"{name}{compat.RESULTS_SUFFIX}")


def compat_run(tmp_path: Path) -> Staged:
    """Validate the whole corpus under `--compat`, writing beside each input."""
    directory = tmp_path / "corpus"
    directory.mkdir()
    inputs = {entry["name"]: input_bytes(entry["name"]) for entry in INPUTS}
    diff.compat_side(inputs, GOLDEN_GTFS, directory)
    return Staged(
        directory=directory,
        gtfs=GOLDEN_GTFS,
        written={
            path.name: path.read_bytes()
            for path in sorted(directory.iterdir())
            if path.name.endswith(compat.RESULTS_SUFFIX)
        },
    )
