"""Names from AIS static data in the entities — F-TRF-08 (TEST §4.4, SPEC §9.4, OD-18).

Type 5 / 24 names reach every place that shows a target's name, whether the static
report arrives before or after the first position report.
"""

import pytest
from freezegun.api import FrozenDateTimeFactory
from homeassistant.core import HomeAssistant
from pyais.encode import encode_dict
from pytest_homeassistant_custom_component.components.diagnostics import (
    get_diagnostics_for_config_entry,
)
from pytest_homeassistant_custom_component.typing import ClientSessionGenerator

from custom_components.vigie.const import CONF_WATCH_LIST
from tests.helpers import BY_ID_PORT, FakePorts
from tests.integration.common import entity_id, make_entry, setup, tick
from tests.tools import scenario

HEAD_ON = scenario.PRESETS["head-on"]  # target 235000001, 2 NM ahead: a threat at once
TARGET = HEAD_ON.targets[0]


def _own(t: float = 0) -> str:
    lat, lon = HEAD_ON.own.at(t)
    return scenario.rmc(HEAD_ON.start_epoch + t, lat, lon, 6.0, 0.0)


def _type5(name: str) -> list[str]:  # synthetic, encoded with pyais (test-only)
    msg = {"type": 5, "mmsi": TARGET.mmsi, "shipname": name, "ship_type": 70}
    return [str(line) for line in encode_dict(msg, talker_id="AI", sentence_type="VDM")]


def _type24a(name: str) -> list[str]:
    msg = {"type": 24, "mmsi": TARGET.mmsi, "partno": 0, "shipname": name}
    return [str(line) for line in encode_dict(msg, talker_id="AI", sentence_type="VDM")]


def _names(hass: HomeAssistant, entry) -> dict[str, object]:
    risk = hass.states.get(entity_id(hass, entry, "collision_risk", "binary_sensor"))
    targets = hass.states.get(entity_id(hass, entry, "ais_targets")).attributes["targets"]
    tracker = hass.states.get(f"device_tracker.ais_{TARGET.mmsi}")
    return {
        "collision_risk": risk.attributes["name"],
        "targets": targets[0]["name"] if targets else None,
        "tracker": tracker.attributes.get("name"),
    }


@pytest.fixture
async def boat(hass: HomeAssistant, fake_ports: FakePorts):
    entry = make_entry(hass, **{CONF_WATCH_LIST: [TARGET.mmsi]})
    await setup(hass, entry)
    return entry, fake_ports[BY_ID_PORT]


@pytest.mark.parametrize("static_first", [True, False])
async def test_f_trf_08_type5_name_everywhere(
    hass: HomeAssistant, boat, freezer: FrozenDateTimeFactory, static_first: bool
):
    entry, fake = boat
    position = [_own(), scenario.vdm(TARGET, 0)]
    static = _type5("CARGO ONE")
    fake.feed_lines(*(static + position if static_first else position + static))
    await tick(hass, freezer, 5)  # the targets list is rebuilt at most every 5 s
    expected = dict.fromkeys(("collision_risk", "targets", "tracker"), "CARGO ONE")
    assert _names(hass, entry) == expected


async def test_f_trf_08_class_b_name_from_type24_part_a(
    hass: HomeAssistant, boat, freezer: FrozenDateTimeFactory
):
    entry, fake = boat
    fake.feed_lines(*_type24a("ALBATROS"), _own(), scenario.vdm(TARGET, 0))
    await tick(hass, freezer, 5)
    assert _names(hass, entry)["collision_risk"] == "ALBATROS"


async def test_f_trf_08_static_counted_in_diagnostics(
    hass: HomeAssistant,
    hass_client: ClientSessionGenerator,
    boat,
    freezer: FrozenDateTimeFactory,
):
    entry, fake = boat
    fake.feed_lines(*_type5("CARGO ONE"), *_type24a("OTHER"))
    await tick(hass, freezer)
    diag = await get_diagnostics_for_config_entry(hass, hass_client, entry)
    assert diag["stats"]["ais_static"] == 2
    assert diag["targets"]["static"] == 1  # same MMSI: one entry
