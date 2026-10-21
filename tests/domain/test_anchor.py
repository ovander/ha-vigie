"""Anchor watch — U-ANC-01…12 (TEST §3.7, SPEC §8.4, OD-21…OD-26).

Positions are built from metres so the expected values are exact by hand: a point d m due
north of the anchor is at Δlat = d / R rad, its haversine distance is d and its bearing to
the anchor 180°; d m due east is at Δlon = d / (R·cos φ) rad (bearing to the anchor 270°).
Defaults: radius 50 m, confirmation 20 s, position timeout 60 s.
"""

import math
import random

import pytest

from custom_components.vigie.anchor import (
    DRAG,
    NO_POSITION,
    AnchorStatus,
    AnchorWatch,
)
from custom_components.vigie.geo import EARTH_RADIUS_M
from tests.helpers import FakeClock

LAT0, LON0 = 43.5, 7.25
ANCHOR = (LAT0, LON0)


def north(d: float) -> tuple[float, float]:
    return LAT0 + math.degrees(d / EARTH_RADIUS_M), LON0


def east(d: float) -> tuple[float, float]:
    return LAT0, LON0 + math.degrees(d / (EARTH_RADIUS_M * math.cos(math.radians(LAT0))))


def at(bearing_deg: float, d: float) -> tuple[float, float]:
    """Point d m from the anchor on a bearing (local plane, good to mm at these ranges)."""
    b = math.radians(bearing_deg)
    dn, de = d * math.cos(b), d * math.sin(b)
    return (
        LAT0 + math.degrees(dn / EARTH_RADIUS_M),
        LON0 + math.degrees(de / (EARTH_RADIUS_M * math.cos(math.radians(LAT0)))),
    )


@pytest.fixture
def clock():
    return FakeClock()


@pytest.fixture
def watch(clock):
    w = AnchorWatch(clock=clock)
    w.arm(*ANCHOR)
    return w


def hold(watch: AnchorWatch, clock: FakeClock, position, seconds: int) -> AnchorStatus:
    """One update per second for `seconds` seconds; returns the last status."""
    status = watch.status
    for _ in range(seconds):
        clock.advance(1)
        status = watch.update(position)
    return status


# --- U-ANC-01: armed at own position -------------------------------------------------------


def test_u_anc_01_armed_at_own_position(clock):
    w = AnchorWatch(clock=clock)
    assert not w.armed
    w.arm(*ANCHOR, armed_at=1_790_000_000.0)
    assert (w.armed, w.anchor, w.radius_m, w.armed_at) == (True, ANCHOR, 50.0, 1_790_000_000.0)
    status = w.update(ANCHOR)
    assert status == AnchorStatus(
        armed=True,
        alarm=False,
        reason=None,
        distance_m=0.0,
        bearing_to_anchor=None,  # no bearing at the anchor itself
        max_distance_m=0.0,
        radius_m=50.0,
    )


# --- U-ANC-02: distance and bearing, by hand ------------------------------------------------


def test_u_anc_02_distance_and_bearing(watch):
    s = watch.update(north(60.0))
    assert s.distance_m == pytest.approx(60.0, abs=0.01)
    assert s.bearing_to_anchor == pytest.approx(180.0, abs=0.1)
    s = watch.update(east(30.0))
    assert s.distance_m == pytest.approx(30.0, abs=0.01)
    assert s.bearing_to_anchor == pytest.approx(270.0, abs=0.1)


# --- U-ANC-03: brief excursions do not raise the alarm ---------------------------------------


def test_u_anc_03_timer_restarts_inside(watch, clock):
    assert not hold(watch, clock, north(60), 19).alarm
    assert not hold(watch, clock, north(40), 1).alarm
    assert not hold(watch, clock, north(60), 19).alarm


# --- U-ANC-04: outside continuously for 20 s -------------------------------------------------


def test_u_anc_04_drag_after_confirmation(watch, clock):
    s = watch.update(north(60))  # outside from t = 0
    assert not s.alarm
    assert not hold(watch, clock, north(60), 19).alarm
    s = hold(watch, clock, north(60), 1)
    assert (s.alarm, s.reason) == (True, DRAG)


def test_u_anc_04_confirmation_configurable(clock):
    w = AnchorWatch(confirm_s=5, clock=clock)
    w.arm(*ANCHOR)
    w.update(north(60))
    assert not hold(w, clock, north(60), 4).alarm
    assert hold(w, clock, north(60), 1).reason == DRAG


# --- U-ANC-05: the drag alarm latches (OD-23) -------------------------------------------------


def test_u_anc_05_drag_alarm_latched(watch, clock):
    watch.update(north(60))
    hold(watch, clock, north(60), 20)
    s = hold(watch, clock, north(10), 30)  # back inside
    assert (s.alarm, s.reason) == (True, DRAG)

    watch.disarm()
    s = watch.update(north(10))
    assert (s.armed, s.alarm, s.reason) == (False, False, None)


def test_u_anc_05_re_drop_clears_and_resets(watch, clock):
    watch.update(north(60))
    hold(watch, clock, north(60), 20)
    assert watch.status.alarm
    watch.arm(*north(60))  # re-dropped where the boat now lies
    s = watch.update(north(60))
    assert (s.alarm, s.distance_m, s.max_distance_m) == (False, 0.0, 0.0)
    assert watch.anchor == north(60)


# --- U-ANC-06: radius changed while armed ----------------------------------------------------


def test_u_anc_06_radius_change(watch, clock):
    watch.update(north(60))
    hold(watch, clock, north(60), 10)
    watch.set_radius(80)
    s = hold(watch, clock, north(60), 30)
    assert (s.alarm, s.radius_m) == (False, 80.0)  # inside again

    watch.set_radius(40)  # the timer starts from the change
    assert not hold(watch, clock, north(60), 20).alarm
    assert hold(watch, clock, north(60), 1).reason == DRAG

    watch.set_radius(200)  # a latched alarm is not cleared by a radius change
    assert hold(watch, clock, north(60), 1).reason == DRAG


def test_u_anc_06_shrinking_while_outside_restarts_the_timer(watch, clock):
    watch.update(north(60))
    hold(watch, clock, north(60), 15)
    watch.set_radius(45)
    assert not hold(watch, clock, north(60), 20).alarm
    assert hold(watch, clock, north(60), 1).alarm


# --- U-ANC-07: position lost while armed (OD-24) ---------------------------------------------


def test_u_anc_07_no_position_alarm_and_recovery_inside(watch, clock):
    watch.update(north(10))
    assert not hold(watch, clock, None, 59).alarm
    s = hold(watch, clock, None, 1)
    assert (s.alarm, s.reason, s.distance_m) == (True, NO_POSITION, None)
    s = hold(watch, clock, north(10), 1)
    assert (s.alarm, s.reason) == (False, None)  # cleared by itself


def test_u_anc_07_no_position_counts_from_the_fix_time(watch, clock):
    """A position passed again with its old fix time does not reset the timer."""
    fix_at = clock()
    for _ in range(60):
        clock.advance(1)
        s = watch.update(north(10), fix_at=fix_at)
    assert s.reason == NO_POSITION


def test_u_anc_07_position_returns_outside(watch, clock):
    hold(watch, clock, None, 60)
    s = hold(watch, clock, north(60), 1)
    assert (s.alarm, s.reason) == (True, NO_POSITION)  # no silent gap
    assert hold(watch, clock, north(60), 19).reason == NO_POSITION
    s = hold(watch, clock, north(60), 1)  # 20 s outside since the position returned
    assert s.reason == DRAG
    assert hold(watch, clock, north(10), 5).reason == DRAG  # now latched


def test_u_anc_07_timer_starts_at_arming(clock):
    w = AnchorWatch(position_timeout_s=10, clock=clock)
    w.arm(*ANCHOR)
    assert not hold(w, clock, None, 9).alarm
    assert hold(w, clock, None, 1).reason == NO_POSITION


# --- U-ANC-08: disarmed ----------------------------------------------------------------------


def test_u_anc_08_disarmed_does_nothing(clock):
    w = AnchorWatch(clock=clock)
    s = hold(w, clock, north(600), 120)
    assert s == AnchorStatus(False, False, None, None, None, None, 50.0)
    assert hold(w, clock, None, 120).alarm is False
    assert w.anchor is None


# --- U-ANC-09: maximum distance ---------------------------------------------------------------


def test_u_anc_09_max_distance(watch, clock):
    for d in (20, 45, 30):
        s = hold(watch, clock, north(d), 1)
    assert s.max_distance_m == pytest.approx(45.0, abs=0.01)
    assert s.distance_m == pytest.approx(30.0, abs=0.01)
    watch.arm(*ANCHOR)
    assert watch.update(north(5)).max_distance_m == pytest.approx(5.0, abs=0.01)


# --- U-ANC-10: snapshot for restore (OD-26) ---------------------------------------------------


def test_u_anc_10_snapshot_round_trip(watch, clock):
    watch.arm(*ANCHOR, radius_m=30, armed_at=1_790_000_000.0)
    watch.update(north(60))
    hold(watch, clock, north(60), 20)
    data = watch.to_dict()
    assert data == {
        "latitude": LAT0,
        "longitude": LON0,
        "radius_m": 30.0,
        "armed_at": 1_790_000_000.0,
        "max_distance_m": pytest.approx(60.0, abs=0.01),
        "alarm": DRAG,
    }

    restart = FakeClock(start=5.0)  # monotonic time starts again after a restart
    w = AnchorWatch(clock=restart)
    w.restore(data)
    assert (w.armed, w.anchor, w.radius_m, w.armed_at) == (True, ANCHOR, 30.0, 1_790_000_000.0)
    s = w.update(north(10))
    assert (s.alarm, s.reason, s.max_distance_m) == (True, DRAG, pytest.approx(60.0, abs=0.01))

    # The position-loss timer starts from the restore time
    w2 = AnchorWatch(clock=restart)
    w2.restore({**data, "alarm": None})
    assert not hold(w2, restart, None, 59).alarm
    assert hold(w2, restart, None, 1).reason == NO_POSITION


def test_u_anc_10_disarmed_and_no_position_snapshots(clock):
    w = AnchorWatch(clock=clock)
    assert w.to_dict() is None
    w.restore(None)
    assert not w.armed

    w.arm(*ANCHOR)
    hold(w, clock, None, 60)
    assert w.to_dict()["alarm"] is None  # only a drag alarm is kept; position loss re-times


@pytest.mark.parametrize(
    "data",
    [
        {"latitude": 91.0, "longitude": 0.0, "radius_m": 50.0},
        {"latitude": 0.0, "longitude": 0.0, "radius_m": 5.0},
        {"longitude": 0.0, "radius_m": 50.0},
        {"latitude": "x", "longitude": 0.0, "radius_m": 50.0},
        {"latitude": 0.0, "longitude": 0.0, "radius_m": 50.0, "alarm": "fire"},
    ],
)
def test_u_anc_10_bad_snapshot_refused(clock, data):
    w = AnchorWatch(clock=clock)
    with pytest.raises(ValueError):
        w.restore(data)
    assert not w.armed


# --- U-ANC-11: invalid inputs -----------------------------------------------------------------


@pytest.mark.parametrize(
    ("lat", "lon", "radius"),
    [
        (None, None, None),  # no own position and no coordinates
        (LAT0, None, None),
        (None, LON0, None),
        (90.5, LON0, None),
        (LAT0, 180.5, None),
        (math.nan, LON0, None),
        (LAT0, LON0, 9.9),
        (LAT0, LON0, 500.1),
    ],
)
def test_u_anc_11_invalid_arm_refused(watch, lat, lon, radius):
    before = (watch.armed, watch.anchor, watch.radius_m)
    with pytest.raises(ValueError):
        watch.arm(lat, lon, radius_m=radius)
    assert (watch.armed, watch.anchor, watch.radius_m) == before


@pytest.mark.parametrize("radius", [9.9, 500.1, math.nan])
def test_u_anc_11_invalid_radius_refused(watch, radius):
    with pytest.raises(ValueError):
        watch.set_radius(radius)
    assert watch.radius_m == 50.0


def test_u_anc_11_invalid_settings_refused(clock):
    with pytest.raises(ValueError):
        AnchorWatch(radius_m=5, clock=clock)
    with pytest.raises(ValueError):
        AnchorWatch(confirm_s=0, clock=clock)
    with pytest.raises(ValueError):
        AnchorWatch(position_timeout_s=-1, clock=clock)


def test_u_anc_11_radius_set_while_disarmed_is_used_at_arming(clock):
    w = AnchorWatch(clock=clock)
    w.set_radius(120)
    w.arm(*ANCHOR)
    assert w.radius_m == 120.0
    w.arm(*ANCHOR, radius_m=35)
    assert w.radius_m == 35.0


# --- U-ANC-12: swinging with GPS noise --------------------------------------------------------


def test_u_anc_12_swinging_with_noise_no_alarm(watch, clock):
    rng = random.Random(12)
    max_seen = 0.0
    for t in range(600):
        lat, lon = at(t * 0.6 % 360, 30.0)  # one turn every 10 min
        lat += math.degrees(rng.uniform(-8, 8) / EARTH_RADIUS_M)
        lon += math.degrees(rng.uniform(-8, 8) / (EARTH_RADIUS_M * math.cos(math.radians(LAT0))))
        clock.advance(1)
        s = watch.update((lat, lon))
        assert not s.alarm, t
        max_seen = max(max_seen, s.distance_m)
    assert s.max_distance_m == pytest.approx(max_seen)
    assert s.max_distance_m < 50.0
