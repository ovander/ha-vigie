"""Fixtures for the functional tests in the Home Assistant harness (TEST §4).

The serial port is always the fake transport: `hub.serial_transport` is patched where the
config flow and the coordinator look it up. No real port, no real waiting.
"""

from collections.abc import Iterator
from unittest.mock import patch

import pytest

from tests.helpers import BY_ID_PORT, FakePorts


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations: None) -> None:
    """Let the harness load custom_components/vigie."""


@pytest.fixture
def fake_ports() -> Iterator[FakePorts]:
    ports = FakePorts()
    with (
        patch("custom_components.vigie.config_flow.serial_transport", ports),
        patch("custom_components.vigie.coordinator.serial_transport", ports),
        patch("custom_components.vigie.config_flow.list_serial_ports", return_value=[BY_ID_PORT]),
    ):
        yield ports
