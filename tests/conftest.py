"""Define test fixtures for PGE."""

from collections.abc import Generator
from unittest.mock import AsyncMock, patch

import pytest

pytest_plugins = "pytest_homeassistant_custom_component"

@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Auto enable custom integration."""
    yield


@pytest.fixture
def mock_setup_entry() -> Generator[AsyncMock, None, None]:
    """Override async_setup_entry."""

    with patch(
        "custom_components.portland_general_electric.async_setup_entry", return_value=True
    ) as mock_entry:
        yield mock_entry
