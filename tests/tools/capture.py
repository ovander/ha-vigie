"""Timestamped raw capture of the receiver's serial port (SPEC X-09, TEST-001 §2).

Every line is written as `<epoch seconds> <raw bytes>` with CRLF, exactly as received:
invalid or garbled lines are kept, since they are regression material. Stop the AIS
integration first (only one program can own the port, SPEC §3.1).

    python -m tests.tools.capture --port /dev/serial/by-id/usb-...-port0 --baud 38400 \
        --duration 900

The default output goes under `captures/` (git-ignored). Anonymise a capture (TEST-001 TP-03)
before committing it to `tests/fixtures/`.
"""

from __future__ import annotations

import argparse
import time
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import BinaryIO


def capture(
    readline: Callable[[], bytes],
    out: BinaryIO,
    *,
    clock: Callable[[], float] = time.time,
    duration: float | None = None,
) -> int:
    """Copy lines from `readline` to `out` with timestamps; return the number written.

    `readline` returns b"" on a read timeout; capture continues until `duration` s elapse
    (or forever when None).
    """
    start = clock()
    count = 0
    while True:
        line = readline()
        now = clock()
        if duration is not None and now - start > duration:
            return count
        line = line.rstrip(b"\r\n")
        if line:
            out.write(f"{now:.3f} ".encode() + line + b"\r\n")
            count += 1


def default_output(port: str, stamp: str | None = None) -> Path:
    stamp = stamp or datetime.now(UTC).strftime("%Y%m%dT%H%M%S")
    return Path("captures") / f"{stamp}_{Path(port).name}.nmea"


def main(argv: list[str] | None = None) -> int:
    import serial  # pyserial, installed with pyserial-asyncio-fast

    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--port", required=True, help="serial port, /dev/serial/by-id/... preferred"
    )
    parser.add_argument("--baud", type=int, default=38400)
    parser.add_argument("--duration", type=float, help="seconds (default: until Ctrl-C)")
    parser.add_argument("-o", "--output", type=Path, help="output file (default: captures/...)")
    args = parser.parse_args(argv)
    output = args.output or default_output(args.port)
    output.parent.mkdir(parents=True, exist_ok=True)
    with (
        serial.Serial(args.port, baudrate=args.baud, timeout=1.0) as port,
        output.open("wb") as out,
    ):
        print(f"Capturing {args.port} at {args.baud} baud into {output} (Ctrl-C to stop)")
        try:
            count = capture(port.readline, out, duration=args.duration)
        except KeyboardInterrupt:
            count = -1
    print(f"Done: {output}" + (f", {count} lines" if count >= 0 else ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
