"""Services: drop and raise the anchor (SPEC §9.6, OD-22).

Registered once for the domain when the first entry is set up; each call targets one
config entry, so two boats keep separate watches.
"""

from __future__ import annotations

import voluptuous as vol
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import config_validation as cv

from .anchor import MAX_RADIUS_M, MIN_RADIUS_M
from .const import (
    ATTR_CONFIG_ENTRY_ID,
    ATTR_LATITUDE,
    ATTR_LONGITUDE,
    ATTR_RADIUS,
    DOMAIN,
    SERVICE_DROP_ANCHOR,
    SERVICE_RAISE_ANCHOR,
)
from .coordinator import NoOwnPosition, VigieCoordinator

_ENTRY = {vol.Required(ATTR_CONFIG_ENTRY_ID): cv.string}

DROP_SCHEMA = vol.Schema(
    {
        **_ENTRY,
        # Both or neither: an explicit anchor point (e.g. read on the chartplotter)
        vol.Inclusive(ATTR_LATITUDE, "position"): cv.latitude,
        vol.Inclusive(ATTR_LONGITUDE, "position"): cv.longitude,
        vol.Optional(ATTR_RADIUS): vol.All(
            vol.Coerce(float), vol.Range(min=MIN_RADIUS_M, max=MAX_RADIUS_M)
        ),
    }
)
RAISE_SCHEMA = vol.Schema(_ENTRY)


def _coordinator(hass: HomeAssistant, call: ServiceCall) -> VigieCoordinator:
    entry_id = call.data[ATTR_CONFIG_ENTRY_ID]
    entry = hass.config_entries.async_get_entry(entry_id)
    if entry is None or entry.domain != DOMAIN:
        raise ServiceValidationError(
            translation_domain=DOMAIN,
            translation_key="unknown_entry",
            translation_placeholders={"entry_id": entry_id},
        )
    if entry.state is not ConfigEntryState.LOADED:
        raise ServiceValidationError(
            translation_domain=DOMAIN,
            translation_key="entry_not_loaded",
            translation_placeholders={"boat": entry.title},
        )
    coordinator: VigieCoordinator = entry.runtime_data
    return coordinator


def async_register_services(hass: HomeAssistant) -> None:
    """Register the services once; runs in the event loop."""
    if hass.services.has_service(DOMAIN, SERVICE_DROP_ANCHOR):
        return

    async def drop_anchor(call: ServiceCall) -> None:
        coordinator = _coordinator(hass, call)
        try:
            coordinator.drop_anchor(
                call.data.get(ATTR_LATITUDE),
                call.data.get(ATTR_LONGITUDE),
                call.data.get(ATTR_RADIUS),
            )
        except NoOwnPosition as err:
            raise HomeAssistantError(
                translation_domain=DOMAIN, translation_key="no_own_position"
            ) from err

    async def raise_anchor(call: ServiceCall) -> None:
        _coordinator(hass, call).raise_anchor()

    hass.services.async_register(DOMAIN, SERVICE_DROP_ANCHOR, drop_anchor, schema=DROP_SCHEMA)
    hass.services.async_register(DOMAIN, SERVICE_RAISE_ANCHOR, raise_anchor, schema=RAISE_SCHEMA)
