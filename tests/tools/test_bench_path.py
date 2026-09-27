"""E-1 bench path end to end, without Home Assistant (TEST §5.1, SPEC OD-12).

A generated D-07 scenario is replayed into the tool's own pseudo-terminal and read by the
real hub through `serial_transport` (pyserial-asyncio-fast), as on the bench.
"""

import asyncio
import threading

import pytest

from custom_components.vigie.hub import Hub, serial_transport
from custom_components.vigie.nmea.parsers import Rmc
from tests.tools import replay, scenario


@pytest.mark.asyncio
async def test_scenario_replayed_to_pty_reaches_the_hub(tmp_path):
    lines = scenario.generate(scenario.PRESETS["head-on"])  # 901 RMC + 91 VDM
    link = tmp_path / "ttyAIS"
    master, slave = replay.open_pty(link)
    gps, ais = [], []
    hub = Hub(
        serial_transport(str(link), 38400),
        on_gps=gps.append,
        on_ais=ais.append,
        on_connection=lambda connected: None,
    )
    try:
        await hub.connect()
        reader = asyncio.create_task(hub.run())
        timed = replay.parse_lines(scenario.format_timed(lines))
        writer = threading.Thread(
            target=replay.run,
            args=(
                replay.schedule(timed, speed=10_000.0),
                lambda data: replay.os.write(master, data),
            ),
        )
        writer.start()
        await asyncio.to_thread(writer.join)
        for _ in range(200):  # let the reader drain the pseudo-terminal
            if len(gps) + len(ais) == len(lines):
                break
            await asyncio.sleep(0.01)
        reader.cancel()
        with pytest.raises(asyncio.CancelledError):
            await reader
    finally:
        await hub.close()
        replay.close_pty(link, master, slave)
    assert len(gps) == 901 and all(isinstance(r, Rmc) and r.valid for r in gps)
    assert len(ais) == 91 and {p.mmsi for p in ais} == {235000001}
    assert hub.stats.checksum_errors == hub.stats.framing_errors == 0
