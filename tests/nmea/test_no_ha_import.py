"""SPEC NFR-02: the protocol layer must not import Home Assistant."""

import subprocess
import sys


def test_nmea_package_does_not_import_homeassistant():
    code = (
        "import sys, custom_components.vigie.nmea.ais_decoder\n"
        "bad = [m for m in sys.modules if m.split('.')[0] == 'homeassistant']\n"
        "assert not bad, bad\n"
    )
    subprocess.run([sys.executable, "-c", code], check=True)
