"""Entities — F-ENT-01…07, entity halves of F-HUB-03 and F-LIFE-06 (TEST §4.1–4.3).

SPEC §9.1, §9.2, §9.5, §10.1, §10.2. Synthetic data only; F-ENT-01 on the real capture
is tracked in issue #2. Time is simulated with the harness's freezer.
"""

import logging

import pytest
from freezegun.api import FrozenDateTimeFactory
from homeassistant.components.sensor import SensorDeviceClass, SensorStateClass
from homeassistant.const import STATE_OFF, STATE_UNAVAILABLE, EntityCategory, UnitOfSpeed
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.util.unit_system import METRIC_SYSTEM, US_CUSTOMARY_SYSTEM

from custom_components.vigie.const import CONF_UPDATE_INTERVAL, DOMAIN
from tests.helpers import BY_ID_PORT, FakePorts, nmea
from tests.integration.common import entity_id, make_entry, setup, tick


def rmc(sog: float = 5.2, cog: float = 271.0, lat: str = "4330.000", lon: str = "00715.500"):
    return nmea(f"GPRMC,081502,A,{lat},N,{lon},E,{sog:.2f},{cog:.1f},270926,,")


GGA = nmea("GPGGA,081502,4330.000,N,00715.500,E,1,08,0.9,5.0,M,48.0,M,,")
AIS_TYPE1 = "!AIVDM,1,1,,B,177KQJ5000G?tO`K>RA1wUbN0TKH,0*5C"  # gpsd reference, MMSI 477553000
AIS_TYPE18 = "!AIVDM,1,1,,A,B5NJ;PP005l4ot5Isbl03wsUkP06,0*76"  # public sample, MMSI 367430530

OWN_BOAT_KEYS = ["sog", "cog", "heading", "fix_quality", "satellites", "hdop"]


@pytest.fixture
async def loaded(hass: HomeAssistant, fake_ports: FakePorts, freezer: FrozenDateTimeFactory):
    """One boat, data flowing: RMC + GGA + two AIS targets, one tick."""
    entry = make_entry(hass)
    await setup(hass, entry)
    fake_ports[BY_ID_PORT].feed_lines(rmc(), GGA, AIS_TYPE1, AIS_TYPE18)
    await tick(hass, freezer)
    return entry


def state(hass: HomeAssistant, entry, key: str, domain: str = "sensor"):
    return hass.states.get(entity_id(hass, entry, key, domain))


# --- F-ENT-01 ---------------------------------------------------------------


@pytest.mark.parametrize(
    "key,device_class,unit,state_class,category,expected",
    [
        (
            "sog",
            SensorDeviceClass.SPEED,
            UnitOfSpeed.KNOTS,
            SensorStateClass.MEASUREMENT,
            None,
            5.2,
        ),
        ("cog", None, "°", SensorStateClass.MEASUREMENT_ANGLE, None, 271.0),
        ("heading", None, "°", SensorStateClass.MEASUREMENT_ANGLE, None, STATE_UNAVAILABLE),
        ("fix_quality", SensorDeviceClass.ENUM, None, None, EntityCategory.DIAGNOSTIC, "gps"),
        ("satellites", None, None, SensorStateClass.MEASUREMENT, EntityCategory.DIAGNOSTIC, 8),
        ("hdop", None, None, SensorStateClass.MEASUREMENT, EntityCategory.DIAGNOSTIC, 0.9),
    ],
)
async def test_f_ent_01_own_boat_sensors(
    hass: HomeAssistant, loaded, key, device_class, unit, state_class, category, expected
):
    entry = loaded
    reg = er.async_get(hass).async_get(entity_id(hass, entry, key))
    assert reg.translation_key == key
    assert reg.original_device_class == device_class
    assert reg.unit_of_measurement == unit
    assert (reg.capabilities or {}).get("state_class") == state_class
    assert reg.entity_category == category
    st = state(hass, entry, key)
    if isinstance(expected, float | int) and not isinstance(expected, bool):
        assert float(st.state) == pytest.approx(expected)
    else:
        assert st.state == expected


async def test_f_ent_01_translated_names(hass: HomeAssistant, loaded):
    assert state(hass, loaded, "sog").attributes["friendly_name"] == "Garnet Speed over ground"
    assert entity_id(hass, loaded, "cog") == "sensor.garnet_course_over_ground"
    assert state(hass, loaded, "connected", "binary_sensor").attributes["friendly_name"] == (
        "Garnet Connected"
    )


async def test_f_ent_01_fix_quality_options(hass: HomeAssistant, loaded):
    st = state(hass, loaded, "fix_quality")
    assert "gps" in st.attributes["options"] and "no_fix" in st.attributes["options"]


async def test_f_ent_01_one_device_per_boat(hass: HomeAssistant, loaded):
    ents = er.async_entries_for_config_entry(er.async_get(hass), loaded.entry_id)
    assert {e.device_id for e in ents} and len({e.device_id for e in ents}) == 1


# --- F-ENT-02 ---------------------------------------------------------------


async def test_f_ent_02_display_unit_converted(hass: HomeAssistant, loaded):
    eid = entity_id(hass, loaded, "sog")
    er.async_get(hass).async_update_entity_options(eid, "sensor", {"unit_of_measurement": "km/h"})
    await hass.async_block_till_done()
    st = hass.states.get(eid)
    assert st.attributes["unit_of_measurement"] == "km/h"
    assert float(st.state) == pytest.approx(5.2 * 1.852, abs=0.01)


@pytest.mark.parametrize("units", [METRIC_SYSTEM, US_CUSTOMARY_SYSTEM])
async def test_f_ent_02_unit_system_leaves_knots(
    hass: HomeAssistant, fake_ports: FakePorts, freezer: FrozenDateTimeFactory, units
):
    hass.config.units = units
    entry = make_entry(hass)
    await setup(hass, entry)
    fake_ports[BY_ID_PORT].feed_lines(rmc())
    await tick(hass, freezer)
    st = state(hass, entry, "sog")
    assert st.attributes["unit_of_measurement"] == UnitOfSpeed.KNOTS
    assert float(st.state) == pytest.approx(5.2)


# --- F-ENT-03 ---------------------------------------------------------------


async def test_f_ent_03_device_tracker(
    hass: HomeAssistant, loaded, fake_ports: FakePorts, freezer: FrozenDateTimeFactory
):
    eid = entity_id(hass, loaded, "position", "device_tracker")
    assert eid == "device_tracker.garnet"
    st = hass.states.get(eid)
    assert st.attributes["source_type"] == "gps"
    assert st.attributes["latitude"] == pytest.approx(43.5)
    assert st.attributes["longitude"] == pytest.approx(7 + 15.5 / 60)
    assert st.attributes["sog"] == pytest.approx(5.2)
    assert st.attributes["cog"] == pytest.approx(271.0)
    assert st.attributes["position_source"] == "gps"
    # Moves ~93 m north: written; 3 m more: below the 5 m dead-band
    fake_ports[BY_ID_PORT].feed_lines(rmc(lat="4330.050"))
    await tick(hass, freezer)
    assert hass.states.get(eid).attributes["latitude"] == pytest.approx(43.5 + 0.05 / 60)
    fake_ports[BY_ID_PORT].feed_lines(rmc(lat="4330.0516"))
    await tick(hass, freezer)
    assert hass.states.get(eid).attributes["latitude"] == pytest.approx(43.5 + 0.05 / 60)


# --- F-ENT-04 ---------------------------------------------------------------


async def test_f_ent_04_gps_silent_own_boat_unavailable(
    hass: HomeAssistant, loaded, freezer: FrozenDateTimeFactory
):
    await tick(hass, freezer, 9)
    assert state(hass, loaded, "sog").state != STATE_UNAVAILABLE
    await tick(hass, freezer, 2)  # 11 s without GPS > 10 s staleness timeout
    for key in OWN_BOAT_KEYS:
        assert state(hass, loaded, key).state == STATE_UNAVAILABLE, key
    assert state(hass, loaded, "position", "device_tracker").state == STATE_UNAVAILABLE
    assert state(hass, loaded, "own_position_source").state == STATE_UNAVAILABLE
    assert state(hass, loaded, "ais_targets").state == "2"  # count needs no own position
    await tick(hass, freezer, 5)  # next rebuild of the list (at most every 5 s, SPEC §10.2)
    targets = state(hass, loaded, "ais_targets")
    assert targets.state == "2"
    assert all(t["distance_nm"] is None for t in targets.attributes["targets"])
    assert state(hass, loaded, "connected", "binary_sensor").state == "on"


# --- F-ENT-05 ---------------------------------------------------------------


async def test_f_ent_05_heading_never_provided(hass: HomeAssistant, loaded, freezer, caplog):
    with caplog.at_level(logging.WARNING):
        await tick(hass, freezer)
    assert state(hass, loaded, "heading").state == STATE_UNAVAILABLE
    assert not [r for r in caplog.records if r.name.startswith("custom_components.vigie")]


async def test_heading_from_hdt(hass: HomeAssistant, loaded, fake_ports: FakePorts, freezer):
    fake_ports[BY_ID_PORT].feed_lines(nmea("HEHDT,268.4,T"))
    await tick(hass, freezer)
    assert float(state(hass, loaded, "heading").state) == pytest.approx(268.4)


# --- F-ENT-06 / F-ENT-07 ------------------------------------------------------


async def test_f_ent_06_two_boats_no_unique_id_collision(
    hass: HomeAssistant, fake_ports: FakePorts
):
    first = make_entry(hass)
    second = make_entry(hass, port="/dev/ttyUSB1", title="Jade")
    await setup(hass, first)
    reg = er.async_get(hass)
    ids_1 = {e.unique_id for e in er.async_entries_for_config_entry(reg, first.entry_id)}
    ids_2 = {e.unique_id for e in er.async_entries_for_config_entry(reg, second.entry_id)}
    assert ids_1 and len(ids_1) == len(ids_2)
    assert not ids_1 & ids_2
    assert entity_id(hass, second, "position", "device_tracker") == "device_tracker.jade"


async def test_f_ent_07_unique_ids_prefixed_by_entry_id(hass: HomeAssistant, loaded):
    ents = er.async_entries_for_config_entry(er.async_get(hass), loaded.entry_id)
    assert len(ents) == 18  # P1: 14; P2 adds collision_risk, closest target, CPA, TCPA
    assert all(e.unique_id.startswith(f"{loaded.entry_id}_") for e in ents)
    assert all(e.platform == DOMAIN for e in ents)


# --- F-HUB-03 (entity half) -------------------------------------------------------


async def test_f_hub_03_disconnect_entities_unavailable_immediately(
    hass: HomeAssistant, loaded, fake_ports: FakePorts
):
    fake = fake_ports[BY_ID_PORT]
    fake.available = False
    fake.disconnect()
    await hass.async_block_till_done()  # no tick: the change is pushed at once
    for key in [*OWN_BOAT_KEYS, "ais_targets", "own_position_source"]:
        assert state(hass, loaded, key).state == STATE_UNAVAILABLE, key
    assert state(hass, loaded, "position", "device_tracker").state == STATE_UNAVAILABLE
    connected = state(hass, loaded, "connected", "binary_sensor")
    assert connected.state == STATE_OFF
    assert state(hass, loaded, "checksum_errors").state == "0"  # diagnostics stay available


# --- F-LIFE-06 (entity half) -------------------------------------------------------


async def test_f_life_06_reload_keeps_unique_ids(hass: HomeAssistant, loaded):
    reg = er.async_get(hass)
    before = {
        e.unique_id: e.entity_id for e in er.async_entries_for_config_entry(reg, loaded.entry_id)
    }
    result = await hass.config_entries.options.async_init(loaded.entry_id)
    await hass.config_entries.options.async_configure(
        result["flow_id"], {**result["data_schema"]({}), CONF_UPDATE_INTERVAL: 2}
    )
    await hass.async_block_till_done()
    assert loaded.runtime_data.update_interval_s == 2
    after = {
        e.unique_id: e.entity_id for e in er.async_entries_for_config_entry(reg, loaded.entry_id)
    }
    assert after == before


# --- Throttle and dead-band (SPEC §10.2, NFR-04) -------------------------------------


async def test_sog_deadband_and_one_write_per_tick(
    hass: HomeAssistant, loaded, fake_ports: FakePorts, freezer: FrozenDateTimeFactory
):
    eid = entity_id(hass, loaded, "sog")
    writes: list[str] = []
    hass.bus.async_listen(
        "state_changed",
        lambda e: writes.append(e.data["new_state"].state) if e.data["entity_id"] == eid else None,
    )
    fake = fake_ports[BY_ID_PORT]
    fake.feed_lines(rmc(sog=5.24))  # < 0.1 kn from the last written 5.2
    await tick(hass, freezer)
    assert writes == []
    for sog in (5.3, 5.4, 5.5, 5.6, 5.7):  # five updates within one interval
        fake.feed_lines(rmc(sog=sog))
        await hass.async_block_till_done()
    assert writes == []  # nothing until the tick
    await tick(hass, freezer)
    assert [float(w) for w in writes] == [pytest.approx(5.7)]  # one write, latest value


async def test_cog_deadband_wraps_through_north(
    hass: HomeAssistant, fake_ports: FakePorts, freezer: FrozenDateTimeFactory
):
    entry = make_entry(hass)
    await setup(hass, entry)
    fake = fake_ports[BY_ID_PORT]
    fake.feed_lines(rmc(cog=359.5))
    await tick(hass, freezer)
    fake.feed_lines(rmc(cog=0.2))  # 0.7° across north: below the 1° dead-band
    await tick(hass, freezer)
    assert float(state(hass, entry, "cog").state) == pytest.approx(359.5)
    fake.feed_lines(rmc(cog=1.0))
    await tick(hass, freezer)
    assert float(state(hass, entry, "cog").state) == pytest.approx(1.0)


# --- Traffic and diagnostics sensors (SPEC §9.2, §9.5) -------------------------------------


async def test_ais_targets_sensor(hass: HomeAssistant, loaded, fake_ports: FakePorts, freezer):
    st = state(hass, loaded, "ais_targets")
    assert st.state == "2"
    assert st.attributes["state_class"] == SensorStateClass.MEASUREMENT
    targets = st.attributes["targets"]
    distances = [t["distance_nm"] for t in targets]
    assert distances == sorted(distances)  # nearest first
    first = targets[0]
    assert set(first) == {
        "mmsi",
        "name",
        "class",
        "lat",
        "lon",
        "sog",
        "cog",
        "distance_nm",
        "age_s",
        "cpa_nm",
        "tcpa_min",
        "ship_type",
        "length_m",
    }
    # A new target: count now, attribute list at most every 5 s
    fake_ports[BY_ID_PORT].feed_lines(nmea("AIVDM,1,1,,A,15MgK45P3@G?fl0E`JbR0OwT0@MS,0", "!"))
    await tick(hass, freezer)
    st = state(hass, loaded, "ais_targets")
    assert st.state == "3" and len(st.attributes["targets"]) == 2
    await tick(hass, freezer, 4)
    assert len(state(hass, loaded, "ais_targets").attributes["targets"]) == 3


def test_ais_targets_attribute_not_recorded():
    from custom_components.vigie.sensor import AisTargetsSensor

    assert "targets" in AisTargetsSensor._unrecorded_attributes  # large list (SPEC §10.2)


async def test_diagnostic_sensors(hass: HomeAssistant, loaded, fake_ports: FakePorts, freezer):
    reg = er.async_get(hass)
    for key in ("sentences_per_min", "last_sentence_age"):
        ent = reg.async_get(entity_id(hass, loaded, key))
        assert ent.disabled_by is er.RegistryEntryDisabler.INTEGRATION, key
        assert ent.entity_category is EntityCategory.DIAGNOSTIC
    assert state(hass, loaded, "own_position_source").state == "gps"
    assert state(hass, loaded, "connected", "binary_sensor").state == "on"
    fake_ports[BY_ID_PORT].feed_lines(rmc()[:-2] + "00", AIS_TYPE1[:-2] + "00")  # bad checksums
    fake_ports[BY_ID_PORT].feed_lines(nmea("AIVDM,1,1,,B,177KQJ5000G?tO`K>RA1wU,0", "!"))  # short
    await tick(hass, freezer)
    assert state(hass, loaded, "checksum_errors").state == "2"
    assert state(hass, loaded, "ais_rejected").state == "1"
    assert state(hass, loaded, "checksum_errors").attributes["state_class"] == "total_increasing"


async def test_enabled_diagnostics_report_rate_and_age(
    hass: HomeAssistant, fake_ports: FakePorts, freezer: FrozenDateTimeFactory
):
    entry = make_entry(hass)
    reg = er.async_get(hass)
    await setup(hass, entry)
    for key in ("sentences_per_min", "last_sentence_age"):
        reg.async_update_entity(entity_id(hass, entry, key), disabled_by=None)
    await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    fake_ports[BY_ID_PORT].feed_lines(rmc(), GGA, AIS_TYPE1)
    await tick(hass, freezer)
    assert state(hass, entry, "sentences_per_min").state == "3"
    await tick(hass, freezer, 5)
    assert float(state(hass, entry, "last_sentence_age").state) == pytest.approx(6, abs=1)
