"""Watch-list trackers — F-TRF-05 (TEST §4.4, SPEC §9.3, §11.2)."""

import pytest
from freezegun.api import FrozenDateTimeFactory
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import STATE_UNAVAILABLE
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er

from custom_components.vigie.const import CONF_WATCH_LIST, DOMAIN
from tests.helpers import BY_ID_PORT, FakePorts
from tests.integration.common import make_entry, setup, tick
from tests.tools import scenario
from tests.tools.scenario import Target, Track, relative

WATCHED_A = 235000101  # synthetic MMSIs
WATCHED_B = 367000102
OTHER = 235000199
OWN = Track(43.5, 7.25, 6.0, 0.0)


def _report(mmsi: int, east: float, north: float, ais_class: str = "A") -> str:
    lat, lon = relative(OWN.lat, OWN.lon, east, north)
    return scenario.vdm(Target(mmsi, Track(lat, lon, 5.0, 90.0), ais_class), 0)


def _own() -> str:
    return scenario.rmc(scenario.DEFAULT_START_EPOCH, OWN.lat, OWN.lon, 6.0, 0.0)


async def _set_watch_list(hass: HomeAssistant, entry: ConfigEntry, mmsis: list[str]):
    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {**result["data_schema"]({}), CONF_WATCH_LIST: mmsis}
    )
    await hass.async_block_till_done()
    return result


def _watched_trackers(hass: HomeAssistant, entry: ConfigEntry) -> dict[str, str]:
    """unique_id → entity_id of the watch-list trackers of this entry."""
    return {
        e.unique_id: e.entity_id
        for e in er.async_entries_for_config_entry(er.async_get(hass), entry.entry_id)
        if e.domain == "device_tracker" and "_ais_" in e.unique_id
    }


@pytest.fixture
async def boat(hass: HomeAssistant, fake_ports: FakePorts):
    entry = make_entry(hass)
    await setup(hass, entry)
    return entry, fake_ports


async def test_f_trf_05_two_mmsis_two_trackers_removal_removes_them(
    hass: HomeAssistant, boat, freezer: FrozenDateTimeFactory
):
    entry, ports = boat
    assert _watched_trackers(hass, entry) == {}  # never auto-created

    result = await _set_watch_list(hass, entry, [str(WATCHED_A), f" {WATCHED_B} "])
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert entry.options[CONF_WATCH_LIST] == [WATCHED_A, WATCHED_B]
    trackers = _watched_trackers(hass, entry)
    assert trackers == {
        f"{entry.entry_id}_ais_{WATCHED_A}": f"device_tracker.ais_{WATCHED_A}",
        f"{entry.entry_id}_ais_{WATCHED_B}": f"device_tracker.ais_{WATCHED_B}",
    }

    # Each on its own device, linked to the boat's device
    devices = dr.async_get(hass)
    boat_device = devices.async_get_device({(DOMAIN, entry.entry_id)})
    for mmsi in (WATCHED_A, WATCHED_B):
        device = devices.async_get_device({(DOMAIN, f"{entry.entry_id}_{mmsi}")})
        assert device is not None and device.via_device_id == boat_device.id
        assert device.name == f"AIS {mmsi}"

    # Traffic for a watched and an unwatched target: only the watched one is tracked
    ports[BY_ID_PORT].feed_lines(_own(), _report(WATCHED_A, 1, 1), _report(OTHER, 2, 2))
    await tick(hass, freezer)
    st = hass.states.get(f"device_tracker.ais_{WATCHED_A}")
    lat, lon = relative(OWN.lat, OWN.lon, 1, 1)
    assert st.attributes["latitude"] == pytest.approx(lat, abs=1e-4)
    assert st.attributes["longitude"] == pytest.approx(lon, abs=1e-4)
    assert st.attributes["source_type"] == "gps"
    assert st.attributes["mmsi"] == WATCHED_A
    assert st.attributes["class"] == "A"
    assert st.attributes["sog"] == pytest.approx(5.0)
    assert st.attributes["distance_nm"] == pytest.approx(2**0.5, abs=0.02)
    assert "cpa_nm" in st.attributes and "tcpa_min" in st.attributes
    assert hass.states.get(f"device_tracker.ais_{WATCHED_B}").state == STATE_UNAVAILABLE
    assert f"device_tracker.ais_{OTHER}" not in {s.entity_id for s in hass.states.async_all()}

    # Remove one MMSI: its entity and device go away on reload
    await _set_watch_list(hass, entry, [str(WATCHED_A)])
    assert list(_watched_trackers(hass, entry).values()) == [f"device_tracker.ais_{WATCHED_A}"]
    assert devices.async_get_device({(DOMAIN, f"{entry.entry_id}_{WATCHED_B}")}) is None
    assert hass.states.get(f"device_tracker.ais_{WATCHED_B}") is None

    # Empty list: none left
    await _set_watch_list(hass, entry, [])
    assert _watched_trackers(hass, entry) == {}


async def test_watched_target_unavailable_after_expiry(
    hass: HomeAssistant, boat, freezer: FrozenDateTimeFactory
):
    entry, ports = boat
    await _set_watch_list(hass, entry, [str(WATCHED_B)])
    ports[BY_ID_PORT].feed_lines(_own(), _report(WATCHED_B, -1, 1, "B"))
    await tick(hass, freezer)
    eid = f"device_tracker.ais_{WATCHED_B}"
    assert hass.states.get(eid).state != STATE_UNAVAILABLE
    await tick(hass, freezer, 900)  # Class B expiry: 15 min
    assert hass.states.get(eid).state == STATE_UNAVAILABLE  # never a frozen position


async def test_watched_target_available_without_own_position(
    hass: HomeAssistant, boat, freezer: FrozenDateTimeFactory
):
    entry, ports = boat
    await _set_watch_list(hass, entry, [str(WATCHED_A)])
    ports[BY_ID_PORT].feed_lines(_report(WATCHED_A, 1, 1))  # no own RMC
    await tick(hass, freezer)
    st = hass.states.get(f"device_tracker.ais_{WATCHED_A}")
    assert st.state != STATE_UNAVAILABLE  # its position does not depend on ours
    assert st.attributes["distance_nm"] is None


@pytest.mark.parametrize("bad", ["12345", "23500010x", "2350001011"])
async def test_watch_list_rejects_invalid_mmsi(hass: HomeAssistant, boat, bad):
    entry, _ = boat
    result = await _set_watch_list(hass, entry, [str(WATCHED_A), bad])
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {CONF_WATCH_LIST: "invalid_watch_list"}
    assert CONF_WATCH_LIST not in entry.options
