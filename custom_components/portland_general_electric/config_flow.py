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


DATA_SCHEMA = vol.Schema(
    {
        vol.Required(
            CONF_USERNAME,
        ): str,
        vol.Required(
            CONF_PASSWORD,
        ): str,
    }
)


class PGEFlowHandler(ConfigFlow, domain=DOMAIN):
    """Config flow for PGE."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle a flow initialized by the user."""
        errors: dict[str, str] = {}

        if user_input is not None:
            self._async_abort_entries_match(
                {CONF_USERNAME: user_input[CONF_USERNAME]}
            )

            if await self.hass.async_add_executor_job(
                validate_auth,
                user_input.get(CONF_USERNAME),
                user_input.get(CONF_PASSWORD),
            ):
                # Storing data in option, to allow for changing them later
                # using an options flow.
                return self.async_create_entry(
                    title=user_input.get(CONF_NAME, user_input[CONF_USERNAME]),
                    data={
                        CONF_PASSWORD: user_input[CONF_PASSWORD],
                        CONF_USERNAME: user_input.get(CONF_USERNAME),
                    },
                )
            errors["base"] = "invalid_auth"

        return self.async_show_form(
            step_id="user",
            data_schema=self.add_suggested_values_to_schema(DATA_SCHEMA, user_input),
            errors=errors,
        )
