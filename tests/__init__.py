"""Tests for the PGE Integration."""

from homeassistant.const import CONF_PASSWORD, CONF_USERNAME

USER_INPUT = {
    CONF_PASSWORD: "redacted",
    CONF_USERNAME: "user@example.com",
}


def get_schema_suggestion(schema, key):
    """Get suggested value for key in voluptuous schema."""
    for k in schema:
        if k == key:
            if k.description is None or "suggested_value" not in k.description:
                return None
            return k.description["suggested_value"]
