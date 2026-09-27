"""Diagnostics download — F-LIFE-08 (TEST §4.1, SPEC §9.5)."""

from freezegun.api import FrozenDateTimeFactory
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.components.diagnostics import (
    get_diagnostics_for_config_entry,
)
from pytest_homeassistant_custom_component.typing import ClientSessionGenerator

from custom_components.vigie.const import CONF_OWN_MMSI
from tests.helpers import BY_ID_PORT, FakePorts, nmea
from tests.integration.common import make_entry, setup, tick

RMC = nmea("GPRMC,081502,A,4330.000,N,00715.500,E,5.2,271.0,270926,,")
AIS_TYPE1 = "!AIVDM,1,1,,B,177KQJ5000G?tO`K>RA1wUbN0TKH,0*5C"


async def test_f_life_08_diagnostics_redacted_with_counters(
    hass: HomeAssistant,
    hass_client: ClientSessionGenerator,
    fake_ports: FakePorts,
    freezer: FrozenDateTimeFactory,
):
    entry = make_entry(hass, **{CONF_OWN_MMSI: 227000001})
    await setup(hass, entry)
    fake_ports[BY_ID_PORT].feed_lines(RMC, AIS_TYPE1, RMC[:-2] + "00")
    await tick(hass, freezer)

    diag = await get_diagnostics_for_config_entry(hass, hass_client, entry)

    assert diag["entry"]["data"]["serial_port"] == "**REDACTED**"
    assert diag["entry"]["data"]["baudrate"] == 38400
    assert diag["entry"]["options"][CONF_OWN_MMSI] == "**REDACTED**"
    assert diag["connected"] is True
    stats = diag["stats"]
    assert stats["gps_ok"] == 1 and stats["ais_ok"] == 1 and stats["checksum_errors"] == 1
    assert stats["sentences_per_min"] == 2
    own = diag["own_state"]
    assert own["position"]["value"] == "**REDACTED**"
    assert own["sog"] == {"value": 5.2, "source": "gps", "sentence": "RMC", "age_s": 1.0}
    assert diag["targets"]["count"] == 1
    assert BY_ID_PORT not in str(diag)
    assert "227000001" not in str(diag)
