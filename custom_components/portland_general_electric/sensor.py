"""PGE sensor platform."""
import logging
from datetime import timedelta
from typing import Callable, Optional
from portlandgeneral import OPowerApi, PortlandGeneralApi
import voluptuous as vol
import json
from datetime import date, datetime
from dateutil.relativedelta import relativedelta

from .const import ATTR_ACCOUNT_NUMBER, ATTR_RAW_DATA

from homeassistant.components.sensor import (
    PLATFORM_SCHEMA,
    SensorDeviceClass,
    SensorStateClass,
    SensorEntity,
    RestoreSensor,
)
from homeassistant.const import (
    CONF_USERNAME,
    CONF_PASSWORD,
    ATTR_UNIT_OF_MEASUREMENT,
    ENERGY_KILO_WATT_HOUR,
)
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.typing import (
    ConfigType,
    DiscoveryInfoType,
    HomeAssistantType,
)

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
    discovery_info: Optional[DiscoveryInfoType] = None,
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
    ]
    async_add_entities(sensors, update_before_add=True)


class PGEUsageSensor(RestoreSensor, SensorEntity):
    """Representation of a PGE sensor."""

    _attr_device_class = SensorDeviceClass.ENERGY
    _attr_state_class = SensorStateClass.TOTAL
    _attr_icon = "mdi:meter-electric"
    _state = None
    _available = True
    _name = None
    _unique_id = None

    def __init__(
        self,
        hass: HomeAssistantType,
        username: str,
        password: str,
    ):
        super().__init__()
        self.async_get_last_sensor_data()

        log_level = logging.getLevelName(_LOGGER.getEffectiveLevel())
        verbose = log_level == "DEBUG"
        _LOGGER.debug(f"log_level={log_level} and verbose={verbose}")

        self.opower_client = OPowerApi(verbose=verbose)
        self.client = PortlandGeneralApi(verbose=verbose)
        self._hass = hass
        self.username = username
        self.password = password
        self.uuid = None

        # if not hasattr(self, "_attr_last_reset"):
        #     self._attr_last_reset = None

        # self._attr_extra_state_attributes = {
        #     ATTR_ACCOUNT_NUMBER: self.uuid,
        #     ATTR_UNIT_OF_MEASUREMENT: ENERGY_KILO_WATT_HOUR,
        #     ATTR_RAW_DATA: None,
        # }

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

    @property
    def state(self) -> str:
        """Return the state of the sensor."""
        return self._state

    @property
    def available(self) -> str:
        """Return the availability of the sensor."""
        return self._available

    @property
    def name(self) -> str:
        """Return the name of the sensor."""
        return self._name

    def _update_state_attr(self, new_state: str, utility_reading: dict):
        self._attr_extra_state_attributes.update(
            {
                ATTR_ACCOUNT_NUMBER: self.uuid,
                ATTR_UNIT_OF_MEASUREMENT: ENERGY_KILO_WATT_HOUR,
                ATTR_RAW_DATA: json.loads(
                    json.dumps(
                        utility_reading,
                        default=lambda o: getattr(o, "__dict__", str(o)),
                    )
                ),
            }
        )

        _LOGGER.debug(f"Setting Meter to {new_state}")
        self._state = new_state
        self._available = True

    def _reset_meter(self, new_reset: datetime, final_value: str) -> None:
        # New readings won't be 0, in order to reset, first update after a new reading will be 0.  Future readings will increment adjust on a delay.

        _LOGGER.debug(f"Evaluating Reset: ({new_reset}>{self.last_reset})")
        # _LOGGER.debug(f"Evaluating Reset: ({new_reset}>{self._attr_last_reset})")
        if self._state and final_value > self._state:
            _LOGGER.debug(f"Maxing meter at {final_value})")
            self._update_state_attr(final_value)
        else:
            _LOGGER.debug(f"Resetting meter to 0 ({final_value}<{self._state})")
            # self._attr_last_reset = new_reset
            self._update_state_attr(0)


class DailyUsageSensor(PGEUsageSensor):
    # _attr_last_reset: datetime

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._name = f"PGE Reported Usage (daily)"
        self.billing_day = None
        self._unique_id = "daily"

    def get_billing_day(self) -> None:
        # Lookup how far we are into the billing cycle
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
        self.billing_day = tracker.details.billing_cycle_day
        _LOGGER.debug(f"Billing Day set to {self.billing_day}")

    def update(self) -> None:
        self._login(client=True)

        try:
            if not self.billing_day:
                self.get_billing_day()

            # Use the billing cycle date as our backstop (attributes show all usages for the current billing cycle)
            start_date = date.today() - relativedelta(days=self.billing_day)
            _LOGGER.debug(f"Billing Period start_date={start_date}")

            meter = self.opower_client.utility_cost_daily(
                self.uuid, start_date=start_date
            )
            new_reset = datetime.strptime(
                meter.reads[-1].end_time, "%Y-%m-%dT%H:%M:%S.%f%z"
            )

            # if new_reset != self._attr_last_reset:
            if self.last_reset and new_reset > self.last_reset:
                final_value = (
                    self.opower_client.utility_usage_daily(self.uuid)
                    .reads[-1]
                    .consumption.value
                )
                self._reset_meter(new_reset, final_value)
            else:
                self._update_state_attr(meter.reads[-1].value, meter)

        except Exception as exc:
            _LOGGER.warn(f"Caught exception: {exc.args}")
            self._login(client=True)
            self._available = False
            # self.update()


class HourlyUsageSensor(PGEUsageSensor):
    # _attr_last_reset: datetime

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._name = "PGE Reported Usage (hourly)"
        self._unique_id = "hourly"

    def update(self) -> None:
        # TODO: Another sensor for cost rate

        self._login()

        try:
            # Use the billing cycle date as our backstop (attributes show all usages for the current billing cycle)
            start_date = date.today() - relativedelta(days=2)
            _LOGGER.debug(f"Billing Period start_date={start_date}")

            meter = self.opower_client.utility_usage_hourly(
                self.uuid, start_date=start_date
            )

            new_reset = datetime.strptime(
                meter.reads[-1].end_time, "%Y-%m-%dT%H:%M:%S.%f%z"
            )

            # if new_reset != self._attr_last_reset:
            if self.last_reset and new_reset != self.last_reset:
                self._reset_meter(new_reset, meter.reads[-2].consumption.value)
            else:
                self._update_state_attr(meter.reads[-1].consumption.value, meter)

        except Exception as exc:
            _LOGGER.warn(f"Caught exception: {exc.args}")
            self._login()
            self._available = False
            # self.update()
