"""The version has one home, and `pyproject.toml` must agree with it.

`version.py` is the single source; the packaging metadata is a copy. A copy that
can drift silently ends up in a report field, so the suite compares them.
"""

import tomllib
from pathlib import Path

import gtfs_rt_validator
from gtfs_rt_validator.version import VERSION


def test_the_package_exports_the_version_from_its_one_home():
    assert gtfs_rt_validator.__version__ == VERSION


def test_pyproject_agrees_with_version_py():
    pyproject = tomllib.loads(Path("pyproject.toml").read_text())
    assert pyproject["project"]["version"] == VERSION
