"""PGE sensor platform."""
import logging
import json
from datetime import timedelta, date, datetime
from typing import Callable, Optional
from portlandgeneral import OPowerApi, PortlandGeneralApi
import voluptuous as vol
from dateutil.relativedelta import relativedelta

from homeassistant.components.sensor import (
    PLATFORM_SCHEMA,
    SensorDeviceClass,
    SensorStateClass,
    RestoreSensor,
    # ENTITY_ID_FORMAT,
)
from homeassistant.const import (
    CONF_USERNAME,
    CONF_PASSWORD,
    ENERGY_KILO_WATT_HOUR,
    CURRENCY_DOLLAR,
)
import homeassistant.helpers.config_validation as cv
from homeassistant.util import dt
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
        # HourlyUsageSensor(
        #     username=config[CONF_USERNAME],
        #     password=config[CONF_PASSWORD],
        #     hass=hass,
        # ),
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

    # TODO: Entity IDs are weird
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
    _attr_native_unit_of_measurement = f"{CURRENCY_DOLLAR}/{ENERGY_KILO_WATT_HOUR}"

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

    def _update_state_attr(self, new_state: str, utility_reading: dict, new_reset: datetime = None):
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
        if new_reset:
            _LOGGER.debug("Updating last_reset to %s", new_reset.isoformat())
            self._attr_last_reset = new_reset

    # TODO: This needs reworked, I'm definitely overthinking it.
    def _update_meter(self, query: callable) -> None:
        """Runs the update, determines what an appropriate value is

        Args:
            query (callable): Query we're running
        """
        # try:
        # Use the billing cycle date as our backstop
        start_date = date.today() - relativedelta(days=self.billing_day)
        _LOGGER.debug("Query Period start_date=%s", start_date)

        meter = query(self.uuid, start_date)

        # "Flatten" read time.
        # PGE read times run 17:00-17:00, but we reset at midnight
        curr_read_time = dt.start_of_local_day(
            (datetime.strptime(meter.reads[-1].end_time, "%Y-%m-%dT%H:%M:%S.%f%z")
            # PGE either lies about the read times or is perpetually 20 hours behind
            # Based on my observations: (consumption spikes during heat waves)
            # I believe PGE is lying about the read times.
            + relativedelta(days=1))
        )
        if hasattr(meter.reads[-1], "consumption"):
            final_read = meter.reads[-2].consumption.value
            this_read = meter.reads[-1].consumption.value
        else:
            final_read = meter.reads[-2].value
            this_read = meter.reads[-1].value
        now = dt.now()

        if curr_read_time > now:
            # Reading is in the future - PGE resets before midnight sometimes.
            # HASS gets confused if we reset before midnight.
            # So this reading will be "delayed".
            _LOGGER.debug("Postponing reset: (%s>%s)", curr_read_time, now.isoformat())
            self._update_state_attr(final_read, meter)
        elif self.last_reset and curr_read_time > self.last_reset:
            # We have a new (valid) reading, proceed cautiously
            _LOGGER.debug("Resetting: (%s>%s)", curr_read_time, self.last_reset)
            if (self._attr_native_value and self._attr_native_value == final_read):
                # Looks like we already stored the final value, time to reset
                _LOGGER.debug("Resetting, final read was %s", final_read)
                self._update_state_attr(0, meter, new_reset=curr_read_time)
            else:
                # PGE is using an appropriate timezone!
                # Store the final_value before resetting (happening next update)
                _LOGGER.debug("Maxing meter prior to reset")
                self._update_state_attr(final_read, meter)
        else:
            current_reset = None
            if not self.last_reset:
                # Rebooting, first run... Either way, zero out our last_reset at midnight
                _LOGGER.debug("Setting last_reset to midnight (last_reset is None")
                current_reset = dt.start_of_local_day()
            # We simply have an update, so store it!
            self._update_state_attr(this_read, meter, new_reset=current_reset)
        # except Exception as exc:
        #     _LOGGER.warning("Caught exception: %s", exc.args)
        #     self._available = False


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
