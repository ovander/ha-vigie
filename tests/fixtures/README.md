# Test fixtures

One sentence per line, UTF-8, `\r\n` line endings preserved (TEST-001 §2). All files here are
**synthetic**: none is a capture of a real receiver. Real captures (D-05/D-06, SPEC X-09) are
tracked in issue #2 and must be anonymised before they are committed (TEST-001 TP-03).

| File | Dataset | Content |
|---|---|---|
| `malformed.nmea` | D-04 | 15 bad lines, in order: 4 checksum errors (wrong, missing `*`, one hex digit, AIS wrong), 4 framing errors (over 82 chars, non-ASCII byte, wrong-baud garbage, unterminated tag block), 5 AIS lines rejected by the decoder with a valid checksum (truncated payload, wrong field count, invalid armoring character `X` (0x58, #11), fill bits > 5, fragment out of range), 2 GPS lines rejected by the parser with a valid checksum (wrong field count, non-numeric field). The AIS payload is the gpsd reference type 1 example. |
| `burst_60s.nmea` | D-08 | 60 s at 51 sentences/s in the timed format `<epoch> <sentence>` (TEST-001 §2): one synthetic `$GPRMC` per second (own boat at 43.5° N 7.25° E, 5 kn, 090°) and 50 `!AIVDM` position reports per second (types 1/2/3 and 18, 80 synthetic MMSIs within ±0.3° lat / ±0.4° lon). AIS sentences were encoded with pyais (MIT, test-only) from random fields with seed 8; the synthetic epoch starts at 1 790 000 000. |
