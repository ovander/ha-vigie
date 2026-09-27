"""Transport hub — F-HUB-01…05 at hub level (TEST §4.2), SPEC §6, §7.1, §10.3.

These run against hub.py directly with the fake transport, an injected clock and an
injected sleep: no Home Assistant, no real serial port, no real waiting. The entity half of
F-HUB-03 is checked in the HA harness (WP5).
"""

import asyncio
import contextlib
import logging
from pathlib import Path

import pytest

from custom_components.vigie.hub import (
    RAW_LINE_LIMIT,
    Hub,
    HubConnectionError,
    ProbeResult,
    backoff_delays,
    probe,
    serial_transport,
)
from custom_components.vigie.nmea.parsers import Gga, Gsa, Hdt, Rmc, Vtg
from tests.helpers import FakeClock, FakeSerial, nmea, settle

pytestmark = pytest.mark.asyncio

FIXTURES = Path(__file__).parent.parent / "fixtures"

# Public reference AIS sentences (gpsd AIVDM document and common corpora), as in the P0 tests
AIS_TYPE1 = "!AIVDM,1,1,,B,177KQJ5000G?tO`K>RA1wUbN0TKH,0*5C"
AIS_TYPE18 = "!AIVDM,1,1,,A,B5NJ;PP005l4ot5Isbl03wsUkP06,0*76"
AIS_TYPE19 = "!AIVDM,1,1,,B,C5N3SRgPEnJGEBT>NhWAwwo862PaLELTBJ:V00000000S0D:R220,0*0B"
AIS_VDO = nmea("AIVDO,1,1,,B,177KQJ5000G?tO`K>RA1wUbN0TKH,0", "!")

RMC = nmea("GPRMC,081502,A,4330.000,N,00715.500,E,5.2,271.0,270926,,")
GGA = nmea("GPGGA,081502,4330.000,N,00715.500,E,1,08,0.9,5.0,M,48.0,M,,")
VTG = nmea("GPVTG,271.0,T,,M,5.2,N,9.6,K,A")
HDT = nmea("HEHDT,272.5,T")
GSA = nmea("GPGSA,A,3,04,05,,09,12,,,24,,,,,2.5,1.3,2.1")

LOGGER = "custom_components.vigie.hub"


class Recorder:
    def __init__(self) -> None:
        self.gps: list[object] = []
        self.ais: list[object] = []
        self.conn: list[bool] = []


def make_hub(fake, clock=None, sleep=None, **kwargs):
    rec = Recorder()
    hub = Hub(
        fake,
        on_gps=rec.gps.append,
        on_ais=rec.ais.append,
        on_connection=rec.conn.append,
        clock=clock or FakeClock(),
        sleep=sleep or asyncio.sleep,
        **kwargs,
    )
    return hub, rec


async def start(hub):
    await hub.connect()
    task = asyncio.create_task(hub.run())
    await settle()
    return task


async def stop(hub, task):
    task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await task
    await hub.close()


# --- F-HUB-01 routing ------------------------------------------------------

AIS_TYPE5 = (  # gpsd AIVDM document, two fragments
    "!AIVDM,2,1,3,B,55P5TL01VIaAL@7WKO@mBplU@<PDhh000000001S;AJ::4A80?4i@E53,0*3E",
    "!AIVDM,2,2,3,B,1@0000000000000,2*55",
)


async def test_f_hub_01_static_reports_not_delivered_as_positions():
    """Until WP12 routes them, decoded static reports count as ignored (as type 5 did)."""
    fake = FakeSerial()
    hub, rec = make_hub(fake)
    task = await start(hub)
    fake.feed_lines(*AIS_TYPE5, AIS_TYPE1)
    await settle()
    assert [p.msg_type for p in rec.ais] == [1]
    s = hub.stats
    assert (s.lines, s.ais_ok, s.ignored, s.ais_rejected) == (3, 1, 2, 0)
    await stop(hub, task)


async def test_f_hub_01_mixed_stream_routed():
    fake, clock = FakeSerial(), FakeClock()
    hub, rec = make_hub(fake, clock)
    task = await start(hub)
    fake.feed_lines(
        RMC,
        GGA,
        AIS_TYPE1,
        VTG,
        "\\s:rcv1,c:1700000000*00\\" + AIS_TYPE18,  # tag block stripped, re-routed
        HDT,
        AIS_TYPE19,
        "\\s:rcv1*00\\" + GSA,
        nmea("PGRME,15.0,M,45.0,M,25.0,M"),  # proprietary: ignored
        nmea("GPGSV,1,1,01,03,03,111,00"),  # unsupported: ignored
        "hello",  # not a sentence: ignored
        "",  # blank line: skipped silently
    )
    await settle()
    assert [type(r) for r in rec.gps] == [Rmc, Gga, Vtg, Hdt, Gsa]
    assert [p.msg_type for p in rec.ais] == [1, 18, 19]
    assert rec.ais[0].mmsi == 477553000
    s = hub.stats
    assert (s.lines, s.gps_ok, s.ais_ok, s.ignored) == (11, 5, 3, 3)
    assert (s.checksum_errors, s.framing_errors, s.ais_rejected, s.gps_rejected) == (0, 0, 0, 0)
    assert s.sentences_per_min(clock()) == 10  # "hello" is not a sentence
    assert s.last_sentence_at == clock()
    clock.advance(60.1)
    assert s.sentences_per_min(clock()) == 0
    await stop(hub, task)


@pytest.mark.parametrize("include_own,expected", [(True, [True]), (False, [])])
async def test_f_hub_01_own_vdo_follows_option(include_own, expected):
    fake = FakeSerial()
    hub, rec = make_hub(fake, include_own=include_own)
    task = await start(hub)
    fake.feed_lines(AIS_VDO)
    await settle()
    assert [p.own_ship for p in rec.ais] == expected
    await stop(hub, task)


async def test_f_hub_01_multifragment_ais_reassembled():
    fake = FakeSerial()
    hub, rec = make_hub(fake)
    task = await start(hub)
    # Type 19 split in two fragments (built from the public sample payload)
    payload = "C5N3SRgPEnJGEBT>NhWAwwo862PaLELTBJ:V00000000S0D:R220"
    fake.feed_lines(
        nmea(f"AIVDM,2,1,7,B,{payload[:30]},0", "!"),
        nmea(f"AIVDM,2,2,7,B,{payload[30:]},0", "!"),
    )
    await settle()
    assert [p.msg_type for p in rec.ais] == [19]
    await stop(hub, task)


# --- F-HUB-02 malformed corpus ---------------------------------------------


async def test_f_hub_02_malformed_corpus_counted_valid_data_unaffected():
    fake = FakeSerial()
    hub, rec = make_hub(fake)
    task = await start(hub)
    bad = (FIXTURES / "malformed.nmea").read_bytes().split(b"\r\n")[:-1]
    assert len(bad) == 15
    for line in bad:
        fake.feed_lines(RMC, AIS_TYPE1)
        fake.feed_bytes(line + b"\r\n")
    fake.feed_lines(RMC)
    await settle()
    assert len(rec.gps) == 16 and all(r == rec.gps[0] for r in rec.gps)
    assert len(rec.ais) == 15 and {p.mmsi for p in rec.ais} == {477553000}
    s = hub.stats
    assert s.checksum_errors == 4
    assert s.framing_errors == 4
    assert s.ais_rejected == 5
    assert s.gps_rejected == 2
    assert s.checksum_errors + s.framing_errors + s.ais_rejected + s.gps_rejected == len(bad)
    await stop(hub, task)


async def test_f_hub_02_over_long_unterminated_line_dropped():
    fake = FakeSerial()
    hub, rec = make_hub(fake)
    task = await start(hub)
    fake.feed_bytes(b"$" + b"A" * (RAW_LINE_LIMIT + 500))  # no terminator
    await settle()
    fake.feed_bytes(b"AAAA\r\n")  # end of the over-long line: dropped, not counted twice
    fake.feed_lines(RMC)
    await settle()
    assert hub.stats.framing_errors == 1
    assert [type(r) for r in rec.gps] == [Rmc]
    await stop(hub, task)


async def test_f_hub_02_callback_exception_contained(caplog):
    fake = FakeSerial()
    calls = []

    def on_gps(rec):
        calls.append(rec)
        if len(calls) == 1:
            raise RuntimeError("consumer bug")

    hub = Hub(fake, on_gps=on_gps, on_ais=lambda p: None, on_connection=lambda c: None)
    task = await start(hub)
    with caplog.at_level(logging.ERROR, logger=LOGGER):
        fake.feed_lines(RMC, RMC, RMC)
        await settle()
    assert len(calls) == 3
    assert hub.stats.internal_errors == 1
    assert hub.connected
    assert len([r for r in caplog.records if r.levelno == logging.ERROR]) == 1
    await stop(hub, task)


async def test_f_hub_02_malformed_address_counted_by_start_character():
    fake = FakeSerial()
    hub, _rec = make_hub(fake)
    task = await start(hub)
    fake.feed_lines(nmea("G$RMC,1"), nmea("A-VDM,1", "!"))
    await settle()
    assert (hub.stats.gps_rejected, hub.stats.ais_rejected) == (1, 1)
    await stop(hub, task)


# --- F-HUB-03 (hub half) ---------------------------------------------------


async def test_f_hub_03_disconnect_signalled_immediately():
    fake = FakeSerial()
    blocked = asyncio.Event()

    async def never_wake(delay):
        await blocked.wait()

    hub, rec = make_hub(fake, sleep=never_wake)
    task = await start(hub)
    assert rec.conn == [True] and hub.connected
    fake.available = False
    fake.disconnect()
    await settle()
    # Signalled before any backoff delay has elapsed
    assert rec.conn == [True, False]
    assert not hub.connected
    await stop(hub, task)


# --- F-HUB-04 reconnect ----------------------------------------------------


async def test_backoff_sequence():
    gen = backoff_delays()
    assert [next(gen) for _ in range(9)] == [1, 2, 4, 8, 16, 32, 60, 60, 60]


@pytest.mark.parametrize(
    "outage_s,expected_sleeps",
    [(1, [1]), (5, [1, 2, 4]), (30, [1, 2, 4, 8, 16])],
)
async def test_f_hub_04_reconnect_after_outage(caplog, outage_s, expected_sleeps):
    fake, clock = FakeSerial(), FakeClock()
    sleeps: list[float] = []
    outage_start = clock()

    async def fake_sleep(delay):
        sleeps.append(delay)
        clock.advance(delay)
        fake.available = clock() - outage_start >= outage_s
        await asyncio.sleep(0)

    hub, rec = make_hub(fake, clock, fake_sleep, name="/dev/ttyAIS")
    task = await start(hub)
    with caplog.at_level(logging.INFO, logger=LOGGER):
        fake.available = False
        fake.disconnect()
        await settle(100)
    assert sleeps == expected_sleeps
    assert rec.conn == [True, False, True]
    assert hub.stats.reconnects == 1
    warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
    infos = [r for r in caplog.records if r.levelno == logging.INFO]
    assert len(warnings) == 1 and "/dev/ttyAIS" in warnings[0].getMessage()
    assert len(infos) == 1
    # The new connection works
    fake.feed_lines(RMC)
    await settle()
    assert [type(r) for r in rec.gps] == [Rmc]
    await stop(hub, task)


async def test_f_hub_04_backoff_capped_and_reset_after_reopen():
    fake = FakeSerial()
    sleeps: list[float] = []

    async def fake_sleep(delay):
        sleeps.append(delay)
        await asyncio.sleep(0)

    hub, rec = make_hub(fake, sleep=fake_sleep)
    task = await start(hub)
    fake.fail_opens = 8
    fake.disconnect()
    await settle(200)
    assert sleeps == [1, 2, 4, 8, 16, 32, 60, 60, 60]
    sleeps.clear()
    fake.disconnect(OSError(5, "read error"))  # a read error is an outage too
    await settle()
    assert sleeps == [1]  # backoff restarted
    assert rec.conn == [True, False, True, False, True]
    await stop(hub, task)


async def test_run_without_connect_opens_with_backoff():
    fake = FakeSerial()
    fake.fail_opens = 2
    sleeps: list[float] = []

    async def fake_sleep(delay):
        sleeps.append(delay)
        await asyncio.sleep(0)

    hub, rec = make_hub(fake, sleep=fake_sleep)
    task = asyncio.create_task(hub.run())
    await settle(50)
    assert sleeps == [1, 2]
    assert rec.conn == [True]
    await stop(hub, task)


async def test_connect_fails_when_port_missing():
    fake = FakeSerial()
    fake.available = False
    hub, rec = make_hub(fake)
    with pytest.raises(HubConnectionError):
        await hub.connect()
    assert rec.conn == []


async def test_serial_transport_missing_port_raises(tmp_path):
    hub, _ = make_hub(serial_transport(str(tmp_path / "ttyMISSING"), 38400))
    with pytest.raises(HubConnectionError):
        await hub.connect()


# --- F-HUB-05 partial line --------------------------------------------------


async def test_f_hub_05_partial_line_at_disconnect_discarded():
    fake = FakeSerial()

    async def no_wait(delay):
        await asyncio.sleep(0)

    hub, rec = make_hub(fake, sleep=no_wait)
    task = await start(hub)
    fake.feed_bytes(RMC[:20].encode())  # partial sentence, no terminator
    fake.disconnect()
    await settle()
    fake.feed_bytes(RMC[20:].encode() + b"\r\n")  # tail on the new connection: garbage
    fake.feed_lines(RMC)
    await settle()
    assert [type(r) for r in rec.gps] == [Rmc]
    assert rec.gps[0].latitude == pytest.approx(43.5)
    assert hub.connected
    await stop(hub, task)


# --- Clean close (NFR-07) ---------------------------------------------------


async def test_close_releases_port():
    fake = FakeSerial()
    hub, _rec = make_hub(fake)
    task = await start(hub)
    await stop(hub, task)
    assert fake.writers[-1].closed
    assert not hub.connected
    assert task.done()
    await hub.close()  # idempotent


# --- Probe (config flow, SPEC §11.1) ----------------------------------------


async def test_probe_ok_on_first_valid_sentence():
    fake = FakeSerial()

    async def opener():
        reader, writer = await fake()
        reader.feed_data(b"\xff\xfe junk\r\n" + RMC.encode() + b"\r\n")
        return reader, writer

    assert await probe(opener, timeout=5.0) is ProbeResult.OK
    assert fake.writers[0].closed


async def test_probe_no_data():
    fake = FakeSerial()

    async def opener():
        reader, writer = await fake()
        reader.feed_eof()
        return reader, writer

    assert await probe(opener, timeout=5.0) is ProbeResult.NO_DATA


async def test_probe_no_data_on_timeout():
    assert await probe(FakeSerial(), timeout=0) is ProbeResult.NO_DATA


async def test_probe_garbage_suggests_other_baud():
    fake = FakeSerial()

    async def opener():
        reader, writer = await fake()
        reader.feed_data(b"\xf8\x80x\xe0\xfc\r\n\x00\x1f\xc3" * 5)
        reader.feed_eof()
        return reader, writer

    assert await probe(opener, timeout=5.0) is ProbeResult.GARBAGE


async def test_probe_endless_garbage_line():
    fake = FakeSerial()

    async def opener():
        reader, writer = await fake()
        reader.feed_data(b"\xf8" * (2**16 + 10))  # longer than the reader limit, no newline
        return reader, writer

    assert await probe(opener, timeout=5.0) is ProbeResult.GARBAGE


async def test_invalid_serial_settings_are_a_connection_error():
    async def opener():
        raise ValueError("Not a valid baudrate: -1")

    hub, _rec = make_hub(opener)
    with pytest.raises(HubConnectionError):
        await hub.connect()
    with pytest.raises(HubConnectionError):
        await probe(opener)


async def test_probe_port_missing():
    fake = FakeSerial()
    fake.available = False
    with pytest.raises(HubConnectionError):
        await probe(fake, timeout=5.0)
