"""The committed agency golden, loaded once, and this project's side of it.

Split out of `tests/test_agency_goldens.py` so that module is assertions and
nothing else, matching `jarcorpus.py` for the crafted corpus. Everything here is
either a read of a committed file, which works anywhere, or a call into
`tools/diff_agency_against_jar.py`, which needs the recorded bytes but never a
jar and never a JDK.

**No staging of its own.** `inputs_for`, `static_for` and `compat_side` are the
same three calls the live differential makes. The staged file names *are* the
validation clock under `--sort name`, so a second naming scheme here would
validate at different instants and then compare the results anyway.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from jarcorpus import import_tool

agencycorpus = import_tool("agencycorpus")
agencygoldens = import_tool("agencygoldens")
diff = import_tool("diff_compat_against_jar")
jarenv = import_tool("jarenv")
tool = import_tool("diff_agency_against_jar")

ROOT = Path(__file__).resolve().parent.parent
GOLDEN = json.loads(agencygoldens.GOLDEN.read_text(encoding="utf-8"))
RUNS = GOLDEN["runs"]

#: The agency whose archive the jar refuses. See `tools/gen_agency_goldens.py`
#: and `tools/diff_agency_against_jar.py` for the Java that settles why.
MBTA = "mdb-437"


def run_id(run: dict[str, Any]) -> str:
    """One regime's name, used as both the fixture key and the pytest id."""
    dropped = "".join(f" --drop-static-file {name}" for name in run["dropped_static_files"])
    return f"{run['static_mdb_id']} --sort {run['sort']}{dropped}"


IDS = [run_id(run) for run in RUNS]


def no_corpus() -> str:
    """Why the recorded bytes cannot be read, or the empty string if they can."""
    try:
        for entry in agencycorpus.manifest()["agencies"]:
            agencycorpus.verified_bytes(entry["static"])
            for record in entry["rounds"]:
                for held in record["files"].values():
                    agencycorpus.verified_bytes(held)
    except agencycorpus.CorpusMissing as absent:
        return f"the recorded agency corpus is not available: {absent}"
    return ""


class OurSides:
    """This project's output per regime, staged on first use and kept.

    Lazy rather than eager because MBTA's four regimes are most of the runtime
    and a `-k` filtered run has no business staging an 18 MB archive it will not
    look at. Kept because the whole-module run asks for each regime once and
    `test_our_mbta_output_does_not_depend_on_areas_txt` asks for two of them a
    second time.
    """

    def __init__(self, workdirs: Any) -> None:
        self._workdirs = workdirs
        self._staged: dict[str, dict[str, bytes | None]] = {}

    def __call__(self, key: str) -> dict[str, bytes | None]:
        if key not in self._staged:
            run = next(one for one in RUNS if run_id(one) == key)
            self._staged[key] = our_side(run, self._workdirs.mktemp("agency-golden"))
        return self._staged[key]


def our_side(run: dict[str, Any], workdir: Path) -> dict[str, bytes | None]:
    """This project's `--compat` output for one regime, keyed by input name.

    Raises if the archive the golden was taken over is not the archive this
    would run against, because a comparison between two feeds is not a
    comparison at all.
    """
    entry = tool.agency(run["static_mdb_id"])
    archive, static_sha = tool.static_for(entry, workdir, tuple(run["dropped_static_files"]))
    if static_sha != run["static_sha256"]:
        raise AssertionError(
            f"{run_id(run)} would run against archive {static_sha} and the golden was taken "
            f"over {run['static_sha256']}; these are not the same feed"
        )
    directory = workdir / "ours"
    directory.mkdir()
    return diff.compat_side(tool.inputs_for(entry), archive, directory, tool.SORTS[run["sort"]])
