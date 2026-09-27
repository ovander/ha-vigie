"""Config flow for Vigie (bootstrap: no port probe yet, see SPEC §11.1)."""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_NAME

from .const import (
    CONF_BAUDRATE,
    CONF_SERIAL_PORT,
    DEFAULT_BAUDRATE,
    DEFAULT_SERIAL_PORT,
    DOMAIN,
)


class VigieConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Vigie."""

    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Handle the initial step."""
        if user_input is not None:
            await self.async_set_unique_id(user_input[CONF_SERIAL_PORT])
            self._abort_if_unique_id_configured()
            return self.async_create_entry(title=user_input[CONF_NAME], data=user_input)

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_NAME): str,
                    vol.Required(CONF_SERIAL_PORT, default=DEFAULT_SERIAL_PORT): str,
                    vol.Required(CONF_BAUDRATE, default=DEFAULT_BAUDRATE): vol.In([4800, 38400]),
                }
            ),
        )
