"""Timed replay of NMEA captures (TEST-001 §2, §5.1 E-1 bench; SPEC OD-12).

Reads a capture in the timed format (`<epoch> <sentence>` per line) and writes the
sentences with their original spacing, scaled by `--speed`. Files without timestamps are
replayed at `--rate` lines per second. Output goes to:

- `--pty /tmp/ttyAIS`: a pseudo-terminal created by this tool, linked at that path. Point
  Vigie's serial port at the link. No socat needed. The link is removed on exit; while
  the tool is stopped, Vigie sees the port as gone.
- `--device PATH`: an existing device or file: a USB-serial adapter wired null-modem to
  the Home Assistant host, one end of a socat pair, or a plain file. `--baud` sets the
  rate of a real serial device.

    python -m tests.tools.replay capture.nmea --pty /tmp/ttyAIS --speed 1 --loop
    python -m tests.tools.replay head-on.nmea --device /dev/ttyUSB1 --baud 38400

Linux/macOS only (pseudo-terminals).
"""

from __future__ import annotations

import argparse
import contextlib
import os
import time
from collections.abc import Callable
from pathlib import Path

_STARTS = ("$", "!", "\\")


def parse_lines(text: str) -> list[tuple[float | None, str]]:
    """(timestamp or None, sentence) per non-blank, non-comment line."""
    lines: list[tuple[float | None, str]] = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        stamp, _, rest = line.partition(" ")
        if rest.startswith(_STARTS):
            try:
                lines.append((float(stamp), rest))
                continue
            except ValueError:
                pass
        lines.append((None, line))
    return lines


def schedule(
    lines: list[tuple[float | None, str]], speed: float = 1.0, rate: float = 1.0
) -> list[tuple[float, str]]:
    """Offsets in seconds from the start of the replay for every sentence."""
    out: list[tuple[float, str]] = []
    first: float | None = None
    for index, (stamp, sentence) in enumerate(lines):
        if stamp is None:
            offset = index / rate
        else:
            first = stamp if first is None else first
            offset = (stamp - first) / speed
        out.append((offset, sentence))
    return out


def run(
    scheduled: list[tuple[float, str]],
    write: Callable[[bytes], object],
    *,
    loops: int = 1,
    clock: Callable[[], float] = time.monotonic,
    sleep: Callable[[float], None] = time.sleep,
) -> int:
    """Write each sentence at its offset, CRLF-terminated; `loops=0` repeats forever."""
    count = 0
    span = (scheduled[-1][0] if scheduled else 0.0) + 1.0  # pause one second between loops
    loop = 0
    start = clock()
    while loops == 0 or loop < loops:
        base = start + loop * span
        for offset, sentence in scheduled:
            delay = base + offset - clock()
            if delay > 0:
                sleep(delay)
            write(sentence.encode("ascii", "replace") + b"\r\n")
            count += 1
        loop += 1
    return count


def open_pty(link: Path) -> tuple[int, int]:
    """Create a raw pseudo-terminal and link its slave side at `link`; return (master, slave).

    The slave stays open here so writes never fail while Vigie reconnects.
    """
    import tty

    master, slave = os.openpty()
    tty.setraw(slave)  # no echo, no CR/LF translation
    with contextlib.suppress(FileNotFoundError):
        link.unlink()
    link.symlink_to(os.ttyname(slave))
    return master, slave


def close_pty(link: Path, master: int, slave: int) -> None:
    with contextlib.suppress(FileNotFoundError):
        link.unlink()
    for fd in (master, slave):
        with contextlib.suppress(OSError):
            os.close(fd)


def _device_writer(
    path: Path, baud: int | None
) -> tuple[Callable[[bytes], object], Callable[[], None]]:
    if baud is not None:
        import serial  # pyserial, installed with pyserial-asyncio-fast

        port = serial.Serial(str(path), baudrate=baud)
        return port.write, port.close
    handle = path.open("wb", buffering=0)
    return handle.write, handle.close


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("capture", type=Path, help="capture file (timed or plain)")
    target = parser.add_mutually_exclusive_group(required=True)
    target.add_argument("--pty", type=Path, help="create a pseudo-terminal linked at this path")
    target.add_argument("--device", type=Path, help="write to an existing device or file")
    parser.add_argument("--baud", type=int, help="baud rate of a real serial --device")
    parser.add_argument("--speed", type=float, default=1.0, help="time scale (2 = twice as fast)")
    parser.add_argument("--rate", type=float, default=10.0, help="lines/s for untimed files")
    parser.add_argument("--loop", action="store_true", help="repeat until interrupted")
    args = parser.parse_args(argv)

    scheduled = schedule(
        parse_lines(args.capture.read_text(encoding="utf-8", errors="replace")),
        speed=args.speed,
        rate=args.rate,
    )
    if args.pty:
        master, slave = open_pty(args.pty)
        print(f"Replaying {len(scheduled)} lines on {args.pty} -> {os.ttyname(slave)}", flush=True)

        def write(data: bytes) -> object:
            return os.write(master, data)

        def close() -> None:
            close_pty(args.pty, master, slave)
    else:
        write, close = _device_writer(args.device, args.baud)
    try:
        run(scheduled, write, loops=0 if args.loop else 1)
    except KeyboardInterrupt:
        pass
    finally:
        close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
