"""Helpers shared by the functional tests (Home Assistant harness)."""

from datetime import timedelta

from freezegun.api import FrozenDateTimeFactory
from homeassistant.const import CONF_NAME
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry, async_fire_time_changed

from custom_components.vigie.const import CONF_BAUDRATE, CONF_SERIAL_PORT, DOMAIN
from tests.helpers import BY_ID_PORT


def make_entry(
    hass: HomeAssistant, port: str = BY_ID_PORT, title: str = "Garnet", **options
) -> MockConfigEntry:
    entry = MockConfigEntry(
        domain=DOMAIN,
        title=title,
        unique_id=port,
        data={CONF_NAME: title, CONF_SERIAL_PORT: port, CONF_BAUDRATE: 38400},
        options=options,
    )
    entry.add_to_hass(hass)
    return entry


async def setup(hass: HomeAssistant, entry: MockConfigEntry) -> None:
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()


async def tick(hass: HomeAssistant, freezer: FrozenDateTimeFactory, seconds: float = 1) -> None:
    """Advance simulated time and run the coordinator tick (no real waiting).

    Lines already fed to the fake port are handled first: data arrives during the
    interval, the tick comes at its end.
    """
    await hass.async_block_till_done()
    freezer.tick(timedelta(seconds=seconds))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()


def entity_id(hass: HomeAssistant, entry: MockConfigEntry, key: str, domain: str = "sensor") -> str:
    """Entity ID from the registry, looked up by the entry-scoped unique ID."""
    eid = er.async_get(hass).async_get_entity_id(domain, DOMAIN, f"{entry.entry_id}_{key}")
    assert eid is not None, f"no {domain} entity for {key}"
    return eid
