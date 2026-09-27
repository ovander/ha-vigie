"""Timed replay tool (TEST §2 timed format, §5.1 E-1 bench, SPEC OD-12)."""

import os
import select

import pytest

from tests.tools import replay
from tests.tools.replay import parse_lines, run, schedule

TIMED = """1790000000.000 $GPRMC,080000,A,4330.000,N,00715.000,E,5.0,090.0,270926,,*16
1790000000.500 !AIVDM,1,1,,A,13P=GOAP2=0OlLHI3;?1<wv1P000,0*6B

# comment lines and blank lines are skipped
1790000002.000 $GPRMC,080002,A,4330.000,N,00715.000,E,5.0,090.0,270926,,*14
"""


def test_parse_timed_and_untimed():
    timed = parse_lines(TIMED)
    assert [t for t, _ in timed] == [1790000000.0, 1790000000.5, 1790000002.0]
    assert timed[1][1].startswith("!AIVDM")
    untimed = parse_lines("$GPRMC,1*00\r\n\\s:r*00\\!AIVDM,1*00\n")
    assert untimed == [(None, "$GPRMC,1*00"), (None, "\\s:r*00\\!AIVDM,1*00")]


@pytest.mark.parametrize(
    "speed,expected", [(1.0, [0.0, 0.5, 2.0]), (2.0, [0.0, 0.25, 1.0]), (10.0, [0.0, 0.05, 0.2])]
)
def test_schedule_honours_spacing_scaled_by_speed(speed, expected):
    offsets = [o for o, _ in schedule(parse_lines(TIMED), speed=speed, rate=1.0)]
    assert offsets == pytest.approx(expected)


def test_schedule_untimed_at_rate():
    lines = [(None, f"$GPTXT,{i}*00") for i in range(4)]
    assert [o for o, _ in schedule(lines, speed=1.0, rate=2.0)] == [0.0, 0.5, 1.0, 1.5]


def test_run_writes_crlf_lines_on_time():
    clock = [100.0]
    sleeps: list[float] = []

    def sleep(seconds):
        sleeps.append(seconds)
        clock[0] += seconds

    written: list[tuple[float, bytes]] = []
    count = run(
        schedule(parse_lines(TIMED), speed=1.0, rate=1.0),
        lambda data: written.append((clock[0], data)),
        clock=lambda: clock[0],
        sleep=sleep,
    )
    assert count == 3
    assert [t - 100.0 for t, _ in written] == pytest.approx([0.0, 0.5, 2.0])
    assert all(data.endswith(b"\r\n") for _, data in written)
    assert written[0][1].startswith(b"$GPRMC")


def test_run_loops():
    clock = [0.0]

    def sleep(seconds):
        clock[0] += seconds

    written: list[bytes] = []
    count = run(
        schedule(parse_lines(TIMED), speed=100.0, rate=1.0),
        written.append,
        clock=lambda: clock[0],
        sleep=sleep,
        loops=3,
    )
    assert count == 9 and len(written) == 9


def test_pty_link_delivers_bytes(tmp_path):
    link = tmp_path / "ttyAIS"
    master, slave = replay.open_pty(link)
    try:
        assert link.is_symlink() and os.path.realpath(link).startswith("/dev/pts/")
        reader = os.open(link, os.O_RDONLY | os.O_NOCTTY | os.O_NONBLOCK)
        try:
            os.write(master, b"$GPTXT,01*00\r\n")
            ready, _, _ = select.select([reader], [], [], 2.0)
            assert ready
            assert os.read(reader, 100) == b"$GPTXT,01*00\r\n"  # raw mode: bytes unchanged
        finally:
            os.close(reader)
    finally:
        replay.close_pty(link, master, slave)
    assert not link.exists()


def test_cli_to_file(tmp_path):
    src = tmp_path / "in.nmea"
    src.write_text(TIMED)
    out = tmp_path / "out.nmea"
    assert replay.main([str(src), "--device", str(out), "--speed", "1000"]) == 0
    assert out.read_bytes().count(b"\r\n") == 3
