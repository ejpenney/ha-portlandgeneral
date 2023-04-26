"""Interacts directly with portlandgeneral-api"""

from datetime import date, datetime
import json
import logging

from dateutil.relativedelta import relativedelta
from homeassistant.components.sensor import (
    RestoreSensor,
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.const import CURRENCY_DOLLAR, ENERGY_KILO_WATT_HOUR
from homeassistant.core import HomeAssistant
from homeassistant.helpers.typing import HomeAssistantType
from homeassistant.util import dt
from portlandgeneral import OPowerApi

from .const import ATTR_ACCOUNT_NUMBER, ATTR_RAW_DATA, ATTR_TOTAL_USAGE, LOGGER


def validate_auth(username: str, password: str) -> bool:
    """Validate PGE credentials"""
    opower_client = OPowerApi()
    try:
        opower_client.login(username=username, password=password)
    except Exception:  # pylint: disable=broad-exception-caught
        return False

    return True


class PGEAuth:
    """Contains PGE authentication and user account details."""

    def __init__(self, username: str, password: str):
        log_level = logging.getLevelName(LOGGER.getEffectiveLevel())
        verbose = log_level == "DEBUG"
        LOGGER.debug("log_level=%s and verbose=%s", log_level, verbose)

        self.username = username
        self.password = password
        self.uuid = None
        self.opower_uuid = None
        self.opower_client = OPowerApi(verbose=verbose)

        # self._login()

    def login(self) -> None:
        """Trigger a login (refresh)."""
        self.opower_client.login(username=self.username, password=self.password)
        if not self.uuid or not self.opower_uuid:
            self.update_uuids()

    def update_uuids(self) -> None:
        """Retrieve UUIDs from the PGE APIs."""
        current_customers = self.opower_client.current_customers()

        self.opower_uuid = current_customers.uuid
        self.uuid = current_customers.utility_accounts[0].uuid


class PGEConnection(SensorEntity):
    """Contains a list of PGE Sensors."""

    def __init__(
        self,
        hass: HomeAssistant,
        username: str,
        password: str,
    ) -> None:
        """Store configuration."""
        self.sensors: list[PGESensor] = []
        self.hass = hass
        self.username = username
        self.password = password

    def update(self) -> bool:
        """Validate connection and retrieve a list of sensors."""
        self.sensors = [
            DailyUsageSensor(
                username=self.username,
                password=self.password,
                hass=self.hass,
            ),
            # HourlyUsageSensor(
            #     username=self.username,
            #     password=self.password,
            #     hass=hass,
            # ),
            CostSensor(
                username=self.username,
                password=self.password,
                hass=self.hass,
            ),
        ]
        return True


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
        self._attr_extra_state_attributes = {}
        self.pge_api = PGEAuth(username, password)
        self._hass = hass
        self._available = True
        self._name = None

    @property
    def unique_id(self) -> str:
        """Return the unique ID of the sensor."""
        return f"{self.pge_api.uuid}-{self._name.replace(' ', '_')}"

    @property
    def available(self):
        """Return if sensor is available."""
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
        present = datetime.now()
        billing_day = 1

        for bill in self.pge_api.opower_client.utility_billing_windows(
            self.pge_api.opower_uuid
        ).bills:
            start_date = datetime.strptime(bill.start_date, "%Y-%m-%dT%H:%M:%S.%fZ")
            end_date = datetime.strptime(bill.end_date, "%Y-%m-%dT%H:%M:%S.%fZ")

            if start_date < present < end_date + relativedelta(days=1):
                billing_day = (present - start_date).days
                break

            self.billing_day = billing_day
            LOGGER.debug("Billing Day set to %s", self.billing_day)


class CostSensor(PGESensor):
    """Representation of Cost"""

    _attr_icon = "mdi:currency-usd"
    _attr_native_unit_of_measurement = f"{CURRENCY_DOLLAR}/{ENERGY_KILO_WATT_HOUR}"

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._name = "PGE reported cost"

    def update(self):
        """Get latest data for the sensor"""
        self.pge_api.login()

        if not self.billing_day:
            self.get_billing_day()

        start_date = date.today() - relativedelta(days=31)
        LOGGER.debug("Query Period start_date=%s", start_date)

        try:
            meter = self.pge_api.opower_client.utility_cost_daily(
                self.pge_api.uuid, start_date
            )
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
        except Exception as exc:  # pylint: disable=broad-exception-caught
            LOGGER.warning("Caught exception: %s", exc.args)
            self.state = None
            return False
        return True


class PGEUsageSensor(PGESensor):
    """Representation of a PGE Usage Sensor"""

    _attr_device_class = SensorDeviceClass.ENERGY
    _attr_state_class = SensorStateClass.TOTAL
    _attr_icon = "mdi:meter-electric"
    _attr_native_unit_of_measurement = ENERGY_KILO_WATT_HOUR

    def _update_state_attr(
        self, new_state: str, utility_reading: dict, new_reset: datetime = None
    ):
        self._attr_extra_state_attributes.update(
            {
                ATTR_ACCOUNT_NUMBER: self.pge_api.uuid,
                ATTR_RAW_DATA: json.loads(
                    json.dumps(
                        utility_reading,
                        default=lambda o: getattr(o, "__dict__", str(o)),
                    )
                ),
            }
        )

        LOGGER.debug("Setting Meter to %s", new_state)
        self._attr_native_value = new_state
        self._available = True
        if new_reset:
            LOGGER.debug("Updating last_reset to %s", new_reset.isoformat())
            self._attr_last_reset = new_reset

    # TODO: This needs reworked, I'm definitely overthinking it.  # pylint: disable=fixme
    def _update_meter(self, query: callable) -> None:
        """Runs the update, determines what an appropriate value is

        Args:
            query (callable): Query we're running
        """
        # try:
        # Use the billing cycle date as our backstop
        start_date = date.today() - relativedelta(days=31)
        LOGGER.debug("Query Period start_date=%s", start_date)

        meter = query(self.pge_api.uuid, start_date)
        curr_read_time = dt.start_of_local_day(
            (
                datetime.strptime(meter.reads[-1].end_time, "%Y-%m-%dT%H:%M:%S.%f%z")
                # PGE either lies about the read times or is perpetually 20 hours behind
                # Based on my observations: (consumption spikes during heat waves)
                # I believe PGE is lying about the read times.
                + relativedelta(days=1)
            )
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
            LOGGER.debug("Postponing reset: (%s>%s)", curr_read_time, now.isoformat())
            self._update_state_attr(final_read, meter)
        elif self.last_reset and curr_read_time > self.last_reset:
            # We have a new (valid) reading, proceed cautiously
            LOGGER.debug("Resetting: (%s>%s)", curr_read_time, self.last_reset)
            if self._attr_native_value and self._attr_native_value == final_read:
                # Looks like we already stored the final value, time to reset
                LOGGER.debug("Resetting, final read was %s", final_read)
                self._update_state_attr(0, meter, new_reset=curr_read_time)
            else:
                # PGE is using an appropriate timezone!
                # Store the final_value before resetting (happening next update)
                LOGGER.debug("Maxing meter prior to reset")
                self._update_state_attr(final_read, meter)
        else:
            current_reset = None
            if not self.last_reset:
                # Rebooting, first run... Either way, zero out our last_reset at midnight
                LOGGER.debug("Setting last_reset to midnight (last_reset is None")
                current_reset = dt.start_of_local_day()
            # We simply have an update, so store it!
            self._update_state_attr(this_read, meter, new_reset=current_reset)


class DailyUsageSensor(PGEUsageSensor):
    """Sensor to monitor daily usage"""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._name = "PGE reported daily usage"

    def update(self) -> None:
        """Get latest data for the sensor"""
        try:
            self.pge_api.login()

            if not self.billing_day:
                self.get_billing_day()

            self._update_meter(self.pge_api.opower_client.utility_cost_daily)
        except Exception:  # pylint: disable=broad-exception-caught
            self.state = None
            return False
        return True


class HourlyUsageSensor(PGEUsageSensor):
    """Sensor to monitor hourly usage"""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._name = "PGE reported hourly usage"
        self.billing_day = 2

    def update(self) -> None:
        """Get latest data for the sensor"""

        try:
            self._update_meter(self.pge_api.opower_client.utility_usage_hourly)
        except Exception:  # pylint: disable=broad-exception-caught
            self.state = None
            return False
        return True
