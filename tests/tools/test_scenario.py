"""D-07 scenario generator (TEST §2, §6). Output is checked with Vigie's own decoders."""

import json

import pytest

from custom_components.vigie.geo import bearing_deg, distance_nm
from custom_components.vigie.nmea.ais_decoder import AisDecoder
from custom_components.vigie.nmea.parsers import GpsParser, Rmc
from tests.tools import scenario
from tests.tools.scenario import PRESETS, Scenario, Target, Track, generate, relative


def _decode(lines):
    gps, ais = GpsParser(), AisDecoder()
    own, targets = [], []
    for t, sentence in lines:
        if sentence.startswith("$"):
            rec = gps.feed(sentence)
            assert isinstance(rec, Rmc), sentence
            own.append((t, rec))
        else:
            pos = ais.feed(sentence)
            assert pos is not None, sentence
            targets.append((t, pos))
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
