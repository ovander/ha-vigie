"""D-07 scenario generator (TEST §2, §6). Output is checked with Vigie's own decoders."""

import json

import pytest

from custom_components.vigie.geo import bearing_deg, distance_nm
from custom_components.vigie.nmea.ais_decoder import AisDecoder, VesselStatic
from custom_components.vigie.nmea.parsers import GpsParser, Rmc
from custom_components.vigie.traffic import Kinematics, TargetReport, ThreatSettings, assess
from tests.tools import scenario
from tests.tools.scenario import PRESETS, Scenario, Target, Track, generate, relative


def _decode(lines, statics=None):
    """Own RMCs and target positions; static records go to `statics` when given."""
    gps, ais = GpsParser(), AisDecoder()
    own, targets = [], []
    for t, sentence in lines:
        if sentence.startswith("$"):
            rec = gps.feed(sentence)
            assert isinstance(rec, Rmc), sentence
            own.append((t, rec))
            continue
        rec = ais.feed(sentence)
        count, index = sentence.split(",")[1:3]
        if rec is None:
            assert index != count, sentence  # only a first fragment yields nothing
        elif isinstance(rec, VesselStatic):
            assert statics is not None, sentence
            statics.append((t, rec))
        else:
            targets.append((t, rec))
    assert gps.stats["rejected"] == 0 and ais.stats["rejected"] == 0
    return own, targets


def test_relative_position():
    lat, lon = relative(43.5, 7.25, east_nm=1.0, north_nm=2.0)
    assert distance_nm(43.5, 7.25, lat, lon) == pytest.approx(5**0.5, rel=2e-3)
    assert bearing_deg(43.5, 7.25, lat, lon) == pytest.approx(26.57, abs=0.1)


def test_track_moves_along_course():
    track = Track(43.5, 7.25, sog_kn=6.0, cog_deg=90.0)
    lat, lon = track.at(600)  # 10 min at 6 kn = 1 NM east
    assert distance_nm(43.5, 7.25, lat, lon) == pytest.approx(1.0, rel=2e-3)
    assert bearing_deg(43.5, 7.25, lat, lon) == pytest.approx(90.0, abs=0.1)


def test_head_on_preset_matches_u_trf_01():
    s = PRESETS["head-on"]
    lines = generate(s)
    own, targets = _decode(lines)
    assert len(own) == s.duration_s + 1  # 1 Hz, both ends included
    assert all(r.valid and r.sog_knots == pytest.approx(6.0) for _, r in own)
    # Start: target 2 NM north of own; after 10 min (TCPA) they meet
    t0, first = targets[0]
    assert first.mmsi == s.targets[0].mmsi
    assert distance_nm(
        own[0][1].latitude, own[0][1].longitude, first.latitude, first.longitude
    ) == (pytest.approx(2.0, abs=0.01))
    at_tcpa = [p for t, p in targets if t - t0 == pytest.approx(600)]
    own_at_tcpa = [r for t, r in own if t - own[0][0] == pytest.approx(600)]
    assert at_tcpa and own_at_tcpa
    gap = distance_nm(
        own_at_tcpa[0].latitude, own_at_tcpa[0].longitude, at_tcpa[0].latitude, at_tcpa[0].longitude
    )
    assert gap == pytest.approx(0.0, abs=0.01)


def test_crossing_preset_matches_u_trf_03():
    s = PRESETS["crossing"]
    target = s.targets[0]
    assert (target.track.sog_kn, target.track.cog_deg) == (12.0, 270.0)
    _, targets = _decode(generate(s))
    assert targets[0][1].cog_deg == pytest.approx(270.0)
    assert targets[0][1].sog_knots == pytest.approx(12.0)


def test_class_b_target_and_report_interval():
    own = Track(43.5, 7.25, 5.0, 0.0)
    lat, lon = relative(43.5, 7.25, 0.5, 0.5)
    s = Scenario(
        own=own,
        targets=(Target(367000123, Track(lat, lon, 4.0, 45.0), ais_class="B", interval_s=30.0),),
        duration_s=90,
    )
    _, targets = _decode(generate(s))
    assert [p.msg_type for _, p in targets] == [18, 18, 18, 18]  # t = 0, 30, 60, 90
    assert all(p.ais_class == "B" and p.mmsi == 367000123 for _, p in targets)


def test_lines_sorted_and_timed_format(tmp_path):
    lines = generate(PRESETS["crossing"])
    stamps = [t for t, _ in lines]
    assert stamps == sorted(stamps)
    text = scenario.format_timed(lines)
    first = text.splitlines()[0]
    stamp, sentence = first.split(" ", 1)
    assert float(stamp) == pytest.approx(PRESETS["crossing"].start_epoch)
    assert sentence.startswith("$GPRMC")
    assert text.endswith("\r\n")


def test_json_scenario_and_cli(tmp_path):
    spec = {
        "own": {"lat": 43.5, "lon": 7.25, "sog": 6.0, "cog": 0.0},
        "duration_s": 20,
        "targets": [
            {"mmsi": 235000042, "east_nm": 1.0, "north_nm": 0.0, "sog": 6.0, "cog": 270.0},
            {
                "mmsi": 367000042,
                "class": "B",
                "east_nm": -1.0,
                "north_nm": 1.0,
                "sog": 0.0,
                "cog": 0.0,
                "interval_s": 10,
                "nav_status": 1,
            },
        ],
    }
    path = tmp_path / "s.json"
    path.write_text(json.dumps(spec))
    out = tmp_path / "out.nmea"
    assert scenario.main([str(path), "-o", str(out)]) == 0
    _, targets = _decode(
        (float(line.split(" ", 1)[0]), line.split(" ", 1)[1])
        for line in out.read_text().splitlines()
    )
    assert {p.mmsi for _, p in targets} == {235000042, 367000042}


def test_cli_preset_to_stdout(capsys):
    assert scenario.main(["--preset", "head-on", "--duration", "5"]) == 0
    assert len(capsys.readouterr().out.splitlines()) == 6 + 1  # 6 RMC + 1 VDM at t=0


# --- E-02 bench presets: one per TEST §3.4 geometry ------------------------------------------

NEG = "negative"
# preset → {target index: (CPA NM, TCPA min, threat)}, hand values of TEST §3.4
E02_EXPECTED = {
    "head-on": {0: (0.00, 10.0, True)},  # U-TRF-01
    "clear-crossing": {0: (0.71, 5.0, False)},  # U-TRF-02
    "crossing": {0: (0.45, 4.0, True)},  # U-TRF-03
    "overtaking": {0: (0.00, 30.0, False)},  # U-TRF-04
    "not-urgent": {0: (0.26, 21.6, False)},  # U-TRF-05
    "diverging": {0: (None, NEG, False)},  # U-TRF-06
    "parallel": {0: (0.30, None, False)},  # U-TRF-07
    "anchored": {0: (0.00, 4.0, False)},  # U-TRF-08, excluded by default
    # U-TRF-11: head-on, crossing, anchored, overtaking together
    "multi-target": {
        0: (0.00, 10.0, True),
        1: (0.45, 4.0, True),
        2: (0.00, 4.0, False),
        3: (0.00, 30.0, False),
    },
}


def _first_picture(s: Scenario, after_s: float = 0.0):
    """Traffic picture from the first own RMC and each target's first report, as decoded,
    dead-reckoned `after_s` seconds on."""
    own, targets = _decode(generate(s), [])
    t0, rmc = own[0]
    own_k = Kinematics(rmc.latitude, rmc.longitude, rmc.sog_knots, rmc.cog_deg, t0)
    reports = {}
    for t, p in targets:
        reports.setdefault(
            p.mmsi,
            TargetReport(
                p.mmsi, Kinematics(p.latitude, p.longitude, p.sog_knots, p.cog_deg, t), p.nav_status
            ),
        )
    return assess(own_k, reports.values(), ThreatSettings(), t0 + after_s)


def test_e_02_every_u_trf_geometry_has_a_preset():
    assert set(E02_EXPECTED) == set(PRESETS) - {"named-traffic"}  # P3 bench, not a U-TRF case
    assert set(scenario.PRESET_REFERENCE) == set(PRESETS)


@pytest.mark.parametrize("name", sorted(E02_EXPECTED))
def test_e_02_preset_matches_u_trf_hand_values(name):
    """Decoded like the receiver's stream, each preset gives the TEST §3.4 CPA/TCPA/threat."""
    s = PRESETS[name]
    picture = _first_picture(s)
    for index, (cpa, tcpa, threat) in E02_EXPECTED[name].items():
        mmsi = s.targets[index].mmsi
        e = picture.encounters[mmsi]
        if cpa is None:
            assert e.cpa_nm is None, (name, mmsi)
        else:
            assert e.cpa_nm == pytest.approx(cpa, abs=0.01), (name, mmsi)
        if tcpa is None:
            assert e.tcpa_min is None, (name, mmsi)
        elif tcpa == NEG:
            assert e.tcpa_min is not None and e.tcpa_min < 0, (name, mmsi)
        else:
            assert e.tcpa_min == pytest.approx(tcpa, abs=0.1), (name, mmsi)
        assert (mmsi in picture.threats) is threat, (name, mmsi)
    # Each preset runs past every target's TCPA, so each alert also clears
    tcpas = [v[1] for v in E02_EXPECTED[name].values() if isinstance(v[1], float)]
    assert s.duration_s > max(tcpas, default=0) * 60


def test_e_02_multi_target_closest_threat_is_the_crossing():
    """U-TRF-11 on the bench: smallest TCPA wins; the anchored target is excluded."""
    s = PRESETS["multi-target"]
    assert len({t.mmsi for t in s.targets}) == len(s.targets)
    picture = _first_picture(s)
    assert picture.closest_threat is not None
    assert picture.closest_threat[0] == s.targets[1].mmsi
    assert s.targets[2].nav_status == 1  # at anchor
    later = _first_picture(s, after_s=300)  # crossing passed at 4 min: head-on takes over
    assert later.closest_threat is not None
    assert later.closest_threat[0] == s.targets[0].mmsi


def test_cli_list_presets(capsys):
    assert scenario.main(["--list"]) == 0
    out = capsys.readouterr().out
    for name in PRESETS:
        assert name in out
    assert "U-TRF-05" in out


# --- Static data (P3): type 5 for Class A, type 24 parts A and B for Class B -----------------

NAMED = PRESETS["named-traffic"]


def _statics(s: Scenario):
    statics = []
    _decode(generate(s), statics)
    return statics


def test_named_traffic_static_reports():
    by_mmsi = {}
    for t, rec in _statics(NAMED):
        by_mmsi.setdefault(rec.mmsi, []).append((t - NAMED.start_epoch, rec))
    cargo, yacht, tender, unnamed = (t.mmsi for t in NAMED.targets)
    assert unnamed not in by_mmsi  # no static data given: none sent

    # Class A: type 5 at 30 s, then every 6 min
    reports = by_mmsi[cargo]
    assert [round(t) for t, _ in reports] == [30, 390, 750, 1110]
    s = reports[0][1]
    assert (s.msg_type, s.name, s.ship_type, s.callsign, s.imo) == (
        5,
        "CARGO ONE",
        70,
        "ABCD",
        9123456,
    )
    assert (s.length_m, s.beam_m, s.draught_m, s.destination) == (180, 30, 8.5, "MARSEILLE")

    # Class B: type 24 part A and part B each time
    parts = [(round(t), r.msg_type, r.part) for t, r in by_mmsi[yacht]]
    assert parts[:2] == [(30, 24, "A"), (30, 24, "B")]
    names = {r.name for _, r in by_mmsi[yacht] if r.part == "A"}
    part_b = next(r for _, r in by_mmsi[yacht] if r.part == "B")
    assert names == {"ALBATROS"}
    assert (part_b.ship_type, part_b.callsign, part_b.length_m) == (36, "FAB1234", 12)

    # Auxiliary craft: mothership MMSI instead of dimensions
    tender_b = next(r for _, r in by_mmsi[tender] if r.part == "B")
    assert (tender_b.mothership_mmsi, tender_b.length_m) == (yacht, None)


def test_named_traffic_positions_first_names_later():
    """Names arrive 30 s after the first positions, as with a real receiver."""
    _, targets = _decode(generate(NAMED), [])
    first_position = min(t for t, _ in targets) - NAMED.start_epoch
    first_static = min(t for t, _ in _statics(NAMED)) - NAMED.start_epoch
    assert first_position < 1 and first_static == pytest.approx(30, abs=0.01)


def test_named_traffic_cargo_becomes_a_threat():
    """The Class A cargo ship crosses ahead: CPA 0.45 NM, TCPA 16 min at the start."""
    picture = _first_picture(NAMED)
    e = picture.encounters[NAMED.targets[0].mmsi]
    assert e.cpa_nm == pytest.approx(0.45, abs=0.01)
    assert e.tcpa_min == pytest.approx(16.0, abs=0.1)
    assert NAMED.targets[0].mmsi not in picture.threats  # not yet: TCPA > 15 min
    later = _first_picture(NAMED, after_s=120)
    assert NAMED.targets[0].mmsi in later.threats


def test_json_scenario_with_static_data(tmp_path):
    spec = {
        "own": {"lat": 43.5, "lon": 7.25, "sog": 6.0, "cog": 0.0},
        "duration_s": 60,
        "targets": [
            {
                "mmsi": 235000021,
                "east_nm": 1.0,
                "north_nm": 1.0,
                "sog": 5.0,
                "cog": 270.0,
                "name": "MOANA",
                "ship_type": 37,
                "callsign": "F1234",
                "dimensions": [9, 3, 2, 2],
                "static_offset_s": 0,
            },
            {
                "mmsi": 235000022,
                "class": "B",
                "east_nm": -1.0,
                "north_nm": 1.0,
                "sog": 4.0,
                "cog": 90.0,
                "name": "LUTIN",
                "ship_type": 36,
                "static_offset_s": 10,
            },
        ],
    }
    path = tmp_path / "s.json"
    path.write_text(json.dumps(spec))
    loaded = scenario.load(path)
    assert loaded.targets[0].dimensions == (9, 3, 2, 2)
    statics = _statics(loaded)
    first = {rec.mmsi: rec for _, rec in reversed(statics)}
    assert (first[235000021].msg_type, first[235000021].name, first[235000021].length_m) == (
        5,
        "MOANA",
        12,
    )
    assert first[235000022].msg_type == 24 and first[235000022].name == "LUTIN"


def test_presets_for_e02_send_no_static_data():
    for name, preset in PRESETS.items():
        if name != "named-traffic":
            assert _statics(preset) == [], name
