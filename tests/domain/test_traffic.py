"""Traffic logic — U-TRF-01…11, 13, 14, 15 (TEST §3.4, SPEC §8).

Expected CPA/TCPA values are the hand-computed ones of TEST §3.4, never an oracle.
Own boat at the origin of a local frame at 43.5° N, 7.25° E, heading 000° at 6 kn unless
stated. Tolerances: CPA ± 0.01 NM, TCPA ± 0.1 min.
"""

import math

import pytest

from custom_components.vigie.geo import distance_nm
from custom_components.vigie.traffic import (
    Encounter,
    Kinematics,
    RiskLatch,
    ThreatSettings,
    closest_threat,
    displace,
    encounter,
    is_threat,
    local_offset_nm,
)
from tests.helpers import FakeClock

LAT0, LON0 = 43.5, 7.25
CPA_TOL, TCPA_TOL = 0.01, 0.1
DEFAULTS = ThreatSettings()  # CPA 0.5 NM, TCPA 15 min, stationary targets excluded


def own(sog: float = 6.0, cog: float = 0.0, at: float = 0.0, lat=LAT0, lon=LON0) -> Kinematics:
    return Kinematics(lat, lon, sog, cog, at)


def target(east_nm: float, north_nm: float, sog, cog, at: float = 0.0, base=(LAT0, LON0)):
    lat, lon = displace(base[0], base[1], east_nm, north_nm)
    return Kinematics(lat, lon, sog, cog, at)


def velocity_target(east_nm, north_nm, v_east, v_north):
    """Target given by its absolute velocity components (kn)."""
    sog = math.hypot(v_east, v_north)
    cog = math.degrees(math.atan2(v_east, v_north)) % 360
    return target(east_nm, north_nm, sog, cog)


# --- U-TRF-01 … 08: reference scenarios ----------------------------------------------

SCENARIOS = {
    # id: (target, nav_status, expected CPA, expected TCPA, threat)
    "U-TRF-01": (target(0, 2, 6, 180), None, 0.00, 10.0, True),
    "U-TRF-02": (target(1, 0, 6, 270), None, 0.71, 5.0, False),
    "U-TRF-03": (target(1, 0, 12, 270), None, 0.45, 4.0, True),
    "U-TRF-04": (target(0, 1, 4, 0), None, 0.00, 30.0, False),
    # relative velocity (−6, −5) kn = absolute (−6, +1) kn with own (0, 6)
    "U-TRF-05": (velocity_target(2, 2, -6, 1), None, 0.26, 21.6, False),
    "U-TRF-08": (target(0, 0.4, 0, 0), "at_anchor", 0.00, 4.0, False),
}


@pytest.mark.parametrize("tid", sorted(SCENARIOS))
def test_u_trf_reference_scenarios(tid):
    tgt, nav_status, cpa, tcpa, threat = SCENARIOS[tid]
    e = encounter(own(), tgt)
    assert e is not None
    assert e.cpa_nm == pytest.approx(cpa, abs=CPA_TOL), tid
    assert e.tcpa_min == pytest.approx(tcpa, abs=TCPA_TOL), tid
    assert is_threat(e, DEFAULTS, nav_status=nav_status, sog_kn=tgt.sog_kn) is threat, tid


def test_u_trf_05_becomes_threat_as_time_advances():
    """U-TRF-05 + OD-16: 7 min later (both dead-reckoned), TCPA < 15 min, CPA unchanged."""
    tgt = velocity_target(2, 2, -6, 1)
    e = encounter(own(), tgt, now=7 * 60)
    assert e.cpa_nm == pytest.approx(0.26, abs=CPA_TOL)
    assert e.tcpa_min == pytest.approx(21.6 - 7, abs=TCPA_TOL)
    assert is_threat(e, DEFAULTS, nav_status=None, sog_kn=tgt.sog_kn)


def test_u_trf_06_diverging():
    e = encounter(own(), target(0, -1, 3, 0))
    assert e.tcpa_min is not None and e.tcpa_min < 0
    assert e.cpa_nm is None  # reported for TCPA ≥ 0 only (SPEC §8.1)
    assert not is_threat(e, DEFAULTS, nav_status=None, sog_kn=3)


def test_u_trf_07_parallel_same_speed():
    e = encounter(own(), target(0.3, 0, 6, 0))
    assert e.tcpa_min is None  # |V| ≈ 0: undefined
    assert e.cpa_nm == pytest.approx(0.30, abs=CPA_TOL)  # current distance
    assert not is_threat(e, DEFAULTS, nav_status=None, sog_kn=6)


def test_u_trf_08_anchored_target_threat_with_exclusion_off():
    tgt, *_ = SCENARIOS["U-TRF-08"]
    e = encounter(own(), tgt)
    no_exclusion = ThreatSettings(exclude_stationary=False)
    assert is_threat(e, no_exclusion, nav_status="at_anchor", sog_kn=0.0)
    assert is_threat(e, DEFAULTS, nav_status="moored", sog_kn=0.0) is False
    # Moving (≥ 0.5 kn) or Class B (no nav status): never excluded
    assert is_threat(e, DEFAULTS, nav_status="at_anchor", sog_kn=0.6)
    assert is_threat(e, DEFAULTS, nav_status=None, sog_kn=0.0)


@pytest.mark.parametrize(
    "cpa,tcpa,threat",
    [
        (0.49, 14.9, True),
        (0.50, 10.0, False),
        (0.1, 15.0, False),
        (0.1, 0.0, True),
        (0.1, -0.1, False),
    ],
)
def test_threat_thresholds_are_strict(cpa, tcpa, threat):
    e = Encounter(
        distance_nm=1.0, bearing_deg=0.0, cpa_nm=cpa if tcpa >= 0 else None, tcpa_min=tcpa
    )
    assert is_threat(e, DEFAULTS, nav_status=None, sog_kn=5.0) is threat


def test_thresholds_are_configurable():
    e = encounter(own(), SCENARIOS["U-TRF-02"][0])  # CPA 0.71 NM, TCPA 5 min
    assert is_threat(e, ThreatSettings(cpa_nm=1.0), nav_status=None, sog_kn=6)
    assert not is_threat(e, ThreatSettings(cpa_nm=1.0, tcpa_min=4.0), nav_status=None, sog_kn=6)


def test_distance_and_bearing():
    e = encounter(own(), target(1, 1, 6, 180))
    assert e.distance_nm == pytest.approx(math.sqrt(2), rel=2e-3)
    assert e.bearing_deg == pytest.approx(45.0, abs=0.1)


# --- U-TRF-09 geodesy ----------------------------------------------------------------


@pytest.mark.parametrize("dist", [1.0, 5.0, 20.0])
@pytest.mark.parametrize("bearing", [0.0, 45.0, 90.0, 135.0, 225.0, 315.0])
def test_u_trf_09_flat_earth_vs_haversine(dist, bearing):
    east = dist * math.sin(math.radians(bearing))
    north = dist * math.cos(math.radians(bearing))
    lat, lon = displace(LAT0, LON0, east, north)
    true_nm = distance_nm(LAT0, LON0, lat, lon)
    e, n = local_offset_nm(LAT0, LON0, lat, lon)
    assert abs(math.hypot(e, n) - true_nm) / true_nm < 0.005


# --- U-TRF-10 missing data -----------------------------------------------------------


@pytest.mark.parametrize(
    "own_k,tgt_k",
    [
        (own(sog=None), target(0, 2, 6, 180)),
        (own(cog=None), target(0, 2, 6, 180)),
        (own(), target(0, 2, None, 180)),
        (own(), target(0, 2, 6, None)),
    ],
)
def test_u_trf_10_motion_unavailable(own_k, tgt_k):
    e = encounter(own_k, tgt_k)
    assert e is not None
    assert (e.cpa_nm, e.tcpa_min) == (None, None)
    assert e.distance_nm == pytest.approx(2.0, abs=0.01)  # position alone still gives distance
    assert not is_threat(e, DEFAULTS, nav_status=None, sog_kn=tgt_k.sog_kn)


@pytest.mark.parametrize("which", ["own", "target"])
def test_u_trf_10_position_unavailable(which):
    own_k = Kinematics(None, None, 6.0, 0.0, 0.0) if which == "own" else own()
    tgt_k = Kinematics(LAT0, None, 6.0, 180.0, 0.0) if which == "target" else target(0, 2, 6, 180)
    assert encounter(own_k, tgt_k) is None


# --- U-TRF-11 closest threat --------------------------------------------------------------


def _enc(cpa, tcpa):
    return Encounter(distance_nm=2.0, bearing_deg=0.0, cpa_nm=cpa, tcpa_min=tcpa)


def test_u_trf_11_smallest_tcpa_wins_tie_smallest_cpa():
    items = [(1, _enc(0.1, 12.0)), (2, _enc(0.4, 6.0)), (3, _enc(0.2, 6.0)), (4, _enc(0.0, 9.0))]
    assert closest_threat(items) == (3, items[2][1])
    assert closest_threat([]) is None


# --- U-TRF-13 antimeridian and equator ------------------------------------------------------


def test_u_trf_13_antimeridian():
    base = (0.0, 179.95)
    own_k = own(sog=6, cog=90, lat=base[0], lon=base[1])
    tgt = target(6, 0, 12, 270, base=base)  # 6 NM east: across 180°
    assert tgt.lon < 0
    e = encounter(own_k, tgt)
    assert e.distance_nm == pytest.approx(6.0, abs=0.01)
    assert e.bearing_deg == pytest.approx(90.0, abs=0.1)
    assert e.cpa_nm == pytest.approx(0.0, abs=CPA_TOL)
    assert e.tcpa_min == pytest.approx(20.0, abs=TCPA_TOL)  # 6 NM closing at 18 kn


def test_u_trf_13_equator():
    own_k = own(lat=-1 / 60, lon=0.0)  # 1 NM south of the equator, heading north at 6 kn
    tgt = Kinematics(1 / 60, 0.0, 6.0, 180.0, 0.0)  # 1 NM north, heading south
    e = encounter(own_k, tgt)
    assert e.cpa_nm == pytest.approx(0.0, abs=CPA_TOL)
    assert e.tcpa_min == pytest.approx(10.0, abs=TCPA_TOL)


def test_u_trf_13_antimeridian_dead_reckoning_wraps():
    k = Kinematics(0.0, 179.99, 6.0, 90.0, 0.0).dead_reckoned(600)  # 1 NM east
    assert -180.0 <= k.lon < -179.99


# --- U-TRF-15 dead reckoning (OD-16) ---------------------------------------------------------


def test_u_trf_15_dead_reckoning_moves_along_course():
    k = own(sog=6.0, cog=90.0).dead_reckoned(600)  # 10 min at 6 kn
    assert distance_nm(LAT0, LON0, k.lat, k.lon) == pytest.approx(1.0, rel=2e-3)
    assert k.at == 600
    assert own(sog=None).dead_reckoned(600).lat == LAT0  # no motion data: stays put


def test_u_trf_15_old_class_b_report_is_projected_to_now():
    """A target reported 3 min ago at 10 kn is 0.5 NM further along now."""
    tgt = Kinematics(*displace(LAT0, LON0, 0, 2), 10.0, 180.0, at=-180.0)  # report at t = −3 min
    e = encounter(own(sog=0.0), tgt, now=0.0)
    assert e.distance_nm == pytest.approx(1.5, abs=0.01)
    assert e.tcpa_min == pytest.approx(9.0, abs=TCPA_TOL)


# --- U-TRF-14 risk latch (OD-15) ----------------------------------------------------------


def test_u_trf_14_latch_holds_60_s_without_threat():
    clock = FakeClock()
    latch = RiskLatch(hold_s=60.0, clock=clock)
    assert latch.update({7}, {7: _enc(0.2, 5.0)}) is True
    clock.advance(1)
    # CPA wobbles above the threshold: not a threat now, but not passed either
    assert latch.update(set(), {7: _enc(0.55, 4.0)}) is True
    clock.advance(58)
    assert latch.update(set(), {7: _enc(0.55, 3.0)}) is True
    clock.advance(2)  # 60 s since the last threat
    assert latch.update(set(), {7: _enc(0.55, 2.9)}) is False


def test_u_trf_14_latch_clears_at_once_when_every_threat_has_passed():
    clock = FakeClock()
    latch = RiskLatch(clock=clock)
    latch.update({7, 8}, {7: _enc(0.2, 1.0), 8: _enc(0.3, 2.0)})
    clock.advance(1)
    # 7 passed, 8 still closing but out of threshold: hold
    assert latch.update(set(), {7: _enc(None, -0.1), 8: _enc(0.6, 1.0)}) is True
    clock.advance(1)
    assert latch.update(set(), {7: _enc(None, -0.2), 8: _enc(None, -0.1)}) is False


def test_u_trf_14_expired_target_holds_then_clears():
    clock = FakeClock()
    latch = RiskLatch(clock=clock)
    latch.update({7}, {7: _enc(0.2, 5.0)})
    clock.advance(10)
    assert latch.update(set(), {}) is True  # vanished: may be a missed report
    clock.advance(50)
    assert latch.update(set(), {}) is False


def test_u_trf_14_new_episode_after_clear():
    clock = FakeClock()
    latch = RiskLatch(clock=clock)
    assert latch.update(set(), {}) is False
    latch.update({1}, {1: _enc(0.1, 3.0)})
    clock.advance(1)
    latch.update(set(), {1: _enc(None, -0.1)})
    assert latch.active is False
    assert latch.update({2}, {2: _enc(0.1, 3.0)}) is True
    assert latch.active is True
