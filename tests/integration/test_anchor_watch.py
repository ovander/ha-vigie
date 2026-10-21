"""Anchor watch entities, services and restore — F-ANC-01…09 (TEST §4.6, SPEC §9.6, §10.4).

Fake serial port and simulated time. Positions are given in metres from the anchor point
(43.5° N, 7.25° E), the same as the `anchor-drag` preset.
"""

import json
import math
import re
from itertools import pairwise
from pathlib import Path

import pytest
import voluptuous as vol
import yaml
from freezegun.api import FrozenDateTimeFactory
from homeassistant.const import STATE_OFF, STATE_ON, STATE_UNAVAILABLE
from homeassistant.core import Event, HomeAssistant
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import entity_registry as er
from homeassistant.setup import async_setup_component
from pytest_homeassistant_custom_component.common import async_mock_service

from custom_components.vigie.const import CONF_ANCHOR_CONFIRM, DOMAIN
from custom_components.vigie.coordinator import ANCHOR_STORE_VERSION
from custom_components.vigie.geo import EARTH_RADIUS_M
from tests.helpers import BY_ID_PORT, FakePorts
from tests.integration.common import entity_id, make_entry, setup, tick
from tests.tools import scenario

ANCHOR = (43.5, 7.25)
START = scenario.DEFAULT_START_EPOCH
README = Path(__file__).parents[2] / "README.md"
ENTITIES = (
    ("switch", "anchor_watch"),
    ("number", "anchor_radius"),
    ("binary_sensor", "anchor_alarm"),
    ("sensor", "anchor_distance"),
)


def north(d: float) -> tuple[float, float]:
    return ANCHOR[0] + math.degrees(d / EARTH_RADIUS_M), ANCHOR[1]


def rmc(position: tuple[float, float], t: float = 0) -> str:
    return scenario.rmc(START + t, *position, 0.0, 0.0)


def state(hass: HomeAssistant, entry, platform: str, key: str):
    return hass.states.get(entity_id(hass, entry, key, platform))


async def call(hass: HomeAssistant, service: str, entry, **data) -> None:
    await hass.services.async_call(
        DOMAIN, service, {"config_entry_id": entry.entry_id, **data}, blocking=True
    )
    await hass.async_block_till_done()


async def hold(hass, freezer, fake, position, seconds: int) -> None:
    """One position a second for `seconds` seconds (None: the receiver is silent)."""
    for _ in range(seconds):
        if position is not None:
            fake.feed_lines(rmc(position))
        await tick(hass, freezer, 1)


@pytest.fixture
async def boat(hass: HomeAssistant, fake_ports: FakePorts):
    entry = make_entry(hass)
    await setup(hass, entry)
    return entry, fake_ports[BY_ID_PORT]


def store_key(entry) -> str:
    return f"{DOMAIN}.anchor.{entry.entry_id}"


# --- F-ANC-01: entities -------------------------------------------------------------------


async def test_f_anc_01_entities_created(hass: HomeAssistant, boat):
    entry, _ = boat
    reg = er.async_get(hass)
    for platform, key in ENTITIES:
        e = reg.async_get(entity_id(hass, entry, key, platform))
        assert (e.unique_id, e.translation_key) == (f"{entry.entry_id}_{key}", key)
        assert e.device_id == reg.async_get(entity_id(hass, entry, "sog")).device_id
    assert hass.states.get("switch.garnet_anchor_watch").state == STATE_OFF
    radius = hass.states.get("number.garnet_anchor_radius")
    assert (float(radius.state), radius.attributes["unit_of_measurement"]) == (50.0, "m")
    assert (radius.attributes["min"], radius.attributes["max"], radius.attributes["step"]) == (
        10,
        500,
        5,
    )
    assert reg.async_get("number.garnet_anchor_radius").entity_category == "config"
    alarm = hass.states.get("binary_sensor.garnet_anchor_alarm")
    assert (alarm.state, alarm.attributes["device_class"]) == (STATE_OFF, "safety")
    distance = hass.states.get("sensor.garnet_anchor_distance")
    assert distance.state == STATE_UNAVAILABLE  # disarmed
    entry_d = reg.async_get("sensor.garnet_anchor_distance")
    assert (entry_d.original_device_class, entry_d.unit_of_measurement) == ("distance", "m")


# --- F-ANC-02: switch -----------------------------------------------------------------------


async def test_f_anc_02_switch_drops_at_own_position(
    hass: HomeAssistant, boat, freezer: FrozenDateTimeFactory
):
    _, fake = boat
    await hold(hass, freezer, fake, ANCHOR, 2)
    await hass.services.async_call(
        "switch", "turn_on", {"entity_id": "switch.garnet_anchor_watch"}, blocking=True
    )
    await hass.async_block_till_done()
    switch = hass.states.get("switch.garnet_anchor_watch")
    assert switch.state == STATE_ON
    assert switch.attributes["anchor_latitude"] == pytest.approx(ANCHOR[0], abs=1e-5)
    assert switch.attributes["anchor_longitude"] == pytest.approx(ANCHOR[1], abs=1e-5)
    assert switch.attributes["radius_m"] == 50.0
    assert switch.attributes["armed_at"] is not None
    assert float(hass.states.get("sensor.garnet_anchor_distance").state) == pytest.approx(0, abs=1)

    await hass.services.async_call(
        "switch", "turn_off", {"entity_id": "switch.garnet_anchor_watch"}, blocking=True
    )
    await hass.async_block_till_done()
    assert hass.states.get("switch.garnet_anchor_watch").state == STATE_OFF
    assert hass.states.get("sensor.garnet_anchor_distance").state == STATE_UNAVAILABLE


async def test_f_anc_02_switch_refused_without_position(hass: HomeAssistant, boat):
    with pytest.raises(HomeAssistantError) as err:
        await hass.services.async_call(
            "switch", "turn_on", {"entity_id": "switch.garnet_anchor_watch"}, blocking=True
        )
    assert err.value.translation_key == "no_own_position"
    assert hass.states.get("switch.garnet_anchor_watch").state == STATE_OFF


# --- F-ANC-03: dragging, README automation ---------------------------------------------------


def readme_anchor_automation() -> dict:
    blocks = re.findall(r"```yaml\n(.*?)```", README.read_text(encoding="utf-8"), re.S)
    return next(yaml.safe_load(b) for b in blocks if "anchor_alarm" in b)


async def test_f_anc_03_anchor_drag_preset_and_readme_automation(
    hass: HomeAssistant, boat, freezer: FrozenDateTimeFactory
):
    entry, fake = boat
    calls = async_mock_service(hass, "notify", "mobile_app_my_phone")
    assert await async_setup_component(hass, "automation", readme_anchor_automation())
    writes: list[str] = []

    def on_change(event: Event) -> None:
        if event.data["entity_id"] == "sensor.garnet_anchor_distance":
            writes.append(event.data["new_state"].state)

    hass.bus.async_listen("state_changed", on_change)
    await call(hass, "drop_anchor", entry, latitude=ANCHOR[0], longitude=ANCHOR[1], radius=50)

    lines = scenario.generate(scenario.PRESETS["anchor-drag"])
    by_second: dict[int, list[str]] = {}
    for t, sentence in lines:
        by_second.setdefault(round(t - START), []).append(sentence)
    alarm_at = None
    for second in range(800):
        fake.feed_lines(*by_second[second])
        await tick(hass, freezer, 1)
        alarm = hass.states.get("binary_sensor.garnet_anchor_alarm")
        if alarm_at is None and alarm.state == STATE_ON:
            alarm_at = second
            assert alarm.attributes["reason"] == "drag"
    reference = scenario.ANCHOR_DRAG.leaves_radius_at(50) + 20  # `--list`: 698 s
    assert alarm_at == pytest.approx(reference, abs=1)

    assert len(calls) == 1
    message = calls[0].data["message"]
    assert re.search(r"Dragging: \d+ m\s+from the anchor \(radius 50 m\)", message), message
    assert calls[0].data["title"] == "⚓ Anchor alarm"

    # At most one write a second, each at least 1 m from the previous one
    values = [float(v) for v in writes[1:]]  # the first is the drop itself
    assert len(writes) <= 800
    assert all(abs(b - a) >= 1 - 1e-9 for a, b in pairwise(values))
    distance = hass.states.get("sensor.garnet_anchor_distance")
    assert distance.attributes["max_distance_m"] >= 50
    assert distance.attributes["bearing_to_anchor"] == pytest.approx(180, abs=1)
    assert (distance.attributes["latitude"], distance.attributes["longitude"]) == ANCHOR


async def test_f_anc_03_readme_automation_position_lost_message(
    hass: HomeAssistant, boat, freezer: FrozenDateTimeFactory
):
    entry, _ = boat
    calls = async_mock_service(hass, "notify", "mobile_app_my_phone")
    assert await async_setup_component(hass, "automation", readme_anchor_automation())
    await call(hass, "drop_anchor", entry, latitude=ANCHOR[0], longitude=ANCHOR[1])
    await hold(hass, freezer, None, None, 61)
    assert len(calls) == 1
    assert calls[0].data["message"].strip().startswith("No position from the receiver")


# --- F-ANC-04: services ------------------------------------------------------------------------


async def test_f_anc_04_drop_anchor_with_point_and_radius(
    hass: HomeAssistant, boat, freezer: FrozenDateTimeFactory
):
    entry, fake = boat
    await call(hass, "drop_anchor", entry, latitude=43.51, longitude=7.26, radius=80)
    switch = hass.states.get("switch.garnet_anchor_watch")
    assert switch.state == STATE_ON
    assert (switch.attributes["anchor_latitude"], switch.attributes["anchor_longitude"]) == (
        43.51,
        7.26,
    )
    assert float(hass.states.get("number.garnet_anchor_radius").state) == 80.0

    # Radius only: at own position
    await hold(hass, freezer, fake, north(100), 2)
    await call(hass, "drop_anchor", entry, radius=35)
    switch = hass.states.get("switch.garnet_anchor_watch")
    assert switch.attributes["anchor_latitude"] == pytest.approx(north(100)[0], abs=1e-5)
    assert switch.attributes["radius_m"] == 35.0

    await call(hass, "raise_anchor", entry)
    assert hass.states.get("switch.garnet_anchor_watch").state == STATE_OFF
    assert hass.states.get("binary_sensor.garnet_anchor_alarm").state == STATE_OFF


@pytest.mark.parametrize(
    "data",
    [
        {"latitude": 43.5},  # longitude missing
        {"longitude": 7.25},
        {"latitude": 91, "longitude": 7.25},
        {"latitude": 43.5, "longitude": 7.25, "radius": 5},
        {"latitude": 43.5, "longitude": 7.25, "radius": 501},
    ],
)
async def test_f_anc_04_invalid_drop_refused(hass: HomeAssistant, boat, data):
    entry, _ = boat
    with pytest.raises(vol.Invalid):
        await call(hass, "drop_anchor", entry, **data)
    assert hass.states.get("switch.garnet_anchor_watch").state == STATE_OFF


async def test_f_anc_04_drop_without_position_refused(hass: HomeAssistant, boat):
    entry, _ = boat
    with pytest.raises(HomeAssistantError) as err:
        await call(hass, "drop_anchor", entry)
    assert err.value.translation_key == "no_own_position"


async def test_f_anc_04_unknown_or_unloaded_entry(hass: HomeAssistant, boat):
    entry, _ = boat
    with pytest.raises(ServiceValidationError) as err:
        await hass.services.async_call(
            DOMAIN, "raise_anchor", {"config_entry_id": "nope"}, blocking=True
        )
    assert err.value.translation_key == "unknown_entry"
    await hass.config_entries.async_unload(entry.entry_id)
    with pytest.raises(ServiceValidationError) as err:
        await call(hass, "raise_anchor", entry)
    assert err.value.translation_key == "entry_not_loaded"


# --- F-ANC-05: position lost ---------------------------------------------------------------------


async def test_f_anc_05_gps_silent(hass: HomeAssistant, boat, freezer: FrozenDateTimeFactory):
    entry, fake = boat
    await hold(hass, freezer, fake, north(10), 2)
    await call(hass, "drop_anchor", entry, latitude=ANCHOR[0], longitude=ANCHOR[1])
    await hold(hass, freezer, fake, north(10), 2)
    await hold(hass, freezer, fake, None, 55)
    alarm = hass.states.get("binary_sensor.garnet_anchor_alarm")
    assert alarm.state == STATE_OFF
    assert hass.states.get("sensor.garnet_anchor_distance").state == STATE_UNAVAILABLE
    await hold(hass, freezer, fake, None, 6)
    alarm = hass.states.get("binary_sensor.garnet_anchor_alarm")
    assert (alarm.state, alarm.attributes["reason"]) == (STATE_ON, "no_position")
    await hold(hass, freezer, fake, north(10), 1)
    alarm = hass.states.get("binary_sensor.garnet_anchor_alarm")
    assert (alarm.state, alarm.attributes["reason"]) == (STATE_OFF, None)


async def test_f_anc_05_port_disconnected(
    hass: HomeAssistant, boat, freezer: FrozenDateTimeFactory
):
    entry, fake = boat
    await hold(hass, freezer, fake, north(10), 2)
    await call(hass, "drop_anchor", entry)
    fake.available = False
    fake.disconnect()
    await hold(hass, freezer, None, None, 59)
    alarm = hass.states.get("binary_sensor.garnet_anchor_alarm")
    assert alarm.state == STATE_OFF  # available, not hidden by the outage
    await hold(hass, freezer, None, None, 2)
    alarm = hass.states.get("binary_sensor.garnet_anchor_alarm")
    assert (alarm.state, alarm.attributes["reason"]) == (STATE_ON, "no_position")
    assert hass.states.get("switch.garnet_anchor_watch").state == STATE_ON


# --- F-ANC-06: restart --------------------------------------------------------------------------


def stored(entry, watch: dict | None, radius: float = 30.0) -> dict:
    return {
        "version": ANCHOR_STORE_VERSION,
        "minor_version": 1,
        "key": store_key(entry),
        "data": {"radius_m": radius, "watch": watch},
    }


WATCH = {
    "latitude": ANCHOR[0],
    "longitude": ANCHOR[1],
    "radius_m": 30.0,
    "armed_at": 1_790_000_000.0,
    "max_distance_m": 62.0,
    "alarm": "drag",
}


async def test_f_anc_06_restored_after_restart(
    hass: HomeAssistant, hass_storage, fake_ports: FakePorts, freezer: FrozenDateTimeFactory
):
    entry = make_entry(hass)
    hass_storage[store_key(entry)] = stored(entry, WATCH)
    await setup(hass, entry)
    switch = hass.states.get("switch.garnet_anchor_watch")
    assert switch.state == STATE_ON
    assert (switch.attributes["anchor_latitude"], switch.attributes["radius_m"]) == (43.5, 30.0)
    assert switch.attributes["armed_at"].timestamp() == 1_790_000_000.0
    alarm = hass.states.get("binary_sensor.garnet_anchor_alarm")
    assert (alarm.state, alarm.attributes["reason"]) == (STATE_ON, "drag")  # still latched
    assert float(hass.states.get("number.garnet_anchor_radius").state) == 30.0

    fake = fake_ports[BY_ID_PORT]
    await hold(hass, freezer, fake, north(5), 2)
    distance = hass.states.get("sensor.garnet_anchor_distance")
    assert distance.attributes["max_distance_m"] == 62.0
    assert hass.states.get("binary_sensor.garnet_anchor_alarm").state == STATE_ON


async def test_f_anc_06_no_position_after_restart(
    hass: HomeAssistant, hass_storage, fake_ports: FakePorts, freezer: FrozenDateTimeFactory
):
    entry = make_entry(hass)
    hass_storage[store_key(entry)] = stored(entry, {**WATCH, "alarm": None})
    await setup(hass, entry)
    assert hass.states.get("binary_sensor.garnet_anchor_alarm").state == STATE_OFF
    await hold(hass, freezer, None, None, 61)
    alarm = hass.states.get("binary_sensor.garnet_anchor_alarm")
    assert (alarm.state, alarm.attributes["reason"]) == (STATE_ON, "no_position")


async def test_f_anc_06_saved_within_seconds(
    hass: HomeAssistant, hass_storage, boat, freezer: FrozenDateTimeFactory
):
    """Saved about 1 s after a change, so a power cut right after anchoring keeps it."""
    entry, _ = boat
    await call(hass, "drop_anchor", entry, latitude=ANCHOR[0], longitude=ANCHOR[1], radius=40)
    await tick(hass, freezer, 2)
    data = hass_storage[store_key(entry)]["data"]
    assert data["radius_m"] == 40.0
    assert (data["watch"]["latitude"], data["watch"]["alarm"]) == (43.5, None)
    await call(hass, "raise_anchor", entry)
    await tick(hass, freezer, 2)
    assert hass_storage[store_key(entry)]["data"] == {"radius_m": 40.0, "watch": None}


async def test_f_anc_06_invalid_store_starts_disarmed(
    hass: HomeAssistant, hass_storage, fake_ports: FakePorts
):
    entry = make_entry(hass)
    hass_storage[store_key(entry)] = stored(entry, {**WATCH, "latitude": 123.0})
    await setup(hass, entry)
    assert hass.states.get("switch.garnet_anchor_watch").state == STATE_OFF
    assert float(hass.states.get("number.garnet_anchor_radius").state) == 30.0


async def test_f_anc_06_removed_with_the_entry(hass: HomeAssistant, hass_storage, boat):
    entry, _ = boat
    await call(hass, "drop_anchor", entry, latitude=ANCHOR[0], longitude=ANCHOR[1])
    await hass.config_entries.async_remove(entry.entry_id)
    await hass.async_block_till_done()
    assert store_key(entry) not in hass_storage


# --- F-ANC-07: radius ----------------------------------------------------------------------------


async def test_f_anc_07_radius_change_applied_and_kept(
    hass: HomeAssistant, boat, freezer: FrozenDateTimeFactory
):
    entry, fake = boat
    await hold(hass, freezer, fake, north(60), 2)
    await call(hass, "drop_anchor", entry, latitude=ANCHOR[0], longitude=ANCHOR[1], radius=80)
    await hass.services.async_call(
        "number",
        "set_value",
        {"entity_id": "number.garnet_anchor_radius", "value": 40},
        blocking=True,
    )
    await hass.async_block_till_done()
    assert hass.states.get("switch.garnet_anchor_watch").attributes["radius_m"] == 40.0
    assert hass.states.get("sensor.garnet_anchor_distance").attributes["radius_m"] == 40.0
    await hold(hass, freezer, fake, north(60), 21)
    assert hass.states.get("binary_sensor.garnet_anchor_alarm").state == STATE_ON

    assert await hass.config_entries.async_reload(entry.entry_id)  # same as a restart
    await hass.async_block_till_done()
    assert float(hass.states.get("number.garnet_anchor_radius").state) == 40.0
    assert hass.states.get("switch.garnet_anchor_watch").state == STATE_ON
    assert hass.states.get("binary_sensor.garnet_anchor_alarm").state == STATE_ON


async def test_f_anc_07_confirmation_option(
    hass: HomeAssistant, fake_ports: FakePorts, freezer: FrozenDateTimeFactory
):
    entry = make_entry(hass, **{CONF_ANCHOR_CONFIRM: 5})
    await setup(hass, entry)
    fake = fake_ports[BY_ID_PORT]
    await call(hass, "drop_anchor", entry, latitude=ANCHOR[0], longitude=ANCHOR[1])
    await hold(hass, freezer, fake, north(60), 7)
    assert hass.states.get("binary_sensor.garnet_anchor_alarm").state == STATE_ON


# --- F-ANC-08: translations ----------------------------------------------------------------------

BASE = Path(__file__).parents[2] / "custom_components" / "vigie"


@pytest.mark.parametrize("name", ["strings.json", "translations/en.json", "translations/fr.json"])
def test_f_anc_08_reason_services_and_errors_translated(name):
    strings = json.loads((BASE / name).read_text(encoding="utf-8"))
    reason = strings["entity"]["binary_sensor"]["anchor_alarm"]["state_attributes"]["reason"]
    assert set(reason["state"]) == {"drag", "no_position"}
    services = yaml.safe_load((BASE / "services.yaml").read_text(encoding="utf-8"))
    for service, spec in services.items():
        assert strings["services"][service]["name"]
        assert set(strings["services"][service]["fields"]) == set(spec["fields"])
    assert {"no_own_position", "unknown_entry", "entry_not_loaded"} <= set(strings["exceptions"])
    options = strings["options"]["step"]["init"]
    assert {"anchor_confirm", "anchor_position_timeout"} <= set(options["data"])


# --- F-ANC-09: two boats -------------------------------------------------------------------------


async def test_f_anc_09_two_boats_independent(
    hass: HomeAssistant, fake_ports: FakePorts, freezer: FrozenDateTimeFactory
):
    first = make_entry(hass)
    second = make_entry(hass, port="/dev/ttyUSB1", title="Jade")
    await setup(hass, first)
    await call(hass, "drop_anchor", first, latitude=43.5, longitude=7.25, radius=50)
    await call(hass, "drop_anchor", second, latitude=43.6, longitude=7.35, radius=70)
    one = hass.states.get("switch.garnet_anchor_watch").attributes
    two = hass.states.get("switch.jade_anchor_watch").attributes
    assert (one["anchor_latitude"], one["radius_m"]) == (43.5, 50.0)
    assert (two["anchor_latitude"], two["radius_m"]) == (43.6, 70.0)
    await call(hass, "raise_anchor", second)
    assert hass.states.get("switch.garnet_anchor_watch").state == STATE_ON
    assert hass.states.get("switch.jade_anchor_watch").state == STATE_OFF
