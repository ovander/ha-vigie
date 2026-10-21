"""Anchor watch: swing radius, drag and position-loss alarm (SPEC §8.4, C-11).

Pure Python, no Home Assistant import (SPEC NFR-02). Distances in metres, times in
seconds of the injectable monotonic clock. `armed_at` is a wall-clock timestamp supplied
by the caller and only carried through (it survives a restart, monotonic time does not).

Decisions (SPEC §14): the drag alarm latches until disarmed or re-dropped (OD-23); a
missing position while armed raises `no_position` (OD-24); the anchor point is the own
position at arming or explicit coordinates, with no bow offset (OD-25); the state can be
saved and restored across a restart (OD-26).
"""

from __future__ import annotations

import math
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

from .geo import bearing_deg, distance_m

DRAG = "drag"
NO_POSITION = "no_position"

MIN_RADIUS_M = 10.0
MAX_RADIUS_M = 500.0
DEFAULT_RADIUS_M = 50.0
DEFAULT_CONFIRM_S = 20.0
DEFAULT_POSITION_TIMEOUT_S = 60.0

# Below this distance the boat is on the anchor point and has no bearing to it
_ON_ANCHOR_M = 0.01


@dataclass(frozen=True, slots=True)
class AnchorStatus:
    armed: bool
    alarm: bool
    reason: str | None  # DRAG, NO_POSITION or None
    distance_m: float | None  # boat to anchor; None when disarmed or without position
    bearing_to_anchor: float | None
    max_distance_m: float | None  # since arming; None when disarmed
    radius_m: float


def _check_radius(radius_m: float) -> float:
    radius = float(radius_m)
    if not MIN_RADIUS_M <= radius <= MAX_RADIUS_M:  # also refuses NaN
        raise ValueError(f"radius must be {MIN_RADIUS_M:g}–{MAX_RADIUS_M:g} m, got {radius_m}")
    return radius


def _check_position(lat: float | None, lon: float | None) -> tuple[float, float]:
    if lat is None and lon is None:
        raise ValueError("no position to drop the anchor at")
    if lat is None or lon is None:
        raise ValueError("latitude and longitude go together")
    lat, lon = float(lat), float(lon)
    if not (-90.0 <= lat <= 90.0 and -180.0 <= lon <= 180.0):
        raise ValueError(f"position out of range: {lat}, {lon}")
    return lat, lon


class AnchorWatch:
    """Watches own position against an anchor point and a swing radius.

    `update()` is called at every tick with the current own position, or `None` when
    there is none. The boat is outside when its distance exceeds the radius; once it has
    been outside continuously for `confirm_s` the alarm turns on with reason `drag` and
    stays on until `disarm()` or a new `arm()`. With no position for `position_timeout_s`
    (counted from the last fix, or from arming/restore) the alarm turns on with reason
    `no_position`; it clears when a position inside returns. A position that returns
    outside keeps the alarm on and starts the drag timer, so there is never a silent gap.
    """

    def __init__(
        self,
        radius_m: float = DEFAULT_RADIUS_M,
        confirm_s: float = DEFAULT_CONFIRM_S,
        position_timeout_s: float = DEFAULT_POSITION_TIMEOUT_S,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if not (confirm_s > 0 and position_timeout_s > 0):
            raise ValueError("confirmation and position timeout must be positive")
        self._radius = _check_radius(radius_m)
        self._confirm = float(confirm_s)
        self._timeout = float(position_timeout_s)
        self._clock = clock
        self._anchor: tuple[float, float] | None = None
        self._armed_at: float | None = None
        self._max = 0.0
        self._reason: str | None = None
        self._last_fix = 0.0
        self._outside_since: float | None = None
        self._status = self._disarmed_status()

    # --- state -------------------------------------------------------------------------

    @property
    def armed(self) -> bool:
        return self._anchor is not None

    @property
    def anchor(self) -> tuple[float, float] | None:
        return self._anchor

    @property
    def radius_m(self) -> float:
        return self._radius

    @property
    def armed_at(self) -> float | None:
        return self._armed_at

    @property
    def status(self) -> AnchorStatus:
        """The status computed by the last `update()` (or the last state change)."""
        return self._status

    # --- commands ----------------------------------------------------------------------

    def arm(
        self,
        lat: float | None,
        lon: float | None,
        radius_m: float | None = None,
        armed_at: float | None = None,
    ) -> None:
        """Drop (or re-drop) the anchor; clears the alarm and the maximum distance."""
        position = _check_position(lat, lon)
        radius = self._radius if radius_m is None else _check_radius(radius_m)
        self._anchor, self._radius, self._armed_at = position, radius, armed_at
        self._max = 0.0
        self._reason = None
        self._outside_since = None
        self._last_fix = self._clock()
        self._status = self._armed_status(None)

    def disarm(self) -> None:
        self._anchor = None
        self._armed_at = None
        self._reason = None
        self._outside_since = None
        self._status = self._disarmed_status()

    def set_radius(self, radius_m: float) -> None:
        """Applies at once; the drag timer restarts, a latched alarm stays on."""
        self._radius = _check_radius(radius_m)
        self._outside_since = None
        self._status = self._armed_status(None) if self.armed else self._disarmed_status()

    # --- tick --------------------------------------------------------------------------

    def update(
        self, position: tuple[float, float] | None, fix_at: float | None = None
    ) -> AnchorStatus:
        """Feed the current own position (`fix_at`: its clock time, default now)."""
        if self._anchor is None:
            self._status = self._disarmed_status()
            return self._status
        now = self._clock()
        if position is not None:
            self._last_fix = max(self._last_fix, now if fix_at is None else fix_at)
            if now - self._last_fix >= self._timeout:
                position = None  # an old fix is no position
        if position is None:
            self._outside_since = None
            if self._reason is None and now - self._last_fix >= self._timeout:
                self._reason = NO_POSITION
            self._status = self._armed_status(None)
            return self._status

        distance = distance_m(*position, *self._anchor)
        self._max = max(self._max, distance)
        if distance > self._radius:
            if self._outside_since is None:
                self._outside_since = now
            if self._reason != DRAG and now - self._outside_since >= self._confirm:
                self._reason = DRAG
        else:
            self._outside_since = None
            if self._reason == NO_POSITION:
                self._reason = None
        bearing = None if distance < _ON_ANCHOR_M else bearing_deg(*position, *self._anchor)
        self._status = self._armed_status(distance, bearing)
        return self._status

    # --- restore (OD-26) ---------------------------------------------------------------

    def to_dict(self) -> dict[str, Any] | None:
        """What survives a restart; `None` when disarmed. Only a drag alarm is kept."""
        if self._anchor is None:
            return None
        return {
            "latitude": self._anchor[0],
            "longitude": self._anchor[1],
            "radius_m": self._radius,
            "armed_at": self._armed_at,
            "max_distance_m": self._max,
            "alarm": DRAG if self._reason == DRAG else None,
        }

    def restore(self, data: Mapping[str, Any] | None) -> None:
        """Re-arm from `to_dict()`; the position-loss timer starts now. Invalid data is
        refused with `ValueError` and leaves the watch unchanged."""
        if data is None:
            self.disarm()
            return
        try:
            position = _check_position(data["latitude"], data["longitude"])
            radius = _check_radius(data["radius_m"])
            max_distance = float(data.get("max_distance_m") or 0.0)
            armed_at = data.get("armed_at")
            armed_at = None if armed_at is None else float(armed_at)
        except (KeyError, TypeError) as err:
            raise ValueError(f"invalid anchor watch state: {err}") from err
        alarm = data.get("alarm")
        if alarm not in (None, DRAG) or not math.isfinite(max_distance):
            raise ValueError(f"invalid anchor watch state: {data}")
        self.arm(*position, radius_m=radius, armed_at=armed_at)
        self._max = max_distance
        self._reason = alarm
        self._status = self._armed_status(None)

    # --- helpers -----------------------------------------------------------------------

    def _armed_status(self, distance: float | None, bearing: float | None = None) -> AnchorStatus:
        return AnchorStatus(
            armed=True,
            alarm=self._reason is not None,
            reason=self._reason,
            distance_m=distance,
            bearing_to_anchor=bearing,
            max_distance_m=self._max,
            radius_m=self._radius,
        )

    def _disarmed_status(self) -> AnchorStatus:
        return AnchorStatus(False, False, None, None, None, None, self._radius)
