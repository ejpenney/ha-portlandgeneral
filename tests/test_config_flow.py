"""Test the PGE config flow."""

from unittest.mock import AsyncMock, patch

import pytest

from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType

from custom_components.portland_general_electric.const import DOMAIN
from . import USER_INPUT

VALIDATE_AUTH_PATCH = "custom_components.portland_general_electric.config_flow.validate_auth"

pytestmark = pytest.mark.usefixtures("mock_setup_entry")


async def test_user_form(hass: HomeAssistant, mock_setup_entry: AsyncMock) -> None:
    """Test we get the user initiated form."""

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "user"
    assert result["errors"] == {}

    with patch(VALIDATE_AUTH_PATCH):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            USER_INPUT,
        )
        await hass.async_block_till_done()

    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["title"] == "user@example.com"
    assert result["data"] == {**USER_INPUT}

    assert len(mock_setup_entry.mock_calls) == 1


async def test_auth_failure(hass: HomeAssistant) -> None:
    """Test we get the authentication error for user flow."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )

    with patch(VALIDATE_AUTH_PATCH, return_value=False):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            USER_INPUT,
        )
        await hass.async_block_till_done()

    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "user"
    assert result["errors"]["base"] == "invalid_auth"
