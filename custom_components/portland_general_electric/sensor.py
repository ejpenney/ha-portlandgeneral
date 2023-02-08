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

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend(
    {
        vol.Required(CONF_USERNAME): cv.string,
        vol.Optional(CONF_PASSWORD): cv.string,
    }
)

# DEPRECATED
async def async_setup_platform(
    hass: HomeAssistant,
    config: ConfigType,
    async_add_entities: AddEntitiesCallback,
    discovery_info: DiscoveryInfoType | None = None,
) -> None:
    """Set up the PGE sensor platform."""
    LOGGER.warning(
        "Configuration of the portland_general_electric platform in YAML is deprecated "
        "and will be removed in V0.2; Your existing "
        "configuration has been imported into the UI automatically and can be "
        "safely removed from your configuration.yaml file"
    )

    if discovery_info:
        config = PLATFORM_SCHEMA(discovery_info)

    hass.async_create_task(
        hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": SOURCE_IMPORT},
            data=config,
        )
    )


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
