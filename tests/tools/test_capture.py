"""Timestamped capture tool (SPEC X-09, TEST §2 timed format)."""

import io

from tests.tools import capture


def test_capture_timestamps_raw_lines_until_duration():
    feed = [b"$GPRMC,1*00\r\n", b"", b"\xff\xfe garbage\r\n", b"!AIVDM,1*00\r\n", b"$late*00\r\n"]
    clock = [1790000000.0]

    def readline():
        clock[0] += 0.25
        return feed.pop(0) if feed else b""

    out = io.BytesIO()
    count = capture.capture(readline, out, clock=lambda: clock[0], duration=1.0)
    lines = out.getvalue().split(b"\r\n")[:-1]
    assert count == 3
    assert lines[0] == b"1790000000.250 $GPRMC,1*00"
    assert lines[1] == b"1790000000.750 \xff\xfe garbage"  # raw bytes kept for regression
    assert lines[2].endswith(b"!AIVDM,1*00")


def test_default_output_path_is_git_ignored_folder():
    path = capture.default_output("/dev/serial/by-id/usb-Fake_AIS-if00", stamp="20260927T120000")
    assert path.parts[0] == "captures"
    assert path.name == "20260927T120000_usb-Fake_AIS-if00.nmea"
