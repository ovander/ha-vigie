"""Config and options flows for Vigie (SPEC §11)."""

from __future__ import annotations

import glob
import re
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlowWithReload,
)
from homeassistant.const import CONF_NAME
from homeassistant.core import callback
from homeassistant.helpers.selector import (
    BooleanSelector,
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
    TextSelector,
)

from .const import (
    BAUDRATES,
    CONF_BAUDRATE,
    CONF_CPA_THRESHOLD,
    CONF_EXCLUDE_STATIONARY,
    CONF_EXPIRY_CLASS_A,
    CONF_EXPIRY_CLASS_B,
    CONF_INCLUDE_OWN_VDO,
    CONF_OWN_MMSI,
    CONF_SERIAL_PORT,
    CONF_STALE_TIMEOUT,
    CONF_TCPA_THRESHOLD,
    CONF_UPDATE_INTERVAL,
    DEFAULT_BAUDRATE,
    DEFAULT_OPTIONS,
    DEFAULT_SERIAL_PORT,
    DOMAIN,
    SERIAL_BY_ID_GLOB,
)
from .hub import HubConnectionError, ProbeResult, probe, serial_transport

_MMSI = re.compile(r"^\d{9}$")


def list_serial_ports() -> list[str]:
    """Stable serial device paths (blocking: run in the executor)."""
    return sorted(glob.glob(SERIAL_BY_ID_GLOB))


def _other_baudrate(baudrate: int) -> int:
    return BAUDRATES[1] if baudrate == BAUDRATES[0] else BAUDRATES[0]


class VigieConfigFlow(ConfigFlow, domain=DOMAIN):
    """Set up one boat on one serial port (SPEC §11.1)."""

    VERSION = 1

    def __init__(self) -> None:
        self._data: dict[str, Any] = {}

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> VigieOptionsFlow:
        return VigieOptionsFlow()

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        placeholders: dict[str, str] = {}
        if user_input is not None:
            port = user_input[CONF_SERIAL_PORT].strip()
            baudrate = _parse_baudrate(user_input[CONF_BAUDRATE])
            if baudrate is None:
                errors[CONF_BAUDRATE] = "invalid_baudrate"
            else:
                await self.async_set_unique_id(port)
                self._abort_if_unique_id_configured()
                self._data = {
                    CONF_NAME: user_input[CONF_NAME],
                    CONF_SERIAL_PORT: port,
                    CONF_BAUDRATE: baudrate,
                }
                try:
                    result = await probe(serial_transport(port, baudrate))
                except HubConnectionError:
                    errors["base"] = "cannot_connect"
                else:
                    if result is ProbeResult.OK:
                        return self._create()
                    if result is ProbeResult.NO_DATA:
                        return await self.async_step_no_data()
                    errors["base"] = "wrong_baud"
                    placeholders["other_baudrate"] = str(_other_baudrate(baudrate))

        ports = await self.hass.async_add_executor_job(list_serial_ports)
        defaults = user_input or {}
        schema = vol.Schema(
            {
                vol.Required(CONF_NAME, default=defaults.get(CONF_NAME, "")): str,
                vol.Required(
                    CONF_SERIAL_PORT,
                    default=defaults.get(
                        CONF_SERIAL_PORT, ports[0] if ports else DEFAULT_SERIAL_PORT
                    ),
                ): SelectSelector(
                    SelectSelectorConfig(
                        options=ports, custom_value=True, mode=SelectSelectorMode.DROPDOWN
                    )
                ),
                vol.Required(
                    CONF_BAUDRATE, default=str(defaults.get(CONF_BAUDRATE, DEFAULT_BAUDRATE))
                ): SelectSelector(
                    SelectSelectorConfig(
                        options=[str(b) for b in BAUDRATES],
                        custom_value=True,
                        mode=SelectSelectorMode.DROPDOWN,
                    )
                ),
            }
        )
        return self.async_show_form(
            step_id="user",
            data_schema=schema,
            errors=errors,
            description_placeholders=placeholders or None,
        )

    async def async_step_no_data(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """The port opened but stayed silent for 5 s: explain, and let the user save."""
        if user_input is not None:
            return self._create()
        return self.async_show_form(
            step_id="no_data",
            data_schema=vol.Schema({}),
            errors={"base": "no_data"},
            description_placeholders={CONF_SERIAL_PORT: self._data[CONF_SERIAL_PORT]},
        )

    def _create(self) -> ConfigFlowResult:
        return self.async_create_entry(title=self._data[CONF_NAME], data=self._data)


def _parse_baudrate(raw: Any) -> int | None:
    try:
        value = int(str(raw).strip())
    except ValueError:
        return None
    return value if value > 0 else None


class VigieOptionsFlow(OptionsFlowWithReload):
    """Options (SPEC §11.2); changing them reloads the entry."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            options = dict(user_input)
            mmsi = str(options.pop(CONF_OWN_MMSI, "") or "").strip()
            if mmsi and not _MMSI.match(mmsi):
                errors[CONF_OWN_MMSI] = "invalid_mmsi"
            else:
                if mmsi:
                    options[CONF_OWN_MMSI] = int(mmsi)
                return self.async_create_entry(data=options)

        current = {**DEFAULT_OPTIONS, **self.config_entry.options}
        if user_input is not None:
            current.update(user_input)
        own_mmsi = current.get(CONF_OWN_MMSI)

        def number(maximum: int, unit: str) -> vol.All:
            return vol.All(
                NumberSelector(
                    NumberSelectorConfig(
                        min=1,
                        max=maximum,
                        step=1,
                        unit_of_measurement=unit,
                        mode=NumberSelectorMode.BOX,
                    )
                ),
                vol.Coerce(int),
            )

        schema = vol.Schema(
            {
                vol.Required(CONF_UPDATE_INTERVAL, default=current[CONF_UPDATE_INTERVAL]): number(
                    60, "s"
                ),
                vol.Required(CONF_STALE_TIMEOUT, default=current[CONF_STALE_TIMEOUT]): number(
                    600, "s"
                ),
                vol.Required(CONF_EXPIRY_CLASS_A, default=current[CONF_EXPIRY_CLASS_A]): number(
                    120, "min"
                ),
                vol.Required(CONF_EXPIRY_CLASS_B, default=current[CONF_EXPIRY_CLASS_B]): number(
                    120, "min"
                ),
                vol.Required(
                    CONF_INCLUDE_OWN_VDO, default=current[CONF_INCLUDE_OWN_VDO]
                ): BooleanSelector(),
                vol.Required(CONF_CPA_THRESHOLD, default=current[CONF_CPA_THRESHOLD]): vol.All(
                    NumberSelector(
                        NumberSelectorConfig(
                            min=0.05,
                            max=5,
                            step=0.05,
                            unit_of_measurement="NM",
                            mode=NumberSelectorMode.BOX,
                        )
                    ),
                    vol.Coerce(float),
                ),
                vol.Required(CONF_TCPA_THRESHOLD, default=current[CONF_TCPA_THRESHOLD]): number(
                    60, "min"
                ),
                vol.Required(
                    CONF_EXCLUDE_STATIONARY, default=current[CONF_EXCLUDE_STATIONARY]
                ): BooleanSelector(),
                vol.Optional(
                    CONF_OWN_MMSI,
                    description={"suggested_value": str(own_mmsi) if own_mmsi else None},
                ): TextSelector(),
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema, errors=errors)
