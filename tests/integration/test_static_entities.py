"""Static data on the entities — F-TRF-09, F-TRF-10, F-TRF-11 (TEST §4.4, SPEC §9.2–9.4).

Ship type (category key and code), call sign, IMO, length, beam, draught and destination
(SPEC OD-17, OD-20) on the closest target/threat sensors, `collision_risk` and the
watch-list trackers; ship type and length in the compact `targets` list.
"""

import json
from pathlib import Path

import pytest
from freezegun.api import FrozenDateTimeFactory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.translation import async_get_translations
from pyais.encode import encode_dict

from custom_components.vigie.const import CONF_WATCH_LIST, DOMAIN
from custom_components.vigie.nmea.ais_decoder import SHIP_TYPE_CATEGORIES
from tests.helpers import BY_ID_PORT, FakePorts
from tests.integration.common import entity_id, make_entry, setup, tick
from tests.tools import scenario
from tests.tools.scenario import Target, Track, relative

OWN = scenario.PRESETS["head-on"].own
START = scenario.DEFAULT_START_EPOCH
MMSI = 235000001
CARGO = {
    "shipname": "CARGO ONE",
    "ship_type": 70,
    "callsign": "ABCD",
    "imo": 9123456,
    "to_bow": 150,
    "to_stern": 30,
    "to_port": 15,
    "to_starboard": 15,
    "draught": 8.5,
    "destination": "MARSEILLE",
}
EXPECTED = {
    "ship_type": "cargo",
    "ship_type_code": 70,
    "callsign": "ABCD",
    "imo": 9123456,
    "length_m": 180,
    "beam_m": 30,
    "draught_m": 8.5,
    "destination": "MARSEILLE",
}
UNKNOWN = dict.fromkeys(EXPECTED)
STATIC_KEYS = tuple(EXPECTED)

# Every entity that describes one target in full (platform, translation key)
TARGET_ENTITIES = (
    ("binary_sensor", "collision_risk"),
    ("sensor", "closest_target_distance"),
    ("sensor", "closest_threat_cpa"),
    ("sensor", "closest_threat_tcpa"),
    ("device_tracker", "watched_target"),
)
ENTITY_KEYS = tuple(key for _, key in TARGET_ENTITIES)


def _type5(**fields) -> list[str]:
    msg = {"type": 5, "mmsi": MMSI, **fields}
    return [str(line) for line in encode_dict(msg, talker_id="AI", sentence_type="VDM")]


def _own(t: float = 0) -> str:
    lat, lon = OWN.at(t)
    return scenario.rmc(START + t, lat, lon, OWN.sog_kn, OWN.cog_deg)


# Stationary target 1 NM ahead (not anchored): a threat, and nothing about it moves, so
# only static data can make its entities write again
STILL = Target(MMSI, Track(*relative(OWN.lat, OWN.lon, 0, 1), 0.0, 0.0))


def _static_attrs(hass: HomeAssistant, entry) -> dict[str, dict]:
    out = {}
    for platform, key in TARGET_ENTITIES:
        if platform == "device_tracker":
            state = hass.states.get(f"device_tracker.ais_{MMSI}")
        else:
            state = hass.states.get(entity_id(hass, entry, key, platform))
        out[key] = {k: state.attributes.get(k) for k in STATIC_KEYS}
    return out


def _target_row(hass: HomeAssistant, entry) -> dict:
    rows = hass.states.get(entity_id(hass, entry, "ais_targets")).attributes["targets"]
    return next(r for r in rows if r["mmsi"] == MMSI)


@pytest.fixture
async def boat(hass: HomeAssistant, fake_ports: FakePorts):
    entry = make_entry(hass, **{CONF_WATCH_LIST: [MMSI]})
    await setup(hass, entry)
    return entry, fake_ports[BY_ID_PORT]


# --- F-TRF-09 ------------------------------------------------------------------------------


async def test_f_trf_09_static_fields_on_every_target_entity(
    hass: HomeAssistant, boat, freezer: FrozenDateTimeFactory
):
    entry, fake = boat
    fake.feed_lines(*_type5(**CARGO), _own(), scenario.vdm(STILL, 0))
    await tick(hass, freezer, 5)
    assert _static_attrs(hass, entry) == dict.fromkeys(ENTITY_KEYS, EXPECTED)
    row = _target_row(hass, entry)
    assert (row["ship_type"], row["length_m"]) == ("cargo", 180)
    assert "callsign" not in row  # the list stays compact


async def test_f_trf_09_unknown_static_data_is_none(
    hass: HomeAssistant, boat, freezer: FrozenDateTimeFactory
):
    entry, fake = boat
    fake.feed_lines(_own(), scenario.vdm(STILL, 0))
    await tick(hass, freezer, 5)
    assert _static_attrs(hass, entry) == dict.fromkeys(ENTITY_KEYS, UNKNOWN)
    row = _target_row(hass, entry)
    assert (row["ship_type"], row["length_m"]) == (None, None)


# --- F-TRF-10 ------------------------------------------------------------------------------


async def test_f_trf_10_static_data_after_the_position_is_written(
    hass: HomeAssistant, boat, freezer: FrozenDateTimeFactory
):
    """The risk stays on for the same target and the tracker's position does not move:
    only the static data changes, and it must still reach the UI."""
    entry, fake = boat
    fake.feed_lines(_own(), scenario.vdm(STILL, 0))
    await tick(hass, freezer, 5)
    risk_id = entity_id(hass, entry, "collision_risk", "binary_sensor")
    before = hass.states.get(risk_id).last_updated
    assert hass.states.get(risk_id).attributes["name"] is None

    fake.feed_lines(_own(5), scenario.vdm(STILL, 5), *_type5(**CARGO))
    await tick(hass, freezer, 5)
    risk = hass.states.get(risk_id)
    assert risk.state == "on" and risk.last_updated > before
    assert (risk.attributes["name"], risk.attributes["ship_type"]) == ("CARGO ONE", "cargo")
    tracker = hass.states.get(f"device_tracker.ais_{MMSI}").attributes
    assert (tracker["name"], tracker["length_m"]) == ("CARGO ONE", 180)

    # A later change (new destination) is written too
    fake.feed_lines(_own(10), *_type5(**{**CARGO, "destination": "SETE"}))
    await tick(hass, freezer, 5)
    assert hass.states.get(risk_id).attributes["destination"] == "SETE"
    assert hass.states.get(f"device_tracker.ais_{MMSI}").attributes["destination"] == "SETE"


# --- F-TRF-11 ------------------------------------------------------------------------------

BASE = Path(__file__).parents[2] / "custom_components" / "vigie"


@pytest.mark.parametrize("name", ["strings.json", "translations/en.json", "translations/fr.json"])
def test_f_trf_11_every_category_translated_for_every_entity(name):
    entity = json.loads((BASE / name).read_text(encoding="utf-8"))["entity"]
    for platform, key in TARGET_ENTITIES:
        states = entity[platform][key]["state_attributes"]["ship_type"]["state"]
        assert set(states) == set(SHIP_TYPE_CATEGORIES), (name, platform, key)


async def test_f_trf_11_french_categories_loaded(hass: HomeAssistant, boat):
    strings = await async_get_translations(hass, "fr", "entity", {DOMAIN})
    prefix = f"component.{DOMAIN}.entity"
    risk = f"{prefix}.binary_sensor.collision_risk.state_attributes.ship_type.state"
    tracker = f"{prefix}.device_tracker.watched_target.state_attributes.ship_type.state"
    assert strings[f"{risk}.sailing"] == "Voilier"
    assert strings[f"{tracker}.cargo"] == "Cargo"
