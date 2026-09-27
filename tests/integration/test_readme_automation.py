"""The README's collision-alert automation, run as published (SPEC §9.2, TEST E-02 prep).

The YAML block is read from README.md, so the example cannot drift from what is tested.
"""

import re
from pathlib import Path

import pytest
import yaml
from freezegun.api import FrozenDateTimeFactory
from homeassistant.core import HomeAssistant
from homeassistant.setup import async_setup_component
from pytest_homeassistant_custom_component.common import async_mock_service

from tests.helpers import BY_ID_PORT, FakePorts
from tests.integration.common import make_entry, setup
from tests.integration.test_traffic_entities import play
from tests.tools import scenario

README = Path(__file__).parents[2] / "README.md"


def readme_automation() -> dict:
    blocks = re.findall(r"```yaml\n(.*?)```", README.read_text(encoding="utf-8"), re.S)
    return next(yaml.safe_load(b) for b in blocks if b.lstrip().startswith("automation:"))


async def test_readme_automation_notifies_once_with_cpa_and_tcpa(
    hass: HomeAssistant, fake_ports: FakePorts, freezer: FrozenDateTimeFactory
):
    entry = make_entry(hass)  # boat "Garnet", as in the README
    await setup(hass, entry)
    calls = async_mock_service(hass, "notify", "mobile_app_my_phone")
    assert await async_setup_component(hass, "automation", readme_automation())

    # U-TRF-03 crossing: own position and the threat arrive in the same window, so the risk
    # goes unavailable → on; played to the end, past the CPA
    lines = scenario.generate(scenario.PRESETS["crossing"])
    await play(hass, freezer, fake_ports[BY_ID_PORT], lines)

    assert len(calls) == 1
    data = calls[0].data
    assert data["title"] == "⚠️ Collision risk"
    # Rounded to the sensors' display precision: no raw floats on the phone (E-02 pre-run)
    match = re.search(r"MMSI 235000001:\s+CPA (\d+\.\d\d) NM\s+in (\d+\.\d) min", data["message"])
    assert match, data["message"]
    assert float(match[1]) == pytest.approx(0.45, abs=0.02)
    assert float(match[2]) == pytest.approx(4.0, abs=0.2)
    assert data["data"]["priority"] == "high"
