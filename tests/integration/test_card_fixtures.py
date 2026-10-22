"""States recorded for the traffic map card's tests (TEST §4.7, SPEC §9.7, OD-31).

The card repository (`ovander/ha-vigie-card`) tests its rendering against these states, so
both repositories agree on the format of the `targets` rows. The fixtures are checked here
against what Vigie produces now; regenerate them with `VIGIE_UPDATE_CARD_FIXTURES=1 pytest
tests/integration/test_card_fixtures.py` and copy them to the card's `test/fixtures/`.
"""

import json
import math
import os
from pathlib import Path

import pytest
from freezegun.api import FrozenDateTimeFactory
from homeassistant.core import HomeAssistant

from custom_components.vigie.const import CONF_WATCH_LIST, DOMAIN
from tests.helpers import BY_ID_PORT, FakePorts
from tests.integration.common import make_entry, setup
from tests.integration.test_traffic_entities import play
from tests.tools import scenario

FIXTURES = Path(__file__).parents[1] / "fixtures" / "card"
ENTITIES = (
    "sensor.garnet_ais_targets",
    "device_tracker.garnet",
    "binary_sensor.garnet_collision_risk",
    "sensor.garnet_anchor_distance",
    "sensor.garnet_closest_threat_cpa",
    "sensor.garnet_closest_threat_tcpa",
)
# Played long enough for the names (30 s) and a threat; the anchor is dropped at the start
# with a radius the boat stays inside
CASES = {"multi-target": 70, "named-traffic": 70}


def _record(hass: HomeAssistant) -> dict:
    out = {}
    for entity_id in ENTITIES:
        state = hass.states.get(entity_id)
        attrs = dict(state.attributes)
        attrs.pop("friendly_name", None)
        out[entity_id] = {"state": state.state, "attributes": attrs}
    # Plain JSON, as the card receives it over the WebSocket API
    return json.loads(json.dumps(out, default=str))


def _same(a, b, path="") -> list[str]:
    """Differences between two JSON values; floats compared to 1e-9 (libm may differ)."""
    if isinstance(a, float) and isinstance(b, int | float) and not isinstance(b, bool):
        return [] if math.isclose(a, b, rel_tol=1e-9, abs_tol=1e-9) else [f"{path}: {a} != {b}"]
    if type(a) is not type(b):
        return [f"{path}: {a!r} != {b!r}"]
    if isinstance(a, dict):
        if set(a) != set(b):
            return [f"{path}: keys {sorted(set(a) ^ set(b))}"]
        return [d for k in a for d in _same(a[k], b[k], f"{path}.{k}")]
    if isinstance(a, list):
        if len(a) != len(b):
            return [f"{path}: length {len(a)} != {len(b)}"]
        pairs = enumerate(zip(a, b, strict=True))
        return [d for i, (x, y) in pairs for d in _same(x, y, f"{path}[{i}]")]
    return [] if a == b else [f"{path}: {a!r} != {b!r}"]


@pytest.mark.parametrize(("preset", "seconds"), sorted(CASES.items()))
async def test_card_fixture_states(
    hass: HomeAssistant,
    fake_ports: FakePorts,
    freezer: FrozenDateTimeFactory,
    preset: str,
    seconds: int,
):
    chosen = scenario.PRESETS[preset]
    watch = [t.mmsi for t in chosen.targets][:2] if preset == "named-traffic" else []
    entry = make_entry(hass, **{CONF_WATCH_LIST: watch})
    await setup(hass, entry)
    lines = scenario.generate(scenario.Scenario(chosen.own, chosen.targets, seconds))
    first = [line for line in lines if line[0] == lines[0][0]]
    fake = fake_ports[BY_ID_PORT]
    await play(hass, freezer, fake, first)  # own position known before the drop
    await hass.services.async_call(
        DOMAIN, "drop_anchor", {"config_entry_id": entry.entry_id, "radius": 500}, blocking=True
    )
    await play(hass, freezer, fake, lines[len(first) :])
    states = _record(hass)

    rows = states["sensor.garnet_ais_targets"]["attributes"]["targets"]
    assert rows and all({"heading", "threat", "lat", "lon", "cog"} <= set(r) for r in rows)
    assert any(r["threat"] for r in rows), "the card's threat drawing needs a threat"
    assert states["sensor.garnet_anchor_distance"]["attributes"]["radius_m"] == 500

    path = FIXTURES / f"{preset}.json"
    if os.environ.get("VIGIE_UPDATE_CARD_FIXTURES"):
        FIXTURES.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(states, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    committed = json.loads(path.read_text(encoding="utf-8"))
    assert _same(states, committed) == [], "regenerate with VIGIE_UPDATE_CARD_FIXTURES=1"
