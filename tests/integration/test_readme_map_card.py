"""The README's map card, checked against real entities (SPEC §13 P3, OD-19).

The card YAML is read from README.md: every entity it names must exist for a boat named
"Garnet" with the card's MMSIs on its watch list, and show a position once the
`named-traffic` scenario has played.
"""

import re
from pathlib import Path

import yaml
from freezegun.api import FrozenDateTimeFactory
from homeassistant.const import STATE_UNAVAILABLE
from homeassistant.core import HomeAssistant

from custom_components.vigie.const import CONF_WATCH_LIST
from tests.helpers import BY_ID_PORT, FakePorts
from tests.integration.common import make_entry, setup
from tests.integration.test_traffic_entities import play
from tests.tools import scenario

README = Path(__file__).parents[2] / "README.md"


def readme_map_card() -> dict:
    blocks = re.findall(r"```yaml\n(.*?)```", README.read_text(encoding="utf-8"), re.S)
    return next(yaml.safe_load(b) for b in blocks if b.lstrip().startswith("type: map"))


async def test_readme_map_card_entities_exist_and_show_the_boats(
    hass: HomeAssistant, fake_ports: FakePorts, freezer: FrozenDateTimeFactory
):
    card = readme_map_card()
    assert card["type"] == "map"
    entities = [e["entity"] if isinstance(e, dict) else e for e in card["entities"]]
    watched = [int(e.rsplit("_", 1)[1]) for e in entities if e.startswith("device_tracker.ais_")]
    assert watched, "the card shows at least one watched target"

    entry = make_entry(hass, **{CONF_WATCH_LIST: watched})  # boat "Garnet", as in the README
    await setup(hass, entry)
    named = scenario.PRESETS["named-traffic"]
    assert set(watched) <= {t.mmsi for t in named.targets}
    lines = scenario.generate(scenario.Scenario(named.own, named.targets, 40))
    await play(hass, freezer, fake_ports[BY_ID_PORT], lines)

    for entity_id in entities:
        state = hass.states.get(entity_id)
        assert state is not None, entity_id
        assert state.state != STATE_UNAVAILABLE, entity_id
        assert "latitude" in state.attributes and "longitude" in state.attributes, entity_id
    names = {hass.states.get(e).attributes.get("name") for e in entities[1:]}
    assert names == {"CARGO ONE", "ALBATROS"}  # static data arrived at 30 s
