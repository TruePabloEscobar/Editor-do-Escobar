"""Prevent reintroducing tool versions with known packaging/temp-directory advisories."""

import tomllib
from importlib.metadata import version
from pathlib import Path

from packaging.requirements import Requirement
from packaging.version import Version


def test_installed_packaging_tools_and_constraints_have_security_floors():
    project = tomllib.loads((Path(__file__).resolve().parents[2] / "pyproject.toml").read_text())
    dev = {
        Requirement(r).name: Requirement(r)
        for r in project["project"]["optional-dependencies"]["dev"]
    }
    for name, minimum, old in (
        ("pip", "26.2", "26.1.2"),
        ("setuptools", "83", "65.5.0"),
        ("pytest", "9.0.3", "8.4.2"),
    ):
        assert Version(version(name)) >= Version(minimum)
        assert Version(old) not in dev[name].specifier
        assert Version(minimum) in dev[name].specifier
