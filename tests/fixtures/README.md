# Test fixtures

One sentence per line, UTF-8, `\r\n` line endings preserved (TEST-001 §2). All files here are
**synthetic**: none is a capture of a real receiver. Real captures (D-05/D-06, SPEC X-09) are
tracked in issue #2 and must be anonymised before they are committed (TEST-001 TP-03).

| File | Dataset | Content |
|---|---|---|
| `malformed.nmea` | D-04 | 15 bad lines, in order: 4 checksum errors (wrong, missing `*`, one hex digit, AIS wrong), 4 framing errors (over 82 chars, non-ASCII byte, wrong-baud garbage, unterminated tag block), 5 AIS lines rejected by the decoder with a valid checksum (truncated payload, wrong field count, invalid armoring character `x`, fill bits > 5, fragment out of range), 2 GPS lines rejected by the parser with a valid checksum (wrong field count, non-numeric field). The AIS payload is the gpsd reference type 1 example. |
