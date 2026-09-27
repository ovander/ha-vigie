"""Base entity for Vigie (SPEC §9, §10.1, §10.2).

Every entity belongs to the boat's device, has an entry-scoped unique ID and a
translation key, and is pushed by the coordinator (no polling). The coordinator notifies
once per `update_interval` tick and at once on connection changes; each entity then writes
its state only when its value moved by at least its dead-band, or when its availability
changed. The tick is the throttle (at most one write per interval, NFR-04), so the gate
here only applies the dead-band.
"""

from __future__ import annotations

import math
from collections.abc import Callable
from typing import Any

from homeassistant.core import callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import Entity

from .const import DOMAIN
from .coordinator import VigieCoordinator
from .state import WriteGate


def _abs_delta(a: float, b: float) -> float:
    return abs(a - b)


def with_identity(delta: Callable[[Any, Any], float]) -> Callable[[Any, Any], float]:
    """Compare (identity, value) pairs: another identity is always a significant change."""

    def compare(a: tuple[Any, Any], b: tuple[Any, Any]) -> float:
        return math.inf if a[0] != b[0] else delta(a[1], b[1])

    return compare


class VigieEntity(Entity):
    """Push-updated entity of one boat."""

    _attr_has_entity_name = True
    _attr_should_poll = False
    # Diagnostics stay available while the port is down, so they can show the outage
    _always_available = False

    def __init__(
        self,
        coordinator: VigieCoordinator,
        key: str,
        *,
        deadband: float | None = None,
        delta: Callable[[Any, Any], float] = _abs_delta,
    ) -> None:
        self.coordinator = coordinator
        entry = coordinator.entry
        self._attr_unique_id = f"{entry.entry_id}_{key}"
        self._attr_translation_key = key
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=entry.title,
            manufacturer="Vigie",
            model="NMEA 0183 AIS receiver",
        )
        self._gate = WriteGate(
            interval_s=0.0, deadband=deadband, delta=delta, clock=coordinator.now
        )
        self._written_available: bool | None = None

    def current_value(self) -> Any:
        """Value to show now, or None when there is none (the entity is then unavailable)."""
        raise NotImplementedError

    def gate_value(self) -> Any:
        """What the dead-band compares; the current value unless an entity needs more."""
        return self.current_value()

    @property
    def available(self) -> bool:
        if self._always_available:
            return True
        return self.coordinator.connected and self.current_value() is not None

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self._should_write()  # HA writes the initial state; remember it
        self.async_on_remove(self.coordinator.async_add_listener(self._handle_update))

    @callback
    def _handle_update(self) -> None:
        if self._should_write():
            self.async_write_ha_state()

    def _should_write(self) -> bool:
        available = self.available
        if available != self._written_available:
            self._gate.reset()
            self._written_available = available
        return self._gate.should_write(self.gate_value() if available else None)
