"""Setup, unload, reload — F-LIFE-04, 05, 06 (TEST §4.1, SPEC §6, §10.3, NFR-06, NFR-07).

The harness fails any test that leaves tasks or timers behind, which is what F-LIFE-05
relies on for "no pending tasks".
"""

from datetime import timedelta

from freezegun.api import FrozenDateTimeFactory
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import CONF_NAME
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry, async_fire_time_changed

from custom_components.vigie.const import (
    CONF_BAUDRATE,
    CONF_INCLUDE_OWN_VDO,
    CONF_SERIAL_PORT,
    CONF_STALE_TIMEOUT,
    CONF_UPDATE_INTERVAL,
    DOMAIN,
)
from custom_components.vigie.state import POSITION, SOG, Source
from tests.helpers import BY_ID_PORT, FakePorts, nmea

RMC = nmea("GPRMC,081502,A,4330.000,N,00715.500,E,5.2,271.0,270926,,")
AIS_TYPE1 = "!AIVDM,1,1,,B,177KQJ5000G?tO`K>RA1wUbN0TKH,0*5C"  # gpsd reference sample


def _entry(hass: HomeAssistant, port: str = BY_ID_PORT, **options) -> MockConfigEntry:
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Garnet",
        unique_id=port,
        data={CONF_NAME: "Garnet", CONF_SERIAL_PORT: port, CONF_BAUDRATE: 38400},
        options=options,
    )
    entry.add_to_hass(hass)
    return entry


async def _setup(hass: HomeAssistant, entry: MockConfigEntry) -> None:
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()


# --- Data path --------------------------------------------------------------


async def test_setup_reads_port_into_coordinator(hass: HomeAssistant, fake_ports: FakePorts):
    entry = _entry(hass)
    await _setup(hass, entry)
    assert entry.state is ConfigEntryState.LOADED
    coordinator = entry.runtime_data
    assert coordinator.connected
    fake_ports[BY_ID_PORT].feed_lines(RMC, AIS_TYPE1)
    await hass.async_block_till_done()
    assert coordinator.own.get(POSITION).value == (43.5, 7.0 + 15.5 / 60)
    assert coordinator.own.get(SOG).source is Source.GPS
    assert 477553000 in coordinator.targets
    assert coordinator.hub.stats.gps_ok == 1


async def test_listeners_notified_on_tick_and_connection_change(
    hass: HomeAssistant, fake_ports: FakePorts, freezer: FrozenDateTimeFactory
):
    entry = _entry(hass, **{CONF_UPDATE_INTERVAL: 2})
    await _setup(hass, entry)
    coordinator = entry.runtime_data
    calls: list[bool] = []
    unsub = coordinator.async_add_listener(lambda: calls.append(coordinator.connected))

    freezer.tick(timedelta(seconds=2))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert calls == [True]  # one tick per update_interval

    fake_ports[BY_ID_PORT].available = False
    fake_ports[BY_ID_PORT].disconnect()
    await hass.async_block_till_done()
    assert calls == [True, False]  # pushed at once, not on the next tick

    unsub()
    freezer.tick(timedelta(seconds=2))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert calls == [True, False]


async def test_vdo_routed_to_own_state_not_targets(hass: HomeAssistant, fake_ports: FakePorts):
    entry = _entry(hass)
    await _setup(hass, entry)
    vdo = nmea("AIVDO,1,1,,B,177KQJ5000G?tO`K>RA1wUbN0TKH,0", "!")
    fake_ports[BY_ID_PORT].feed_lines(vdo)
    await hass.async_block_till_done()
    coordinator = entry.runtime_data
    assert len(coordinator.targets) == 0
    assert coordinator.own.own_mmsi == 477553000
    assert coordinator.own.position_source is Source.VDO


# --- F-LIFE-04 --------------------------------------------------------------


async def test_f_life_04_port_missing_setup_retried(hass: HomeAssistant, fake_ports: FakePorts):
    fake_ports[BY_ID_PORT].available = False
    entry = _entry(hass)
    assert not await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.SETUP_RETRY

    fake_ports[BY_ID_PORT].available = True  # receiver plugged in: the retry succeeds
    await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.LOADED


# --- F-LIFE-05 --------------------------------------------------------------


async def test_f_life_05_unload_cancels_reader_and_closes_port(
    hass: HomeAssistant, fake_ports: FakePorts
):
    entry = _entry(hass)
    await _setup(hass, entry)
    coordinator = entry.runtime_data
    reader_task = coordinator.reader_task
    assert reader_task is not None and not reader_task.done()

    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.NOT_LOADED
    assert reader_task.done()
    assert fake_ports[BY_ID_PORT].writers[-1].closed
    assert not coordinator.connected


async def test_f_life_05_unload_during_outage(hass: HomeAssistant, fake_ports: FakePorts):
    entry = _entry(hass)
    await _setup(hass, entry)
    fake_ports[BY_ID_PORT].available = False
    fake_ports[BY_ID_PORT].disconnect()  # reader now waiting in backoff
    await hass.async_block_till_done()
    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.NOT_LOADED


# --- F-LIFE-06 --------------------------------------------------------------


async def test_f_life_06_reload_after_options_change(hass: HomeAssistant, fake_ports: FakePorts):
    entry = _entry(hass)
    await _setup(hass, entry)
    first = entry.runtime_data
    assert first.update_interval_s == 1
    assert first.own.stale_timeout_s == 10

    hass.config_entries.async_update_entry(
        entry,
        options={CONF_UPDATE_INTERVAL: 3, CONF_STALE_TIMEOUT: 20, CONF_INCLUDE_OWN_VDO: False},
    )
    await hass.async_block_till_done()
    # Options changed outside the options flow are applied on the next reload
    await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    second = entry.runtime_data
    assert second is not first
    assert first.reader_task.done()
    assert (second.update_interval_s, second.own.stale_timeout_s) == (3, 20)
    assert second.own.use_vdo is False
    assert entry.unique_id == BY_ID_PORT
    assert len(fake_ports[BY_ID_PORT].writers) == 2
    assert fake_ports[BY_ID_PORT].writers[0].closed
    assert not fake_ports[BY_ID_PORT].writers[1].closed


async def test_two_entries_on_two_ports(hass: HomeAssistant, fake_ports: FakePorts):
    first, second = _entry(hass), _entry(hass, port="/dev/ttyUSB1")
    await _setup(hass, first)  # sets up every entry of the domain
    assert second.state is ConfigEntryState.LOADED
    fake_ports["/dev/ttyUSB1"].feed_lines(RMC)
    await hass.async_block_till_done()
    assert second.runtime_data.own.get(POSITION) is not None
    assert first.runtime_data.own.get(POSITION) is None
