"""Load and recorder — F-PERF-01…03 (TEST §4.5, SPEC §10.2, NFR-04, NFR-09).

Marked `perf`: excluded from the PR gate and run nightly (TEST §7). Time is simulated
(freezer); only F-PERF-01 measures real processing time on the runner.
"""

import json
import time
from collections import defaultdict
from itertools import pairwise
from pathlib import Path

import pytest
from freezegun.api import FrozenDateTimeFactory
from homeassistant.core import HomeAssistant

from tests.helpers import BY_ID_PORT, FakePorts, nmea
from tests.integration.common import entity_id, make_entry, setup, tick

pytestmark = pytest.mark.perf

BURST = Path(__file__).parent.parent / "fixtures" / "burst_60s.nmea"


def _burst_by_second() -> list[list[str]]:
    """D-08 lines grouped by whole second of their timestamp."""
    seconds: dict[int, list[str]] = defaultdict(list)
    for raw in BURST.read_text().splitlines():
        stamp, sentence = raw.split(" ", 1)
        seconds[int(float(stamp))].append(sentence)
    return [seconds[k] for k in sorted(seconds)]


async def test_f_perf_01_burst_processed_without_backlog(
    hass: HomeAssistant, fake_ports: FakePorts, freezer: FrozenDateTimeFactory
):
    entry = make_entry(hass)
    await setup(hass, entry)
    hub = entry.runtime_data.hub
    fed = 0
    worst = 0.0
    for batch in _burst_by_second():
        assert len(batch) >= 50
        start = time.perf_counter()
        fake_ports[BY_ID_PORT].feed_lines(*batch)
        await hass.async_block_till_done()
        worst = max(worst, time.perf_counter() - start)
        fed += len(batch)
        assert hub.stats.lines == fed  # no backlog: every line handled within its second
        await tick(hass, freezer)
    assert hub.stats.ais_ok == 3000 and hub.stats.gps_ok == 60
    # Handling one second of burst blocks the loop far less than 100 ms (NFR-09)
    assert worst < 0.1, f"worst batch took {worst * 1000:.1f} ms"


async def test_f_perf_02_writes_per_entity_at_most_one_per_second(
    hass: HomeAssistant, fake_ports: FakePorts, freezer: FrozenDateTimeFactory, record_property
):
    entry = make_entry(hass)
    await setup(hass, entry)
    writes: dict[str, list[float]] = defaultdict(list)
    hass.bus.async_listen(
        "state_changed",
        lambda e: writes[e.data["entity_id"]].append(e.time_fired.timestamp()),
    )
    batches = _burst_by_second()
    for second in range(600):  # 10 min of synthetic traffic at real rate (D-06 stand-in, #2)
        sog = 5.0 + (second % 30) / 10  # SOG drifts 0.1 kn per second
        cog = (90 + second * 0.7) % 360
        fake_ports[BY_ID_PORT].feed_lines(
            nmea(
                f"GPRMC,0800{second % 60:02d},A,4330.000,N,00715.000,E,{sog:.1f},{cog:.1f},270926,,"
            ),
            *batches[second % 60][1:],
        )
        await tick(hass, freezer)
    for eid, stamps in writes.items():
        gaps = [b - a for a, b in pairwise(stamps)]
        assert all(g >= 1.0 - 1e-6 for g in gaps), f"{eid} wrote twice within 1 s"
        assert len(stamps) <= 601, eid
    total = sum(len(s) for s in writes.values())
    record_property("state_writes_10_min", total)  # baseline, re-recorded on D-06 (#2)
    record_property("writes_per_entity", {k: len(v) for k, v in writes.items()})


async def test_f_perf_03_targets_attribute_rebuilt_at_most_every_5_s(
    hass: HomeAssistant, fake_ports: FakePorts, freezer: FrozenDateTimeFactory
):
    entry = make_entry(hass)
    await setup(hass, entry)
    eid = entity_id(hass, entry, "ais_targets")
    rebuilds: list[float] = []
    last: list[object] = [None]

    def on_change(event):
        if event.data["entity_id"] != eid or event.data["new_state"] is None:
            return
        targets = event.data["new_state"].attributes.get("targets")
        if targets != last[0]:
            last[0] = targets
            rebuilds.append(event.time_fired.timestamp())

    hass.bus.async_listen("state_changed", on_change)
    for batch in _burst_by_second()[:30]:
        fake_ports[BY_ID_PORT].feed_lines(*batch)
        await tick(hass, freezer)
    st = hass.states.get(eid)
    assert int(st.state) == 80  # every synthetic MMSI heard
    targets = st.attributes["targets"]
    assert len(targets) == 50  # capped at the 50 nearest
    size = len(json.dumps(dict(st.attributes)).encode())
    assert size < 16 * 1024, f"attributes {size} bytes"  # recorder attribute limit
    gaps = [b - a for a, b in pairwise(rebuilds[1:])]
    assert gaps and all(g >= 5.0 - 1e-6 for g in gaps)
