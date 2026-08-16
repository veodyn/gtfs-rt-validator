"""Whether an installed wheel actually carries `data/rules.json`.

`[tool.setuptools.packages.find]` ships Python modules. It does not ship data
files sitting beside them, so a package that reads its own JSON at run time can
pass every test in a source checkout and raise `FileNotFoundError` the first
time somebody installs it. That failure mode is invisible to the rest of the
suite, which imports from `src/`.

Two questions, one built wheel: is the JSON inside the archive, and can
`report/manifest.py` read it back out of a zip rather than off a directory. The
second runs in a subprocess with `-S`, so site-packages and the editable install
are out of the picture and the only place `gtfs_rt_validator` can come from is
the wheel on `PYTHONPATH`.

Building needs pip and the build backend, which pip fetches when it is not
already cached, so this skips loudly rather than failing on a machine with no
network. Everything it protects is packaging configuration, which changes in
`pyproject.toml` and nowhere else.
"""

import json
import os
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
RESOURCE = "gtfs_rt_validator/data/rules.json"
SOURCE = ROOT / "src" / RESOURCE

READ_FROM_THE_ZIP = (
    "import json\n"
    "from gtfs_rt_validator.report import manifest\n"
    "print(json.dumps({\n"
    "    'origin': manifest.__spec__.origin,\n"
    "    'ids': len(manifest.all_ids()),\n"
    "    'reachable': len(manifest.batch_reachable_ids()),\n"
    "    'w003_suffix': manifest.rule('W003').occurrence_suffix,\n"
    "    'e019_severity': manifest.rule('E019').severity,\n"
    "}))\n"
)


@pytest.fixture(scope="module")
def wheel(tmp_path_factory: pytest.TempPathFactory) -> Path:
    target = tmp_path_factory.mktemp("wheel")
    command = [sys.executable, "-m", "pip", "wheel", "--no-deps", "--wheel-dir", str(target), "."]
    try:
        # S603: argv is this file's own literals plus a pytest tmp path. The
        # rule fires on any non-literal element, and there is no external input.
        subprocess.run(command, cwd=ROOT, check=True, capture_output=True, timeout=600)  # noqa: S603
    except (OSError, subprocess.SubprocessError) as exc:
        pytest.skip(
            "NOT ENFORCED: nothing checked that the wheel ships data/rules.json. Building it "
            f"needs pip and the setuptools backend, and `{' '.join(command)}` failed ({exc}). "
            "Every other test in this suite reads the JSON out of src/, so a packaging "
            "regression would pass them all."
        )
    built = sorted(target.glob("gtfs_rt_validator-*.whl"))
    assert len(built) == 1, f"expected one wheel in {target}, found {built}"
    return built[0]


def test_the_wheel_contains_the_packed_manifest(wheel: Path):
    with zipfile.ZipFile(wheel) as archive:
        assert RESOURCE in archive.namelist(), (
            f"{wheel.name} has no {RESOURCE}. packages.find ships modules only; the JSON needs "
            "an entry under [tool.setuptools.package-data]."
        )
        assert archive.read(RESOURCE) == SOURCE.read_bytes()


def test_the_manifest_loads_from_inside_the_zip(wheel: Path):
    """`importlib.resources` over zipimport, which is what an installed wheel is
    before anything unpacks it. A loader built on `__file__` fails here."""
    environment = dict(os.environ, PYTHONPATH=str(wheel))
    result = subprocess.run(  # noqa: S603 - argv is this module's own constants
        [sys.executable, "-S", "-c", READ_FROM_THE_ZIP],
        env=environment,
        capture_output=True,
        text=True,
        check=True,
        timeout=120,
    )
    read = json.loads(result.stdout)
    assert read["origin"].startswith(str(wheel)), (
        f"the subprocess imported {read['origin']}, not the wheel; the check proved nothing"
    )
    assert read == {
        "origin": read["origin"],
        "ids": 61,
        "reachable": 56,
        "w003_suffix": "",
        "e019_severity": "ERROR",
    }
