"""Every attribute of every Vigie entity has a translated label (CLAUDE.md, TEST F-ENT-08).

Found by the P3 bench pre-run: only `ship_type` was translated; the others showed Home
Assistant's automatic English labels, and enumerated values showed raw keys. After a
scenario that fills every entity, each attribute must have a label, and each enumerated
value a translation, in strings.json, en.json and fr.json.
"""

import json
from pathlib import Path

import pytest
from freezegun.api import FrozenDateTimeFactory
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

from custom_components.vigie.const import CONF_WATCH_LIST
from custom_components.vigie.nmea.ais_decoder import NAV_STATUS
from custom_components.vigie.state import Source
from tests.helpers import BY_ID_PORT, FakePorts
from tests.integration.common import make_entry, setup
from tests.integration.test_traffic_entities import play
from tests.tools import scenario

BASE = Path(__file__).parents[2] / "custom_components" / "vigie"
FILES = ("strings.json", "translations/en.json", "translations/fr.json")

# Attributes Home Assistant adds itself (translated by HA, not by the integration)
HA_ATTRIBUTES = {
    "friendly_name",
    "unit_of_measurement",
    "device_class",
    "state_class",
    "icon",
    "source_type",
    "latitude",
    "longitude",
    "gps_accuracy",
    "options",
}

# Attributes whose values are keys shown to the user: (platform, translation key, attribute)
ENUMERATED = {
    ("device_tracker", "watched_target", "nav_status"): {*NAV_STATUS.values(), "reserved"},
    ("device_tracker", "position", "position_source"): {str(s) for s in Source},
}


def _entity_strings(name: str) -> dict:
    return json.loads((BASE / name).read_text(encoding="utf-8"))["entity"]


async def _filled_boat(hass: HomeAssistant, fake_ports: FakePorts, freezer) -> list:
    """Every Vigie entity with its attributes filled: named traffic, a threat at 60 s."""
    named = scenario.PRESETS["named-traffic"]
    entry = make_entry(hass, **{CONF_WATCH_LIST: [t.mmsi for t in named.targets]})
    await setup(hass, entry)
    lines = scenario.generate(scenario.Scenario(named.own, named.targets, 70))
    await play(hass, freezer, fake_ports[BY_ID_PORT], lines)
    return er.async_entries_for_config_entry(er.async_get(hass), entry.entry_id)


@pytest.mark.parametrize("name", FILES)
async def test_every_attribute_has_a_translated_label(
    hass: HomeAssistant, fake_ports: FakePorts, freezer: FrozenDateTimeFactory, name: str
):
    strings = _entity_strings(name)
    missing = []
    for entry in await _filled_boat(hass, fake_ports, freezer):
        state = hass.states.get(entry.entity_id)
        if state is None:
            continue  # disabled by default
        attributes = set(state.attributes) - HA_ATTRIBUTES
        assert entry.translation_key or not attributes, f"{entry.entity_id}: no translation key"
        known = (
            strings.get(entry.domain, {})
            .get(entry.translation_key or "", {})
            .get("state_attributes", {})
        )
        missing += [
            f"{entry.domain}.{entry.translation_key}.{attr}"
            for attr in sorted(attributes)
            if not known.get(attr, {}).get("name")
        ]
    assert missing == [], f"{name}: attributes without a label"


@pytest.mark.parametrize("name", FILES)
@pytest.mark.parametrize(("platform", "key", "attr"), sorted(ENUMERATED))
def test_enumerated_attribute_values_translated(name, platform, key, attr):
    states = _entity_strings(name)[platform][key]["state_attributes"][attr]["state"]
    assert set(states) == ENUMERATED[(platform, key, attr)]


async def test_own_boat_tracker_keeps_its_name(
    hass: HomeAssistant, fake_ports: FakePorts, freezer: FrozenDateTimeFactory
):
    """The translation key added for its attributes does not change its name or ID."""
    entries = await _filled_boat(hass, fake_ports, freezer)
    own = next(e for e in entries if e.unique_id.endswith("_position"))
    assert (own.entity_id, own.translation_key) == ("device_tracker.garnet", "position")
    assert hass.states.get("device_tracker.garnet").name == "Garnet"
