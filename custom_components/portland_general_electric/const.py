"""Constants for the Portland General Electric integration."""

import logging
from typing import Final

from homeassistant.const import Platform

DOMAIN: Final = "portland_general_electric"

ATTR_ACCOUNT_NUMBER = "account_number"
ATTR_RAW_DATA = "raw_data"
ATTR_TOTAL_USAGE = "total_usage"

LOGGER = logging.getLogger(__package__)
PLATFORMS: Final = [Platform.SENSOR]
