"""PGE sensor platform."""
import logging
from datetime import timedelta
from typing import Callable, Optional
from portlandgeneral import OPowerApi, PortlandGeneralApi
import voluptuous as vol
import json
from datetime import date, datetime
from dateutil.relativedelta import relativedelta

from homeassistant.components.sensor import (
    PLATFORM_SCHEMA,
    SensorDeviceClass,
    SensorStateClass,
    RestoreSensor,
    ENTITY_ID_FORMAT,
)
from homeassistant.const import (
    CONF_USERNAME,
    CONF_PASSWORD,
    ATTR_UNIT_OF_MEASUREMENT,
    ENERGY_KILO_WATT_HOUR,
    CURRENCY_DOLLAR,
)
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.typing import (
    ConfigType,
    DiscoveryInfoType,
    HomeAssistantType,
)

from .const import ATTR_ACCOUNT_NUMBER, ATTR_RAW_DATA, ATTR_TOTAL_USAGE

_LOGGER = logging.getLogger(__name__)
# Time between updating data from PGE
SCAN_INTERVAL = timedelta(minutes=10)

REPO_SCHEMA = vol.Schema(
    {vol.Required(CONF_USERNAME): cv.string, vol.Required(CONF_PASSWORD): cv.string}
)

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend(
    {
        vol.Required(CONF_USERNAME): cv.string,
        vol.Optional(CONF_PASSWORD): cv.string,
    }
)


async def async_setup_platform(
    hass: HomeAssistantType,
    config: ConfigType,
    async_add_entities: Callable,
    _: Optional[DiscoveryInfoType] = None,
) -> None:
    """Set up the sensor platform."""

    sensors = [
        DailyUsageSensor(
            username=config[CONF_USERNAME],
            password=config[CONF_PASSWORD],
            hass=hass,
        ),
        HourlyUsageSensor(
            username=config[CONF_USERNAME],
            password=config[CONF_PASSWORD],
            hass=hass,
        ),
        CostSensor(
            username=config[CONF_USERNAME],
            password=config[CONF_PASSWORD],
            hass=hass,
        ),
    ]
    async_add_entities(sensors, update_before_add=True)


class PGESensor(RestoreSensor):
    """Representation of a PGE sensor."""
    billing_day = None

    def __init__(
        self,
        hass: HomeAssistantType,
        username: str,
        password: str,
    ):
        super().__init__()

        log_level = logging.getLevelName(_LOGGER.getEffectiveLevel())
        verbose = log_level == "DEBUG"
        _LOGGER.debug("log_level=%s and verbose=%s", log_level, verbose)
        self._attr_extra_state_attributes = {}

        self.opower_client = OPowerApi(verbose=verbose)
        self.client = PortlandGeneralApi(verbose=verbose)
        self._hass = hass
        self.username = username
        self.password = password
        self.uuid = None
        self._available = True
        self._name = None
        self._unique_id = None

    def _login(self, client=False) -> None:
        self.opower_client.login(username=self.username, password=self.password)

        if client:
            self.client.login(username=self.username, password=self.password)

        if not self.uuid:
            self.uuid = self.opower_client.current_customers().utility_accounts[0].uuid

    @property
    def unique_id(self) -> str:
        """Return the unique ID of the sensor."""
        return f"{self.uuid}-{self._unique_id}"

    # @property
    # def entity_id(self) -> str:
    #     """Returns entity_id of the sensor"""
    #     return ENTITY_ID_FORMAT.format(f"pge_reported_{self.unique_id}")

    @property
    def available(self) -> str:
        """Return the availability of the sensor."""
        return self._available

    @property
    def name(self) -> str:
        """Return the name of the sensor."""
        return self._name

    async def async_added_to_hass(self) -> None:
        """Handle entity which will be added."""
        if restored_data := await self.async_get_last_sensor_data():
            self._attr_native_value = restored_data.native_value
        await super().async_added_to_hass()

    def get_billing_day(self) -> None:
        """Lookup how far we are into the billing cycle"""
        info = self.client.get_account_info()
        first_account_number = [
            group.default_account.account_number for group in info.groups
        ][0]
        first_account_detail = self.client.get_account_details(
            first_account_number, info.encrypted_person_id
        )[0]
        tracker = self.client.get_energy_tracker_info(
            first_account_detail.encrypted_account_number,
            first_account_detail.encrypted_person_id,
        )
        billing_day = tracker.details.billing_cycle_day
        self.billing_day = billing_day if billing_day else 1
        _LOGGER.debug("Billing Day set to %s", self.billing_day)


class CostSensor(PGESensor):
    """Representation of Cost"""
    _attr_icon = "mdi:currency-usd"
    _attr_native_unit_of_measurement = "%s/%s" % (CURRENCY_DOLLAR, ENERGY_KILO_WATT_HOUR)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._name = "PGE Reported Cost"
        self._unique_id = "cost"

    def update(self):
        """Get latest data for the sensor"""
        self._login(client=True)

        if not self.billing_day:
            self.get_billing_day()

        start_date = date.today() - relativedelta(days=self.billing_day)
        _LOGGER.debug("Query Period start_date=%s", start_date)

        try:
            meter = self.opower_client.utility_cost_daily(self.uuid, start_date)
            total_usage = 0
            for read in meter.reads:
                total_usage += read.value
            if total_usage > 1000:
                self._attr_native_value = meter.series_components[1].cost
            else:
                self._attr_native_value = meter.series_components[0].cost

            self._attr_extra_state_attributes.update(
                {
                    ATTR_TOTAL_USAGE: str(total_usage),
                }
            )
        except Exception as exc:
            _LOGGER.warning("Caught exception: %s", exc.args)
            self._available = False


class PGEUsageSensor(PGESensor):
    """Representation of a PGE Usage Sensor"""
    _attr_device_class = SensorDeviceClass.ENERGY
    _attr_state_class = SensorStateClass.TOTAL
    _attr_icon = "mdi:meter-electric"
    _attr_native_unit_of_measurement = ENERGY_KILO_WATT_HOUR

    def _update_state_attr(self, new_state: str, utility_reading: dict):
        self._attr_extra_state_attributes.update(
            {
                ATTR_ACCOUNT_NUMBER: self.uuid,
                ATTR_RAW_DATA: json.loads(
                    json.dumps(
                        utility_reading,
                        default=lambda o: getattr(o, "__dict__", str(o)),
                    )
                ),
            }
        )

        _LOGGER.debug("Setting Meter to %s", new_state)
        self._attr_native_value = new_state
        self._available = True

    def _reset_meter(self, new_reset: datetime, meter: any) -> None:
        """New readings won't be 0, in order to reset, first update after a new reading will be 0.
            Future readings will increment adjust on a delay.

        Args:
            new_reset (datetime): New time of "0" value
            meter (UtilityCost | UtilityUsage): Contain the entire response
        """
        if hasattr(meter.reads[-2], "consumption"):
            final_value = meter.reads[-2].consumption.value
        else:
            final_value = meter.reads[-2].value

        _LOGGER.debug("Evaluating Reset: (%s>%s)", new_reset, self.last_reset)
        if self._attr_native_value and final_value > self._attr_native_value:
            _LOGGER.debug("Maxing meter at %s", final_value)
            self._update_state_attr(final_value, meter)
        else:
            _LOGGER.debug(
                "Resetting meter to 0 (%s<%s)", final_value, self._attr_native_value
            )
            self._update_state_attr(0, meter)
            self._attr_last_reset = new_reset

    # TODO: These two functions need reworked, I'm definitely overthinking it.

    def _update_meter(self, query: callable) -> None:
        try:
            # Use the billing cycle date as our backstop (attributes show all usages for the current billing cycle)
            start_date = date.today() - relativedelta(days=self.billing_day)
            _LOGGER.debug("Query Period start_date=%s", start_date)

            meter = query(self.uuid, start_date)
            new_reset = datetime.strptime(
                meter.reads[-1].end_time, "%Y-%m-%dT%H:%M:%S.%f%z"
            )

            if self.last_reset and new_reset > self.last_reset:
                self._reset_meter(new_reset, meter)
            else:
                if not self.last_reset and not self.state == 0:
                    _LOGGER.debug("Resetting meter to 0 (last_reset is None)")
                    self._update_state_attr(0, meter)
                    self._attr_last_reset = new_reset
                elif hasattr(meter.reads[-1], "consumption"):
                    self._update_state_attr(meter.reads[-1].consumption.value, meter)
                else:
                    self._update_state_attr(meter.reads[-1].value, meter)
        except Exception as exc:
            _LOGGER.warning("Caught exception: %s", exc.args)
            self._available = False


class DailyUsageSensor(PGEUsageSensor):
    """Sensor to monitor daily usage"""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._name = "PGE Reported Usage (daily)"
        self._unique_id = "daily"

    def update(self) -> None:
        """Get latest data for the sensor"""
        self._login(client=True)

        if not self.billing_day:
            self.get_billing_day()

        self._update_meter(self.opower_client.utility_cost_daily)


class HourlyUsageSensor(PGEUsageSensor):
    """Sensor to monitor hourly usage"""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._name = "PGE Reported Usage (hourly)"
        self._unique_id = "hourly"
        self.billing_day = 2

    def update(self) -> None:
        """Get latest data for the sensor"""

        self._login()
        self._update_meter(self.opower_client.utility_usage_hourly)
