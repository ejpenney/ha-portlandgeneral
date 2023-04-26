"""PGE sensor platform."""

from datetime import timedelta
import voluptuous as vol

from homeassistant.components.sensor import PLATFORM_SCHEMA
from homeassistant.config_entries import SOURCE_IMPORT, ConfigEntry
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import ConfigType, DiscoveryInfoType

from .const import LOGGER, DOMAIN
from .pge_api import PGEConnection

# Time between updating data from PGE
SCAN_INTERVAL = timedelta(minutes=10)

async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up the PGE sensor entries."""

    username = entry.options[CONF_USERNAME]
    password = entry.options[CONF_PASSWORD]
    requester = PGEConnection(hass, username, password)

    await hass.async_add_executor_job(requester.update)
    sensors = requester.sensors

    async_add_entities(sensors, update_before_add=True)
