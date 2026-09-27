"""SPEC NFR-02: the pure modules must not import Home Assistant."""

import subprocess
import sys

import pytest

PURE_MODULES = [
    "custom_components.vigie.nmea.ais_decoder",
    "custom_components.vigie.nmea.sentence",
    "custom_components.vigie.nmea.parsers",
    "custom_components.vigie.geo",
    "custom_components.vigie.state",
]


@pytest.mark.parametrize("module", PURE_MODULES)
def test_pure_module_does_not_import_homeassistant(module):
    code = (
        f"import sys, {module}\n"
        "bad = [m for m in sys.modules if m.split('.')[0] == 'homeassistant']\n"
        "assert not bad, bad\n"
    )
    subprocess.run([sys.executable, "-c", code], check=True)
