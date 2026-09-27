"""geo.py — distance and bearing (SPEC §8.1 helpers, used in P1 for target ordering)."""

import pytest

from custom_components.vigie.geo import METRES_PER_NM, bearing_deg, distance_m, distance_nm


def test_one_arc_minute_of_latitude_is_about_one_nautical_mile():
    # Mean-radius sphere: one arc-minute is 1853.2 m, 0.07 % above the 1852 m definition
    assert distance_nm(43.0, 7.0, 43.0 + 1 / 60, 7.0) == pytest.approx(1.0, rel=1e-3)


def test_distance_units_consistent():
    assert distance_m(43.5, 7.0, 43.6, 7.1) == pytest.approx(
        distance_nm(43.5, 7.0, 43.6, 7.1) * METRES_PER_NM
    )


def test_zero_distance():
    assert distance_m(43.5, 7.25, 43.5, 7.25) == 0.0


def test_distance_across_antimeridian_is_short():
    # 0.2° of longitude on the equator ≈ 12 NM, not ≈ 21 600 NM the long way round
    assert distance_nm(0.0, 179.9, 0.0, -179.9) == pytest.approx(12.0, rel=2e-3)


@pytest.mark.parametrize(
    "lat2,lon2,expected",
    [(1.0, 0.0, 0.0), (0.0, 1.0, 90.0), (-1.0, 0.0, 180.0), (0.0, -1.0, 270.0)],
)
def test_bearing_cardinal_points(lat2, lon2, expected):
    assert bearing_deg(0.0, 0.0, lat2, lon2) == pytest.approx(expected, abs=1e-9)


def test_bearing_range_and_antimeridian():
    b = bearing_deg(0.0, 179.9, 0.0, -179.9)
    assert 0.0 <= b < 360.0
    assert b == pytest.approx(90.0, abs=1e-6)
