"""Domain core — U-COO-01…06 (TEST §3.5) and U-TRF-12 (TEST §3.4), SPEC §7.4, §9.4, §10.2."""

from datetime import UTC, datetime

import pytest

from custom_components.vigie.nmea.ais_decoder import VesselPosition
from custom_components.vigie.nmea.parsers import FixMode, FixQuality, Gga, Gsa, Hdt, Rmc, Vtg
from custom_components.vigie.state import (
    COG,
    FIX_MODE,
    FIX_QUALITY,
    HDOP,
    HEADING,
    PDOP,
    POSITION,
    SATELLITES,
    SOG,
    UTC_TIME,
    VARIATION,
    AisTargetTable,
    OwnBoatState,
    Source,
    WriteGate,
    angle_delta,
    position_delta_m,
)
from tests.helpers import FakeClock

OWN_MMSI = 227000001  # synthetic


def rmc(lat=43.5, lon=7.25, sog=5.0, cog=90.0, valid=True, var=None):
    utc = datetime(2026, 9, 27, 12, 0, tzinfo=UTC)
    if not valid:
        return Rmc("GP", False, None, None, None, None, utc, var)
    return Rmc("GP", True, lat, lon, sog, cog, utc, var)


def vp(
    mmsi=235000001,
    ais_class="A",
    lat=43.6,
    lon=7.3,
    sog=6.0,
    cog=180.0,
    heading=None,
    nav_status="under_way_engine",
    name=None,
    own_ship=False,
    msg_type=None,
):
    return VesselPosition(
        mmsi=mmsi,
        ais_class=ais_class,
        msg_type=msg_type or (1 if ais_class == "A" else 18),
        latitude=lat,
        longitude=lon,
        sog_knots=sog,
        cog_deg=cog,
        heading_deg=heading,
        nav_status=nav_status if ais_class == "A" else None,
        name=name,
        own_ship=own_ship,
        channel="A",
        received_at=0.0,
    )


@pytest.fixture
def clock():
    return FakeClock()


# --- OwnBoatState ----------------------------------------------------------


def test_u_coo_01_sog_most_recent_valid_value_wins_with_source(clock):
    state = OwnBoatState(clock=clock)
    assert state.apply_gps(rmc(sog=5.0)) >= {SOG, POSITION, COG}
    clock.advance(0.5)
    state.apply_gps(Vtg("GP", 91.0, None, 5.4))
    sog = state.get(SOG)
    assert sog is not None
    assert (sog.value, sog.source, sog.sentence, sog.updated_at) == (
        5.4,
        Source.GPS,
        "VTG",
        clock(),
    )
    clock.advance(0.5)
    state.apply_gps(rmc(sog=5.2))
    assert state.get(SOG).value == 5.2
    assert state.get(SOG).sentence == "RMC"


def test_u_coo_01_missing_values_do_not_overwrite(clock):
    state = OwnBoatState(clock=clock)
    state.apply_gps(rmc(sog=5.0))
    changed = state.apply_gps(Vtg("GP", None, None, None))
    assert changed == frozenset()
    assert state.get(SOG).value == 5.0


def test_void_rmc_not_applied_but_utc_kept(clock):
    state = OwnBoatState(clock=clock)
    assert state.apply_gps(rmc(valid=False)) == {UTC_TIME}
    assert state.get(POSITION) is None
    assert state.get(UTC_TIME).value == datetime(2026, 9, 27, 12, 0, tzinfo=UTC)


def test_all_gps_fields_mapped(clock):
    state = OwnBoatState(clock=clock)
    state.apply_gps(rmc(var=-1.5))
    state.apply_gps(Gga("GN", 43.5, 7.25, FixQuality.DGPS, 9, 0.8))
    state.apply_gps(Gsa("GN", FixMode.FIX_3D, 1.6, 0.8, 1.4))
    state.apply_gps(Hdt("HE", 92.0))
    values = {k: state.get(k).value for k in (VARIATION, FIX_QUALITY, SATELLITES, HDOP, FIX_MODE)}
    assert values == {
        VARIATION: -1.5,
        FIX_QUALITY: FixQuality.DGPS,
        SATELLITES: 9,
        HDOP: 0.8,
        FIX_MODE: FixMode.FIX_3D,
    }
    assert state.get(PDOP).value == 1.6
    assert state.get(HEADING).value == 92.0
    assert state.get(POSITION).value == (43.5, 7.25)
    assert state.get(POSITION).sentence == "GGA"


def test_gga_without_fix_leaves_position_to_expire(clock):
    state = OwnBoatState(stale_timeout_s=10.0, clock=clock)
    state.apply_gps(rmc())
    state.apply_gps(Gga("GP", None, None, FixQuality.NO_FIX, 0, None))
    assert state.get(FIX_QUALITY).value is FixQuality.NO_FIX
    clock.advance(10.1)
    assert state.get(POSITION) is None


def test_u_coo_02_gps_fresh_vdo_ignored_for_own_state(clock):
    state = OwnBoatState(clock=clock)
    state.apply_gps(rmc(lat=43.5, lon=7.25, sog=5.0, cog=90.0))
    state.apply_vdo(vp(mmsi=OWN_MMSI, lat=43.51, lon=7.26, sog=4.0, cog=80.0, own_ship=True))
    assert state.get(POSITION).value == (43.5, 7.25)
    assert state.get(SOG).value == 5.0
    assert state.get(COG).value == 90.0
    assert state.position_source is Source.GPS


def test_u_coo_03_gps_stale_falls_back_to_vdo(clock):
    state = OwnBoatState(stale_timeout_s=10.0, clock=clock)
    state.apply_gps(rmc(lat=43.5, lon=7.25))
    clock.advance(10.5)  # GPS now stale
    state.apply_vdo(vp(mmsi=OWN_MMSI, lat=43.51, lon=7.26, sog=4.0, cog=80.0, own_ship=True))
    pos = state.get(POSITION)
    assert pos is not None and pos.value == (43.51, 7.26)
    assert pos.source is Source.VDO
    assert state.position_source is Source.VDO
    assert state.get(SOG).value == 4.0
    # GPS comes back: preferred again
    state.apply_gps(rmc(lat=43.52, lon=7.27))
    assert state.position_source is Source.GPS


def test_u_coo_03_vdo_disabled_by_option(clock):
    state = OwnBoatState(stale_timeout_s=10.0, use_vdo=False, clock=clock)
    assert state.apply_vdo(vp(mmsi=OWN_MMSI, own_ship=True)) == frozenset()
    assert state.get(POSITION) is None
    assert state.position_source is None
    assert state.own_mmsi is None


def test_everything_stale_gives_none(clock):
    state = OwnBoatState(stale_timeout_s=10.0, clock=clock)
    state.apply_gps(rmc())
    state.apply_vdo(vp(mmsi=OWN_MMSI, own_ship=True))
    clock.advance(10.0)
    assert state.get(POSITION) is not None  # exactly at the timeout: still fresh
    clock.advance(0.1)
    assert state.get(POSITION) is None
    assert state.position_source is None


def test_heading_hdt_first_then_vdo(clock):
    state = OwnBoatState(stale_timeout_s=10.0, clock=clock)
    state.apply_vdo(vp(mmsi=OWN_MMSI, heading=270, own_ship=True))
    assert state.get(HEADING).value == 270
    assert state.get(HEADING).source is Source.VDO
    state.apply_gps(Hdt("HE", 268.5))
    assert state.get(HEADING).value == 268.5
    assert state.get(HEADING).source is Source.GPS


def test_vdo_heading_not_available_is_none(clock):
    state = OwnBoatState(clock=clock)
    state.apply_vdo(vp(mmsi=OWN_MMSI, heading=None, own_ship=True))
    assert state.get(HEADING) is None


def test_own_mmsi_learned_from_vdo_or_configured(clock):
    state = OwnBoatState(clock=clock)
    assert state.own_mmsi is None
    state.apply_vdo(vp(mmsi=OWN_MMSI, own_ship=True))
    assert state.own_mmsi == OWN_MMSI
    assert OwnBoatState(own_mmsi=111111111, clock=clock).own_mmsi == 111111111


def test_vdm_is_not_own_state(clock):
    state = OwnBoatState(clock=clock)
    assert state.apply_vdo(vp(own_ship=False)) == frozenset()
    assert state.get(POSITION) is None


# --- AisTargetTable --------------------------------------------------------


def test_u_coo_04_vdm_with_own_mmsi_not_inserted(clock):
    table = AisTargetTable(clock=clock)
    assert table.upsert(vp(mmsi=OWN_MMSI), own_mmsi=OWN_MMSI) is False
    assert table.upsert(vp(mmsi=OWN_MMSI, own_ship=True)) is False  # VDO never enters
    assert len(table) == 0
    assert table.upsert(vp(mmsi=235000001), own_mmsi=OWN_MMSI) is True
    assert len(table) == 1


def test_upsert_updates_and_keeps_known_name(clock):
    table = AisTargetTable(clock=clock)
    table.upsert(vp(mmsi=367000001, ais_class="B", msg_type=19, name="SEA DOG"))
    clock.advance(30)
    table.upsert(vp(mmsi=367000001, ais_class="B", lat=43.7, name=None))
    target = table.get(367000001)
    assert target is not None
    assert target.name == "SEA DOG"
    assert target.report.latitude == 43.7
    assert target.last_seen == clock()
    assert 367000001 in table
    assert [t.mmsi for t in table.targets()] == [367000001]


@pytest.mark.parametrize(
    "ais_class,nav_status,expiry_s",
    [
        ("A", "under_way_engine", 600),
        ("A", "at_anchor", 900),
        ("A", "moored", 900),
        ("B", None, 900),
    ],
)
def test_u_trf_12_stale_target_removed_after_class_expiry(clock, ais_class, nav_status, expiry_s):
    table = AisTargetTable(expiry_a_s=600, expiry_b_s=900, clock=clock)
    table.upsert(vp(mmsi=235000009, ais_class=ais_class, nav_status=nav_status))
    clock.advance(expiry_s)
    assert table.expire() == []  # exactly at expiry: kept
    clock.advance(1)
    assert table.expire() == [235000009]
    assert len(table) == 0


def test_u_trf_12_refreshed_target_kept(clock):
    table = AisTargetTable(expiry_a_s=600, clock=clock)
    table.upsert(vp(mmsi=235000009))
    clock.advance(500)
    table.upsert(vp(mmsi=235000009))
    clock.advance(500)
    assert table.expire() == []


def test_nearest_ordered_by_distance_and_capped(clock):
    table = AisTargetTable(clock=clock)
    for i in range(1, 61):  # 60 targets, i/60° north of own position
        table.upsert(vp(mmsi=235000000 + i, lat=43.0 + i / 60, lon=7.0))
    table.upsert(vp(mmsi=235999999, lat=None, lon=None))  # no position yet
    listed = table.nearest(43.0, 7.0, limit=50)
    assert len(listed) == 50
    assert [t.mmsi for t, _ in listed[:3]] == [235000001, 235000002, 235000003]
    assert listed[0][1] == pytest.approx(1.0, rel=1e-3)
    distances = [d for _, d in listed]
    assert distances == sorted(distances)


def test_nearest_without_own_position_orders_by_recency(clock):
    table = AisTargetTable(clock=clock)
    table.upsert(vp(mmsi=1))
    clock.advance(5)
    table.upsert(vp(mmsi=2))
    clock.advance(5)
    table.upsert(vp(mmsi=3, lat=None, lon=None))
    assert [(t.mmsi, d) for t, d in table.nearest(None, None)] == [
        (3, None),
        (2, None),
        (1, None),
    ]


def test_nearest_targets_without_position_come_last(clock):
    table = AisTargetTable(clock=clock)
    table.upsert(vp(mmsi=1, lat=None, lon=None))
    table.upsert(vp(mmsi=2, lat=43.1, lon=7.0))
    assert [(t.mmsi, d is None) for t, d in table.nearest(43.0, 7.0)] == [(2, False), (1, True)]


# --- WriteGate -------------------------------------------------------------


def test_u_coo_05_deadband_against_last_written_value(clock):
    gate = WriteGate(interval_s=1.0, deadband=0.1, clock=clock)
    written = []
    for sog in (5.00, 5.04, 5.12):
        if gate.should_write(sog):
            written.append(sog)
        clock.advance(1.0)
    assert written == [5.00, 5.12]


def test_u_coo_05_slow_drift_is_written_once_it_adds_up(clock):
    gate = WriteGate(interval_s=1.0, deadband=0.1, clock=clock)
    written = []
    for sog in (5.00, 5.04, 5.08, 5.10, 5.12):
        if gate.should_write(sog):
            written.append(sog)
        clock.advance(1.0)
    assert written == [5.00, 5.10]  # 5.10 − 5.00 reaches the dead-band exactly


def test_u_coo_06_throttle_one_write_per_interval_with_latest_value(clock):
    gate = WriteGate(interval_s=1.0, deadband=None, clock=clock)
    written = []
    for i in range(10):  # 10 updates within one second
        value = 5.0 + i
        if gate.should_write(value):
            written.append(value)
        clock.advance(0.1)
    # Next tick, one interval after the first write: the latest value goes out
    assert gate.should_write(14.0)
    written.append(14.0)
    assert written == [5.0, 14.0]


def test_gate_unchanged_value_not_rewritten(clock):
    gate = WriteGate(interval_s=1.0, clock=clock)
    assert gate.should_write("gps")
    clock.advance(5)
    assert not gate.should_write("gps")
    assert gate.should_write("vdo")


def test_gate_none_transitions_always_written(clock):
    gate = WriteGate(interval_s=1.0, deadband=0.1, clock=clock)
    assert gate.should_write(5.0)
    clock.advance(1)
    assert gate.should_write(None)
    clock.advance(1)
    assert not gate.should_write(None)
    assert gate.should_write(5.0)


def test_gate_reset_forces_next_write(clock):
    gate = WriteGate(interval_s=1.0, deadband=0.1, clock=clock)
    assert gate.should_write(5.0)
    gate.reset()
    assert gate.should_write(5.0)


def test_angle_deadband_wraps_around(clock):
    gate = WriteGate(interval_s=0.0, deadband=1.0, delta=angle_delta, clock=clock)
    assert gate.should_write(359.5)
    assert not gate.should_write(0.2)  # 0.7° across north
    assert gate.should_write(0.6)  # 1.1° from 359.5
    assert angle_delta(350.0, 10.0) == pytest.approx(20.0)
    assert angle_delta(10.0, 350.0) == pytest.approx(20.0)


def test_position_deadband_in_metres(clock):
    gate = WriteGate(interval_s=0.0, deadband=5.0, delta=position_delta_m, clock=clock)
    assert gate.should_write((43.5, 7.25))
    assert not gate.should_write((43.50003, 7.25))  # ≈ 3.3 m
    assert gate.should_write((43.50005, 7.25))  # ≈ 5.6 m from the last written
    assert position_delta_m((0.0, 0.0), (0.0, 0.0)) == 0.0


def test_configuration_is_readable(clock):
    state = OwnBoatState(stale_timeout_s=30.0, use_vdo=False, clock=clock)
    assert (state.stale_timeout_s, state.use_vdo) == (30.0, False)
    assert AisTargetTable(expiry_a_s=720, expiry_b_s=1200, clock=clock).expiry_s == (720, 1200)
