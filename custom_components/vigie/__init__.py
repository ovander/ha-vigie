"""Vigie — AIS traffic watch for Home Assistant.

Bootstrap skeleton: the entry loads without platforms. The transport hub,
coordinator and entities arrive in phase P1 (see docs/HA-SAIL-SPEC-001.md).

Home Assistant types are imported for type checking only, so that importing
the `nmea` sub-package never pulls in Home Assistant (SPEC NFR-02).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry
    from homeassistant.core import HomeAssistant


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Vigie from a config entry."""
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    return True
