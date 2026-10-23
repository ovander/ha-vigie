"""Config, reconfigure and options flows — F-LIFE-01, 02, 03, 07, 09…12 (TEST §4.1, SPEC §11)."""

from homeassistant.config_entries import SOURCE_USER
from homeassistant.const import CONF_NAME
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.vigie.const import (
    CONF_ANCHOR_CONFIRM,
    CONF_ANCHOR_POSITION_TIMEOUT,
    CONF_BAUDRATE,
    CONF_CPA_THRESHOLD,
    CONF_EXCLUDE_STATIONARY,
    CONF_EXPIRY_CLASS_A,
    CONF_EXPIRY_CLASS_B,
    CONF_INCLUDE_OWN_VDO,
    CONF_OWN_MMSI,
    CONF_SERIAL_PORT,
    CONF_STALE_TIMEOUT,
    CONF_TCPA_THRESHOLD,
    CONF_UPDATE_INTERVAL,
    CONF_WATCH_LIST,
    DOMAIN,
)
from tests.helpers import BY_ID_PORT, FakePorts, nmea

RMC = nmea("GPRMC,081502,A,4330.000,N,00715.500,E,5.2,271.0,270926,,")


async def _start(hass: HomeAssistant):
    return await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})


def _user_input(port: str = BY_ID_PORT, baud: str = "38400", name: str = "Garnet") -> dict:
    return {CONF_NAME: name, CONF_SERIAL_PORT: port, CONF_BAUDRATE: baud}


# --- F-LIFE-01 --------------------------------------------------------------


async def test_f_life_01_ports_listed_and_entry_created(hass: HomeAssistant, fake_ports: FakePorts):
    fake_ports[BY_ID_PORT].initial_data = (RMC + "\r\n").encode()
    result = await _start(hass)
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"
    schema = result["data_schema"].schema
    port_key = next(k for k in schema if k == CONF_SERIAL_PORT)
    assert port_key.default() == BY_ID_PORT
    assert schema[port_key].config["options"] == [BY_ID_PORT]
    assert schema[port_key].config["custom_value"] is True

    result = await hass.config_entries.flow.async_configure(result["flow_id"], _user_input())
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Garnet"
    assert result["data"] == {
        CONF_NAME: "Garnet",
        CONF_SERIAL_PORT: BY_ID_PORT,
        CONF_BAUDRATE: 38400,
    }
    assert result["result"].unique_id == BY_ID_PORT
    assert fake_ports[BY_ID_PORT].baudrates[0] == 38400
    assert fake_ports[BY_ID_PORT].writers[0].closed  # probe released the port


async def test_f_life_01_manual_port_and_custom_baud(hass: HomeAssistant, fake_ports: FakePorts):
    fake_ports["/dev/ttyAMA0"].initial_data = (RMC + "\r\n").encode()
    result = await _start(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], _user_input(port="/dev/ttyAMA0", baud="9600")
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_BAUDRATE] == 9600
    # Probe, then the entry setup: both at the custom rate
    assert set(fake_ports["/dev/ttyAMA0"].baudrates) == {9600}


async def test_f_life_01_invalid_baudrate(hass: HomeAssistant, fake_ports: FakePorts):
    result = await _start(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], _user_input(baud="fast")
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {CONF_BAUDRATE: "invalid_baudrate"}


async def test_f_life_01_port_cannot_be_opened(hass: HomeAssistant, fake_ports: FakePorts):
    fake_ports[BY_ID_PORT].available = False
    result = await _start(hass)
    result = await hass.config_entries.flow.async_configure(result["flow_id"], _user_input())
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "cannot_connect"}


async def test_f_life_01_same_port_twice_aborted(hass: HomeAssistant, fake_ports: FakePorts):
    MockConfigEntry(domain=DOMAIN, unique_id=BY_ID_PORT, data=_user_input()).add_to_hass(hass)
    result = await _start(hass)
    result = await hass.config_entries.flow.async_configure(result["flow_id"], _user_input())
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


# --- F-LIFE-02 --------------------------------------------------------------


async def test_f_life_02_no_data_user_can_proceed(hass: HomeAssistant, fake_ports: FakePorts):
    fake_ports[BY_ID_PORT].eof_on_open = True  # port opens, nothing arrives
    result = await _start(hass)
    result = await hass.config_entries.flow.async_configure(result["flow_id"], _user_input())
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "no_data"
    assert result["errors"] == {"base": "no_data"}
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_SERIAL_PORT] == BY_ID_PORT


# --- F-LIFE-03 --------------------------------------------------------------


async def test_f_life_03_garbage_suggests_other_baud(hass: HomeAssistant, fake_ports: FakePorts):
    fake_ports[BY_ID_PORT].initial_data = b"\xf8\x80x\xe0\xfc\r\n\x00\x1f\xc3\r\n" * 5
    fake_ports[BY_ID_PORT].eof_on_open = True
    result = await _start(hass)
    result = await hass.config_entries.flow.async_configure(result["flow_id"], _user_input())
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"
    assert result["errors"] == {"base": "wrong_baud"}
    assert result["description_placeholders"]["other_baudrate"] == "4800"

    # Following the hint fixes it
    fake_ports[BY_ID_PORT].initial_data = (RMC + "\r\n").encode()
    fake_ports[BY_ID_PORT].eof_on_open = False
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], _user_input(baud="4800")
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_BAUDRATE] == 4800


# --- F-LIFE-07 --------------------------------------------------------------


async def _setup_entry(hass: HomeAssistant) -> MockConfigEntry:
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Garnet",
        unique_id=BY_ID_PORT,
        data={CONF_NAME: "Garnet", CONF_SERIAL_PORT: BY_ID_PORT, CONF_BAUDRATE: 38400},
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


OPTIONS = {
    CONF_UPDATE_INTERVAL: 2,
    CONF_STALE_TIMEOUT: 30,
    CONF_EXPIRY_CLASS_A: 12,
    CONF_EXPIRY_CLASS_B: 20,
    CONF_INCLUDE_OWN_VDO: False,
    CONF_OWN_MMSI: "227000001",
    CONF_CPA_THRESHOLD: 0.3,
    CONF_TCPA_THRESHOLD: 20,
    CONF_EXCLUDE_STATIONARY: False,
    CONF_WATCH_LIST: ["235000101", "235000101"],  # duplicate dropped
    CONF_ANCHOR_CONFIRM: 30,
    CONF_ANCHOR_POSITION_TIMEOUT: 90,
}


async def test_f_life_07_every_option_round_trips(hass: HomeAssistant, fake_ports: FakePorts):
    entry = await _setup_entry(hass)
    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "init"
    result = await hass.config_entries.options.async_configure(result["flow_id"], OPTIONS)
    assert result["type"] is FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()
    assert entry.options == {**OPTIONS, CONF_OWN_MMSI: 227000001, CONF_WATCH_LIST: [235000101]}

    # Applied: the entry was reloaded with a coordinator built from the new options
    coordinator = entry.runtime_data
    assert coordinator.update_interval_s == 2
    assert coordinator.own.stale_timeout_s == 30
    assert coordinator.targets.expiry_s == (12 * 60, 20 * 60)
    assert coordinator.own.use_vdo is False
    assert coordinator.own.own_mmsi == 227000001
    assert coordinator.watch_list == (235000101,)
    settings = coordinator.threat_settings
    assert (settings.cpa_nm, settings.tcpa_min, settings.exclude_stationary) == (0.3, 20, False)
    assert (coordinator.anchor.confirm_s, coordinator.anchor.position_timeout_s) == (30, 90)

    # The form shows the stored values next time; clearing the MMSI removes it
    result = await hass.config_entries.options.async_init(entry.entry_id)
    schema = result["data_schema"].schema
    mmsi_key = next(k for k in schema if k == CONF_OWN_MMSI)
    assert mmsi_key.description == {"suggested_value": "227000001"}
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {k: v for k, v in OPTIONS.items() if k != CONF_OWN_MMSI}
    )
    await hass.async_block_till_done()
    assert CONF_OWN_MMSI not in entry.options
    assert entry.runtime_data.own.own_mmsi is None


async def test_f_life_07_invalid_mmsi_rejected(hass: HomeAssistant, fake_ports: FakePorts):
    entry = await _setup_entry(hass)
    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {**OPTIONS, CONF_OWN_MMSI: "12345"}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {CONF_OWN_MMSI: "invalid_mmsi"}
    assert entry.options == {}


# --- F-LIFE-09…12: Reconfigure the port and baud rate (WP32, #98) ------------

NEW_PORT = "socket://192.168.1.20:10110"


async def _configured(hass: HomeAssistant, fake_ports: FakePorts) -> MockConfigEntry:
    """A running entry on BY_ID_PORT at 38 400 baud."""
    fake_ports[BY_ID_PORT].initial_data = (RMC + "\r\n").encode()
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Garnet",
        unique_id=BY_ID_PORT,
        data={CONF_NAME: "Garnet", CONF_SERIAL_PORT: BY_ID_PORT, CONF_BAUDRATE: 38400},
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


def _reconfigure_input(port: str = NEW_PORT, baud: str = "38400") -> dict:
    return {CONF_SERIAL_PORT: port, CONF_BAUDRATE: baud}


async def test_f_life_09_reconfigure_moves_to_a_new_port(
    hass: HomeAssistant, fake_ports: FakePorts
):
    entry = await _configured(hass, fake_ports)
    registry = er.async_get(hass)
    before = {
        e.entity_id: e.unique_id
        for e in er.async_entries_for_config_entry(registry, entry.entry_id)
    }
    fake_ports[NEW_PORT].initial_data = (RMC + "\r\n").encode()

    result = await entry.start_reconfigure_flow(hass)
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "reconfigure"
    schema = result["data_schema"].schema
    port_key = next(k for k in schema if k == CONF_SERIAL_PORT)
    assert port_key.default() == BY_ID_PORT  # the current port, ready to change
    assert BY_ID_PORT in schema[port_key].config["options"]

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], _reconfigure_input(baud="4800")
    )
    await hass.async_block_till_done()
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"
    assert entry.data == {CONF_NAME: "Garnet", CONF_SERIAL_PORT: NEW_PORT, CONF_BAUDRATE: 4800}
    assert entry.unique_id == NEW_PORT
    assert entry.title == "Garnet"
    # Reloaded on the new port; the same entities, unique IDs and entry
    assert fake_ports[NEW_PORT].baudrates == [4800, 4800]  # the probe, then the reader
    assert fake_ports[BY_ID_PORT].writers[-1].closed
    after = {
        e.entity_id: e.unique_id
        for e in er.async_entries_for_config_entry(registry, entry.entry_id)
    }
    assert after == before


async def test_f_life_10_reconfigure_probe_errors(hass: HomeAssistant, fake_ports: FakePorts):
    entry = await _configured(hass, fake_ports)
    result = await entry.start_reconfigure_flow(hass)

    fake_ports[NEW_PORT].available = False
    result = await hass.config_entries.flow.async_configure(result["flow_id"], _reconfigure_input())
    assert result["step_id"] == "reconfigure"
    assert result["errors"] == {"base": "cannot_connect"}

    fake_ports[NEW_PORT].available = True
    fake_ports[NEW_PORT].initial_data = b"\xf8\x80x\xe0\xfc\r\n\x00\x1f\xc3\r\n" * 5
    fake_ports[NEW_PORT].eof_on_open = True
    result = await hass.config_entries.flow.async_configure(result["flow_id"], _reconfigure_input())
    assert result["errors"] == {"base": "wrong_baud"}
    assert result["description_placeholders"]["other_baudrate"] == "4800"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], _reconfigure_input(baud="nope")
    )
    assert result["errors"] == {CONF_BAUDRATE: "invalid_baudrate"}
    assert entry.data[CONF_SERIAL_PORT] == BY_ID_PORT  # nothing changed


async def test_f_life_11_reconfigure_no_data_saves_anyway(
    hass: HomeAssistant, fake_ports: FakePorts
):
    entry = await _configured(hass, fake_ports)
    fake_ports[NEW_PORT].eof_on_open = True
    result = await entry.start_reconfigure_flow(hass)
    result = await hass.config_entries.flow.async_configure(result["flow_id"], _reconfigure_input())
    assert result["step_id"] == "no_data"
    assert result["errors"] == {"base": "no_data"}
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    await hass.async_block_till_done()
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"
    assert entry.data[CONF_SERIAL_PORT] == NEW_PORT


async def test_f_life_11_same_port_new_baud_skips_the_probe(
    hass: HomeAssistant, fake_ports: FakePorts
):
    """Vigie holds its own port, so it cannot be probed: saved and reloaded directly."""
    entry = await _configured(hass, fake_ports)
    opens = fake_ports[BY_ID_PORT].opens
    result = await entry.start_reconfigure_flow(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], _reconfigure_input(port=BY_ID_PORT, baud="4800")
    )
    await hass.async_block_till_done()
    assert result["reason"] == "reconfigure_successful"
    assert entry.data[CONF_BAUDRATE] == 4800
    assert fake_ports[BY_ID_PORT].opens == opens + 1  # only the reloaded reader
    assert fake_ports[BY_ID_PORT].baudrates[-1] == 4800


async def test_f_life_12_port_of_another_boat_refused(hass: HomeAssistant, fake_ports: FakePorts):
    entry = await _configured(hass, fake_ports)
    MockConfigEntry(
        domain=DOMAIN,
        title="Tender",
        unique_id=NEW_PORT,
        data={CONF_NAME: "Tender", CONF_SERIAL_PORT: NEW_PORT, CONF_BAUDRATE: 38400},
    ).add_to_hass(hass)
    result = await entry.start_reconfigure_flow(hass)
    result = await hass.config_entries.flow.async_configure(result["flow_id"], _reconfigure_input())
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {CONF_SERIAL_PORT: "port_in_use"}
    assert entry.data[CONF_SERIAL_PORT] == BY_ID_PORT
