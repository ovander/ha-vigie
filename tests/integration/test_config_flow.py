"""Config and options flows — F-LIFE-01, 02, 03, 07 (TEST §4.1, SPEC §11)."""

from homeassistant.config_entries import SOURCE_USER
from homeassistant.const import CONF_NAME
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.vigie.const import (
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
}


async def test_f_life_07_every_option_round_trips(hass: HomeAssistant, fake_ports: FakePorts):
    entry = await _setup_entry(hass)
    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "init"
    result = await hass.config_entries.options.async_configure(result["flow_id"], OPTIONS)
    assert result["type"] is FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()
    assert entry.options == {**OPTIONS, CONF_OWN_MMSI: 227000001}

    # Applied: the entry was reloaded with a coordinator built from the new options
    coordinator = entry.runtime_data
    assert coordinator.update_interval_s == 2
    assert coordinator.own.stale_timeout_s == 30
    assert coordinator.targets.expiry_s == (12 * 60, 20 * 60)
    assert coordinator.own.use_vdo is False
    assert coordinator.own.own_mmsi == 227000001
    settings = coordinator.threat_settings
    assert (settings.cpa_nm, settings.tcpa_min, settings.exclude_stationary) == (0.3, 20, False)

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
