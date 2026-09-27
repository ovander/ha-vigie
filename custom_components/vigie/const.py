"""Constants for the Vigie integration."""

DOMAIN = "vigie"

# Config entry data (SPEC §11.1)
CONF_SERIAL_PORT = "serial_port"
CONF_BAUDRATE = "baudrate"

DEFAULT_SERIAL_PORT = "/dev/ttyUSB0"
DEFAULT_BAUDRATE = 38400
BAUDRATES = (38400, 4800)  # offered in the form; custom values allowed (OD-14)
SERIAL_BY_ID_GLOB = "/dev/serial/by-id/*"

# Options (SPEC §11.2, P1 subset)
CONF_UPDATE_INTERVAL = "update_interval"  # seconds
CONF_STALE_TIMEOUT = "stale_timeout"  # seconds
CONF_EXPIRY_CLASS_A = "expiry_class_a"  # minutes
CONF_EXPIRY_CLASS_B = "expiry_class_b"  # minutes, also anchored/moored Class A
CONF_INCLUDE_OWN_VDO = "include_own_vdo"
CONF_OWN_MMSI = "own_mmsi"

DEFAULT_OPTIONS: dict[str, int | bool] = {
    CONF_UPDATE_INTERVAL: 1,
    CONF_STALE_TIMEOUT: 10,
    CONF_EXPIRY_CLASS_A: 10,
    CONF_EXPIRY_CLASS_B: 15,
    CONF_INCLUDE_OWN_VDO: True,
}
