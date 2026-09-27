"""Vigie — AIS traffic watch for Home Assistant.

Home Assistant is imported inside the entry points or for type checking only: importing
any `custom_components.vigie` sub-module runs this file first, and the pure modules
(`nmea/`, `state.py`, `geo.py`, `hub.py`) must not pull in Home Assistant (SPEC NFR-02).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from homeassistant.const import Platform
    from homeassistant.core import HomeAssistant

    from .coordinator import VigieConfigEntry

PLATFORMS: list[Platform | str] = ["binary_sensor", "device_tracker", "sensor"]


async def async_setup_entry(hass: HomeAssistant, entry: VigieConfigEntry) -> bool:
    """Set up Vigie from a config entry: open the port, start the reader."""
    from homeassistant.exceptions import ConfigEntryNotReady

    from .coordinator import VigieCoordinator
    from .hub import HubConnectionError

    coordinator = VigieCoordinator(hass, entry)
    try:
        await coordinator.async_start()
    except HubConnectionError as err:
        # HA retries the setup with its own backoff (SPEC §10.3)
        raise ConfigEntryNotReady(str(err)) from err
    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: VigieConfigEntry) -> bool:
    """Unload a config entry: stop the reader and close the port (NFR-07)."""
    unloaded: bool = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        await entry.runtime_data.async_stop()
    return unloaded
