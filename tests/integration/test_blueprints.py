"""F-TRF-13, F-ANC-11: the alarm blueprints, imported and run (WP33, #100; SPEC §9.2, §9.6).

Each blueprint is copied into Home Assistant's blueprint folder, as the import button does,
and an automation is made from it with a phone device, as the UI does.
"""

import re
import shutil
from pathlib import Path

import pytest
from freezegun.api import FrozenDateTimeFactory
from homeassistant.const import STATE_ON
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.setup import async_setup_component
from pytest_homeassistant_custom_component.common import MockConfigEntry, async_mock_service

from tests.helpers import BY_ID_PORT, FakePorts
from tests.integration.common import make_entry, setup, tick
from tests.integration.test_anchor_watch import ANCHOR, START, call, hold
from tests.integration.test_traffic_entities import play
from tests.tools import scenario

BLUEPRINTS = Path(__file__).parents[2] / "blueprints" / "automation" / "vigie"


def install(hass: HomeAssistant, name: str) -> None:
    target = Path(hass.config.path("blueprints", "automation", "vigie"))
    target.mkdir(parents=True, exist_ok=True)
    shutil.copy(BLUEPRINTS / name, target / name)


def phone(hass: HomeAssistant) -> str:
    """A companion-app phone named "My Phone": its notify action is mobile_app_my_phone."""
    entry = MockConfigEntry(domain="mobile_app")
    entry.add_to_hass(hass)
    device = dr.async_get(hass).async_get_or_create(
        config_entry_id=entry.entry_id, identifiers={("mobile_app", "phone-1")}, name="My Phone"
    )
    return device.id


async def automation(hass: HomeAssistant, name: str, inputs: dict) -> None:
    install(hass, name)
    config = {"automation": [{"use_blueprint": {"path": f"vigie/{name}", "input": inputs}}]}
    assert await async_setup_component(hass, "automation", config)
    await hass.async_block_till_done()


@pytest.mark.parametrize("name", ["collision_alert.yaml", "anchor_alarm.yaml"])
def test_blueprints_are_documented(name: str) -> None:
    text = (BLUEPRINTS / name).read_text(encoding="utf-8")
    assert f"blob/main/blueprints/automation/vigie/{name}" in text  # source_url
    readme = (Path(__file__).parents[2] / "README.md").read_text(encoding="utf-8")
    assert f"blueprints%2Fautomation%2Fvigie%2F{name}" in readme  # the import button


async def test_f_trf_13_collision_blueprint(
    hass: HomeAssistant, fake_ports: FakePorts, freezer: FrozenDateTimeFactory
):
    entry = make_entry(hass)
    await setup(hass, entry)
    calls = async_mock_service(hass, "notify", "mobile_app_my_phone")
    await automation(
        hass,
        "collision_alert.yaml",
        {"collision_risk": "binary_sensor.garnet_collision_risk", "phone": phone(hass)},
    )
    # U-TRF-03 crossing, played past the CPA: one alert for the encounter
    await play(
        hass, freezer, fake_ports[BY_ID_PORT], scenario.generate(scenario.PRESETS["crossing"])
    )
    assert len(calls) == 1
    data = calls[0].data
    assert data["title"] == "⚠️ Collision risk"
    match = re.search(r"MMSI 235000001:\s+CPA (\d+\.\d\d) NM\s+in (\d+\.\d) min", data["message"])
    assert match, data["message"]
    assert float(match[1]) == pytest.approx(0.45, abs=0.02)
    assert float(match[2]) == pytest.approx(4.0, abs=0.2)
    assert data["data"] == {
        "ttl": 0,
        "priority": "high",
        "push": {"interruption-level": "critical"},
    }


async def test_f_trf_13_collision_blueprint_not_critical(
    hass: HomeAssistant, fake_ports: FakePorts, freezer: FrozenDateTimeFactory
):
    entry = make_entry(hass)
    await setup(hass, entry)
    calls = async_mock_service(hass, "notify", "mobile_app_my_phone")
    await automation(
        hass,
        "collision_alert.yaml",
        {
            "collision_risk": "binary_sensor.garnet_collision_risk",
            "phone": phone(hass),
            "critical": False,
        },
    )
    await play(
        hass, freezer, fake_ports[BY_ID_PORT], scenario.generate(scenario.PRESETS["crossing"])
    )
    assert len(calls) == 1
    assert calls[0].data["data"] == {"priority": "high"}


async def test_f_anc_11_anchor_blueprint_drag(
    hass: HomeAssistant, fake_ports: FakePorts, freezer: FrozenDateTimeFactory
):
    entry = make_entry(hass)
    await setup(hass, entry)
    fake = fake_ports[BY_ID_PORT]
    calls = async_mock_service(hass, "notify", "mobile_app_my_phone")
    await automation(
        hass,
        "anchor_alarm.yaml",
        {"anchor_alarm": "binary_sensor.garnet_anchor_alarm", "phone": phone(hass)},
    )
    await call(hass, "drop_anchor", entry, latitude=ANCHOR[0], longitude=ANCHOR[1], radius=50)
    by_second: dict[int, list[str]] = {}
    for t, sentence in scenario.generate(scenario.PRESETS["anchor-drag"]):
        by_second.setdefault(round(t - START), []).append(sentence)
    for second in range(720):
        fake.feed_lines(*by_second[second])
        await tick(hass, freezer, 1)
    assert hass.states.get("binary_sensor.garnet_anchor_alarm").state == STATE_ON
    assert len(calls) == 1
    assert calls[0].data["title"] == "⚓ Anchor alarm"
    message = calls[0].data["message"]
    assert re.search(r"Dragging: \d+ m\s+from the anchor \(radius 50 m\)", message), message


async def test_f_anc_11_anchor_blueprint_position_lost(
    hass: HomeAssistant, fake_ports: FakePorts, freezer: FrozenDateTimeFactory
):
    entry = make_entry(hass)
    await setup(hass, entry)
    calls = async_mock_service(hass, "notify", "mobile_app_my_phone")
    await automation(
        hass,
        "anchor_alarm.yaml",
        {"anchor_alarm": "binary_sensor.garnet_anchor_alarm", "phone": phone(hass)},
    )
    await call(hass, "drop_anchor", entry, latitude=ANCHOR[0], longitude=ANCHOR[1])
    await hold(hass, freezer, None, None, 61)
    assert len(calls) == 1
    assert calls[0].data["message"].strip().startswith("No position from the receiver")
