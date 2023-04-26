"""Config flow to configure the Portland General Electric integration."""
from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigFlow
from homeassistant.const import CONF_NAME, CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResult

from .const import DOMAIN
from .pge_api import validate_auth


DATA_SCHEMA = {
    vol.Required(
        CONF_USERNAME,
    ): str,
    vol.Required(
        CONF_PASSWORD,
    ): str,
}

async def async_validate_credentials(
    hass: HomeAssistant, user_input: dict[str, Any]
) -> dict[str, str]:
    """Manage PGE options."""
    errors = {}
    result = await hass.async_add_executor_job(
        validate_auth,
        user_input.get(CONF_USERNAME),
        user_input[CONF_PASSWORD],
    )

    if not result:
        errors["base"] = "cannot_connect"

    return errors


class PGEFlowHandler(ConfigFlow, domain=DOMAIN):
    """Config flow for PGE."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle a flow initialized by the user."""
        if user_input is not None:
            return await self.async_validate_input(user_input)

        user_input = {}
        return self.async_show_form(
            step_id="user",
            data_schema=self.add_suggested_values_to_schema(DATA_SCHEMA, user_input),
        )

    async def async_validate_input(self, user_input: dict[str, Any]) -> FlowResult:
        """Check form inputs for errors."""
        errors = await async_validate_credentials(self.hass, user_input)
        if not errors:
            self._async_abort_entries_match(
                {CONF_USERNAME: user_input[CONF_USERNAME]}
            )

            # Storing data in option, to allow for changing them later
            # using an options flow.
            return self.async_create_entry(
                title=user_input.get(CONF_NAME, user_input[CONF_USERNAME]),
                data={},
                options={
                    CONF_PASSWORD: user_input[CONF_PASSWORD],
                    CONF_USERNAME: user_input.get(CONF_USERNAME),
                },
            )

        return self.async_show_form(
            step_id="user",
            data_schema=self.add_suggested_values_to_schema(DATA_SCHEMA, user_input),
            errors=errors,
        )
