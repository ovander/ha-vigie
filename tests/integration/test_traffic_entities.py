"""Traffic behaviour — F-TRF-01, 02, 03, 04, 06, 07 (TEST §4.4, SPEC §8.2, §9.2, §10.1).

Synthetic D-07 traffic from tests/tools/scenario.py, fed through the fake port in simulated
time (freezer). Expected values follow TEST §3.4 (hand-computed).
"""

import math
from collections import defaultdict

import pytest
from freezegun.api import FrozenDateTimeFactory
from homeassistant.const import STATE_OFF, STATE_ON, STATE_UNAVAILABLE, UnitOfLength
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.setup import async_setup_component
from homeassistant.util import dt as dt_util
from homeassistant.util.unit_system import METRIC_SYSTEM
from pytest_homeassistant_custom_component.common import async_mock_service

from custom_components.vigie.const import CONF_EXCLUDE_STATIONARY
from tests.helpers import BY_ID_PORT, FakePorts
from tests.integration.common import entity_id, make_entry, setup, tick
from tests.tools import scenario
from tests.tools.scenario import Scenario, Target, Track, relative

OWN = Track(43.5, 7.25, 6.0, 0.0)  # TEST §3.4: own boat heading 000° at 6 kn
START = scenario.DEFAULT_START_EPOCH


def at(east_nm: float, north_nm: float, sog: float, cog: float) -> Track:
    lat, lon = relative(OWN.lat, OWN.lon, east_nm, north_nm)
    return Track(lat, lon, sog, cog)


async def play(hass, freezer, fake, lines, step: int = 5) -> dict[int, list[str]]:
    """Feed timed lines window by window, ticking `step` s after each; return states."""
    windows: dict[int, list[str]] = defaultdict(list)
    for t, sentence in lines:
        windows[int((t - START) // step)].append(sentence)
    last = max(windows)
    for w in range(last + 1):
        if windows[w]:
            fake.feed_lines(*windows[w])
        await tick(hass, freezer, step)
    return windows


def state(hass, entry, key, domain="sensor"):
    return hass.states.get(entity_id(hass, entry, key, domain))


@pytest.fixture
async def boat(hass: HomeAssistant, fake_ports: FakePorts):
    entry = make_entry(hass)
    await setup(hass, entry)
    return entry, fake_ports[BY_ID_PORT]


# --- F-TRF-01 ------------------------------------------------------------------------------


async def test_f_trf_01_risk_on_when_tcpa_crosses_15_min_off_after_passage(
    hass: HomeAssistant, boat, freezer: FrozenDateTimeFactory
):
    """U-TRF-05 played over 30 min: on at TCPA < 15 min (≈ 6.6 min), off once passed (≈ 21.6)."""
    entry, fake = boat
    eid = entity_id(hass, entry, "collision_risk", "binary_sensor")
    changes: list[tuple[float, str]] = []
    hass.bus.async_listen(
        "state_changed",
        lambda e: (
            changes.append((e.time_fired.timestamp(), e.data["new_state"].state))
            if e.data["entity_id"] == eid
            else None
        ),
    )
    v_east, v_north = -6.0, 1.0  # absolute target velocity: relative (−6, −5) kn
    target = Target(
        235000005,
        at(2, 2, math.hypot(v_east, v_north), math.degrees(math.atan2(v_east, v_north)) % 360),
    )
    start = dt_util.utcnow().timestamp()
    await play(hass, freezer, fake, scenario.generate(Scenario(OWN, (target,), 30 * 60)))
    transitions = [(t, s) for t, s in changes if s in (STATE_ON, STATE_OFF)]
    states = [s for _, s in transitions]
    assert states.count(STATE_ON) == 1, transitions  # one risk episode
    on_at = next(t for t, s in transitions if s == STATE_ON) - start
    off_at = next(t for t, s in transitions if s == STATE_OFF and t - start > on_at) - start
    assert 6 * 60 <= on_at <= 7.5 * 60, on_at
    assert 21 * 60 <= off_at <= 23 * 60, off_at


# --- F-TRF-02 ------------------------------------------------------------------------------


async def test_f_trf_02_head_on_closest_threat(hass: HomeAssistant, boat, freezer):
    entry, fake = boat
    hass.config.units = METRIC_SYSTEM  # NM must stay NM (suggested unit)
    await play(hass, freezer, fake, scenario.generate(scenario.PRESETS["head-on"])[:3], step=1)
    cpa = state(hass, entry, "closest_threat_cpa")
    tcpa = state(hass, entry, "closest_threat_tcpa")
    assert float(cpa.state) == pytest.approx(0.0, abs=0.01)
    assert cpa.attributes["unit_of_measurement"] == UnitOfLength.NAUTICAL_MILES
    assert cpa.attributes["mmsi"] == 235000001
    assert float(tcpa.state) == pytest.approx(10.0, abs=0.1)
    assert tcpa.attributes["unit_of_measurement"] == "min"
    assert state(hass, entry, "collision_risk", "binary_sensor").state == STATE_ON
    closest = state(hass, entry, "closest_target_distance")
    assert float(closest.state) == pytest.approx(2.0, abs=0.01)
    assert closest.attributes["unit_of_measurement"] == UnitOfLength.NAUTICAL_MILES
    assert closest.attributes["mmsi"] == 235000001
    target = state(hass, entry, "ais_targets").attributes["targets"][0]
    assert target["cpa_nm"] == pytest.approx(0.0, abs=0.01)
    assert target["tcpa_min"] == pytest.approx(10.0, abs=0.1)


async def test_entity_model(hass: HomeAssistant, boat):
    entry, _ = boat
    reg = er.async_get(hass)
    risk = reg.async_get(entity_id(hass, entry, "collision_risk", "binary_sensor"))
    assert risk.original_device_class == "safety"
    for key, device_class in (
        ("closest_target_distance", "distance"),
        ("closest_threat_cpa", "distance"),
        ("closest_threat_tcpa", "duration"),
    ):
        ent = reg.async_get(entity_id(hass, entry, key))
        assert ent.original_device_class == device_class, key
        assert ent.translation_key == key
    capabilities = reg.async_get(entity_id(hass, entry, "closest_target_distance")).capabilities
    assert capabilities == {"state_class": "measurement"}
    assert not reg.async_get(entity_id(hass, entry, "closest_threat_cpa")).capabilities


# --- No threat / no own position ---------------------------------------------------------------


async def test_no_threat_threat_sensors_unavailable(hass: HomeAssistant, boat, freezer):
    entry, fake = boat
    clear = Target(235000002, at(1, 0, 6, 270))  # U-TRF-02: passes clear
    await play(hass, freezer, fake, scenario.generate(Scenario(OWN, (clear,), 2)), step=1)
    assert state(hass, entry, "collision_risk", "binary_sensor").state == STATE_OFF
    assert state(hass, entry, "closest_threat_cpa").state == STATE_UNAVAILABLE
    assert state(hass, entry, "closest_threat_tcpa").state == STATE_UNAVAILABLE
    assert float(state(hass, entry, "closest_target_distance").state) == pytest.approx(
        1.0, abs=0.02
    )


async def test_own_position_lost_traffic_entities_unavailable(hass: HomeAssistant, boat, freezer):
    entry, fake = boat
    await play(hass, freezer, fake, scenario.generate(scenario.PRESETS["head-on"])[:3], step=1)
    assert state(hass, entry, "collision_risk", "binary_sensor").state == STATE_ON
    await tick(hass, freezer, 11)  # no RMC for longer than the staleness timeout
    for key, domain in (
        ("collision_risk", "binary_sensor"),
        ("closest_target_distance", "sensor"),
        ("closest_threat_cpa", "sensor"),
        ("closest_threat_tcpa", "sensor"),
    ):
        assert state(hass, entry, key, domain).state == STATE_UNAVAILABLE, key  # never "off"
    assert state(hass, entry, "ais_targets").state == "1"


# --- F-TRF-03 ------------------------------------------------------------------------------


async def test_f_trf_03_sixty_targets_list_capped(hass: HomeAssistant, boat, freezer):
    entry, fake = boat
    targets = tuple(
        Target(235100000 + i, at(5 * math.cos(i / 10), 5 * math.sin(i / 10) + i / 60, 5.0, i * 6.0))
        for i in range(60)
    )
    await play(hass, freezer, fake, scenario.generate(Scenario(OWN, targets, 0)), step=1)
    st = state(hass, entry, "ais_targets")
    assert st.state == "60"
    listed = st.attributes["targets"]
    assert len(listed) == 50
    assert [t["distance_nm"] for t in listed] == sorted(t["distance_nm"] for t in listed)
    assert all("cpa_nm" in t and "tcpa_min" in t for t in listed)


# --- F-TRF-04 ------------------------------------------------------------------------------


async def test_f_trf_04_silent_targets_expire_by_class(hass: HomeAssistant, boat, freezer):
    entry, fake = boat
    targets = (Target(235000010, at(1, 1, 5, 90)), Target(367000010, at(-1, 1, 5, 90), "B"))
    await play(hass, freezer, fake, scenario.generate(Scenario(OWN, targets, 0)), step=1)
    assert state(hass, entry, "ais_targets").state == "2"
    await tick(hass, freezer, 600)  # 10 min + 1 s since the reports
    assert state(hass, entry, "ais_targets").state == "1"  # Class A gone
    await tick(hass, freezer, 300)
    assert state(hass, entry, "ais_targets").state == "0"  # Class B gone after 15 min


# --- F-TRF-06 ------------------------------------------------------------------------------


async def test_f_trf_06_automation_runs_once_per_episode(hass: HomeAssistant, boat, freezer):
    entry, fake = boat
    eid = entity_id(hass, entry, "collision_risk", "binary_sensor")
    calls = async_mock_service(hass, "test", "automation")
    assert await async_setup_component(
        hass,
        "automation",
        {
            "automation": {
                "trigger": {"platform": "state", "entity_id": eid, "to": "on"},
                "action": {"service": "test.automation"},
            }
        },
    )
    # A target 2 NM ahead on a reciprocal course whose reports alternate between passing
    # 0.3 NM and 0.6 NM abeam: CPA hovers around the 0.5 NM threshold every 10 s.
    lines = []
    for k in range(0, 13):  # 2 min of reports
        t = k * 10
        east = 0.3 if k % 2 == 0 else 0.6
        track = at(east, 2 - 6.0 * t / 3600, 6.0, 180.0)  # 12 kn closing with own boat
        lines.append((START + t + 0.001, scenario.vdm(Target(235000006, track), 0)))
    lines += [(START + s, scenario.rmc(START + s, *OWN.at(s), 6.0, 0.0)) for s in range(0, 121)]
    lines.sort()
    await play(hass, freezer, fake, lines, step=5)
    assert len(calls) == 1  # one episode, no flapping
    assert hass.states.get(eid).state == STATE_ON


# --- F-TRF-07 ------------------------------------------------------------------------------


async def test_f_trf_07_anchored_target_exclusion_follows_option(
    hass: HomeAssistant, boat, freezer
):
    entry, fake = boat
    anchored = Target(235000008, at(0, 0.4, 0.0, 0.0), nav_status=1)  # U-TRF-08: at anchor
    lines = scenario.generate(Scenario(OWN, (anchored,), 2))
    await play(hass, freezer, fake, lines, step=1)
    assert state(hass, entry, "collision_risk", "binary_sensor").state == STATE_OFF

    result = await hass.config_entries.options.async_init(entry.entry_id)
    await hass.config_entries.options.async_configure(
        result["flow_id"], {**result["data_schema"]({}), CONF_EXCLUDE_STATIONARY: False}
    )
    await hass.async_block_till_done()
    fake.feed_lines(*(s for _, s in lines))
    await tick(hass, freezer, 1)
    assert state(hass, entry, "collision_risk", "binary_sensor").state == STATE_ON
