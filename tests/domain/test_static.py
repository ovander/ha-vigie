"""AIS static data store — U-STA-01…07 (TEST §3.6, SPEC §9.4, OD-18)."""

from dataclasses import replace

import pytest

from custom_components.vigie.nmea.ais_decoder import VesselStatic
from custom_components.vigie.state import AisStaticStore, StaticInfo
from tests.helpers import FakeClock

MMSI = 227000001


def static(msg_type: int = 5, part: str | None = None, **fields) -> VesselStatic:
    base = VesselStatic(
        mmsi=MMSI,
        ais_class="A" if msg_type == 5 else "B",
        msg_type=msg_type,
        part=part,
        name=None,
        callsign=None,
        imo=None,
        ship_type=None,
        to_bow=None,
        to_stern=None,
        to_port=None,
        to_starboard=None,
        draught_m=None,
        destination=None,
        mothership_mmsi=None,
        own_ship=False,
        channel="A",
        received_at=0.0,
    )
    return replace(base, **fields)


TYPE5 = static(
    name="CARGO ONE",
    callsign="ABCD",
    imo=9123456,
    ship_type=70,
    to_bow=150,
    to_stern=30,
    to_port=15,
    to_starboard=15,
    draught_m=8.5,
    destination="MARSEILLE",
)
PART_A = static(24, "A", name="ALBATROS")
PART_B = static(
    24, "B", callsign="FAB1234", ship_type=36, to_bow=8, to_stern=4, to_port=2, to_starboard=2
)


@pytest.fixture
def clock():
    return FakeClock()


@pytest.fixture
def store(clock):
    return AisStaticStore(clock=clock)


# --- U-STA-01: type 5 stored and read back -------------------------------------------------


def test_u_sta_01_type5_stored(store, clock):
    assert store.get(MMSI) is None
    assert store.update(TYPE5) is True
    info = store.get(MMSI)
    assert isinstance(info, StaticInfo)
    assert (info.mmsi, info.name, info.callsign, info.imo) == (MMSI, "CARGO ONE", "ABCD", 9123456)
    assert (info.ship_type, info.ship_category) == (70, "cargo")
    assert (info.length_m, info.beam_m, info.draught_m) == (180, 30, 8.5)
    assert (info.destination, info.mothership_mmsi) == ("MARSEILLE", None)
    assert info.updated_at == clock()
    assert len(store) == 1


# --- U-STA-02: type 24 parts A and B merged, in either order -------------------------------


@pytest.mark.parametrize("order", [(PART_A, PART_B), (PART_B, PART_A)])
def test_u_sta_02_type24_parts_merged(store, order):
    for part in order:
        store.update(part)
    info = store.get(MMSI)
    assert (info.name, info.callsign, info.ship_category) == ("ALBATROS", "FAB1234", "sailing")
    assert (info.length_m, info.beam_m) == (12, 4)


# --- U-STA-03: known values kept, newer values win ----------------------------------------


def test_u_sta_03_later_report_updates_without_erasing(store):
    store.update(TYPE5)
    store.update(static(destination="LE HAVRE", draught_m=None))  # draught not available
    info = store.get(MMSI)
    assert (info.destination, info.draught_m, info.name) == ("LE HAVRE", 8.5, "CARGO ONE")
    store.update(static(name="CARGO ONE II"))
    assert store.get(MMSI).name == "CARGO ONE II"


def test_u_sta_03_type19_static_part_and_auxiliary_craft(store):
    store.update(
        static(19, name="SEA BREEZE", ship_type=37, to_bow=9, to_stern=3, to_port=2, to_starboard=1)
    )
    assert (store.get(MMSI).name, store.get(MMSI).ship_category) == ("SEA BREEZE", "pleasure_craft")
    tender = replace(
        PART_B,
        mmsi=982270001,
        to_bow=None,
        to_stern=None,
        to_port=None,
        to_starboard=None,
        mothership_mmsi=MMSI,
    )
    store.update(tender)
    info = store.get(982270001)
    assert (info.mothership_mmsi, info.length_m) == (MMSI, None)


# --- U-STA-04: kept before and without any position ---------------------------------------


def test_u_sta_04_independent_of_the_target_table(store, clock):
    """Static data arrives first and outlives a target that expires and comes back."""
    store.update(PART_A)
    clock.advance(20 * 60)  # longer than the target expiry, shorter than 30 min
    assert store.expire() == []
    assert store.get(MMSI).name == "ALBATROS"


# --- U-STA-05: dropped 30 min after the last static report --------------------------------


def test_u_sta_05_expiry_after_30_min(store, clock):
    store.update(TYPE5)
    clock.advance(25 * 60)
    store.update(static(destination="SETE"))  # refreshed
    clock.advance(29 * 60)
    assert store.expire() == []
    assert store.get(MMSI).destination == "SETE"
    clock.advance(61)
    assert store.get(MMSI) is None  # stale data is never returned, even before expire()
    assert store.expire() == [MMSI]
    assert len(store) == 0


def test_u_sta_05_max_age_configurable(clock):
    store = AisStaticStore(max_age_s=60, clock=clock)
    store.update(TYPE5)
    clock.advance(61)
    assert store.expire() == [MMSI]


# --- U-STA-06: at most 2 000 MMSIs, oldest update dropped first -----------------------------


def test_u_sta_06_capacity(clock):
    store = AisStaticStore(clock=clock)
    assert store.capacity == 2000
    small = AisStaticStore(capacity=3, clock=clock)
    for mmsi in (1, 2, 3):
        small.update(replace(PART_A, mmsi=200000000 + mmsi))
        clock.advance(1)
    small.update(replace(PART_B, mmsi=200000001))  # refreshed: now the newest
    small.update(replace(PART_A, mmsi=200000004))
    assert len(small) == 3
    assert small.get(200000002) is None  # oldest update dropped
    assert small.get(200000001).callsign == "FAB1234"
    assert small.get(200000001).name == "ALBATROS"  # merged, not replaced


# --- U-STA-07: own ship refused -------------------------------------------------------------


def test_u_sta_07_own_ship_refused(store):
    assert store.update(replace(TYPE5, own_ship=True)) is False
    assert store.update(TYPE5, own_mmsi=MMSI) is False
    assert len(store) == 0
