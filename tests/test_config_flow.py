"""Config, reauth, reconfigure and options flows."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry
from veeam_one import VeeamAuthenticationError

from custom_components.veeam_one.const import DOMAIN

USER_INPUT = {
    "host": "one.example",
    "port": 1239,
    "username": "user",
    "password": "pass",
    "verify_ssl": False,
}


@pytest.fixture
def client():
    """The Veeam client the flow creates; connects successfully unless told otherwise."""
    client = MagicMock()
    client.connect = AsyncMock()
    client.close = AsyncMock()
    with (
        patch("custom_components.veeam_one.config_flow.create_client", return_value=client),
        patch("custom_components.veeam_one.config_flow.revoke", AsyncMock()),
        patch(
            "custom_components.veeam_one.api_version.detect_api_version",
            AsyncMock(return_value="2.3"),
        ),
        patch(
            "custom_components.veeam_one.config_flow.async_find_other_port",
            AsyncMock(return_value=None),
        ) as other_port,
        patch("custom_components.veeam_one.async_setup_entry", return_value=True),
    ):
        client.other_port = other_port
        yield client


def _entry(hass: HomeAssistant, **data) -> MockConfigEntry:
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={**USER_INPUT, "api_version": "auto", **data},
        unique_id="one.example:1239",
        minor_version=2,
    )
    entry.add_to_hass(hass)
    return entry


async def test_user_flow_creates_entry(hass: HomeAssistant, client) -> None:
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {**USER_INPUT, "api_version": "auto"}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Veeam ONE (one.example)"
    # "auto" is stored as the intent, not the version it resolved to
    assert result["data"]["api_version"] == "auto"
    client.close.assert_awaited()


@pytest.mark.parametrize(
    ("error", "other_port", "expected"),
    [
        (VeeamAuthenticationError("no"), None, "invalid_auth"),
        (OSError("refused"), None, "cannot_connect"),
        (OSError("refused"), 1240, "wrong_port"),
    ],
)
async def test_user_flow_errors_then_recovers(
    hass: HomeAssistant, client, error, other_port, expected
) -> None:
    client.connect.side_effect = error
    client.other_port.return_value = other_port
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(result["flow_id"], USER_INPUT)
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": expected}
    if other_port:
        assert result["description_placeholders"]["wrong_port"] == "1240"

    client.connect.side_effect = None
    result = await hass.config_entries.flow.async_configure(result["flow_id"], USER_INPUT)
    assert result["type"] is FlowResultType.CREATE_ENTRY


async def test_user_flow_unexpected_error(hass: HomeAssistant, client) -> None:
    with patch(
        "custom_components.veeam_one.config_flow.validate_input", side_effect=ValueError("boom")
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
        result = await hass.config_entries.flow.async_configure(result["flow_id"], USER_INPUT)
    assert result["errors"] == {"base": "unknown"}


async def test_user_flow_aborts_on_duplicate(hass: HomeAssistant, client) -> None:
    _entry(hass)
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(result["flow_id"], USER_INPUT)
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_reauth_updates_credentials(hass: HomeAssistant, client) -> None:
    entry = _entry(hass)
    result = await entry.start_reauth_flow(hass)
    assert result["step_id"] == "reauth_confirm"

    client.connect.side_effect = VeeamAuthenticationError("no")
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"username": "user", "password": "wrong"}
    )
    assert result["errors"] == {"base": "invalid_auth"}

    client.connect.side_effect = None
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"username": "other", "password": "new"}
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reauth_successful"
    assert entry.data["username"] == "other"
    assert entry.data["password"] == "new"
    assert entry.data["host"] == "one.example"


async def test_reconfigure_moves_to_another_server(hass: HomeAssistant, client) -> None:
    entry = _entry(hass)
    result = await entry.start_reconfigure_flow(hass)
    assert result["step_id"] == "reconfigure"
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {**USER_INPUT, "host": "one2.example", "port": 1300}
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"
    assert entry.unique_id == "one2.example:1300"
    assert entry.data["host"] == "one2.example"
    assert entry.title == "Veeam ONE (one2.example)"
    # The API version setting survives a reconfigure
    assert entry.data["api_version"] == "auto"


async def test_reconfigure_refuses_a_server_another_entry_has(hass: HomeAssistant, client) -> None:
    entry = _entry(hass)
    MockConfigEntry(
        domain=DOMAIN, data={**USER_INPUT, "host": "taken"}, unique_id="taken:1239"
    ).add_to_hass(hass)
    result = await entry.start_reconfigure_flow(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {**USER_INPUT, "host": "taken"}
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_reconfigure_reports_connection_errors(hass: HomeAssistant, client) -> None:
    entry = _entry(hass)
    client.connect.side_effect = OSError("refused")
    result = await entry.start_reconfigure_flow(hass)
    result = await hass.config_entries.flow.async_configure(result["flow_id"], USER_INPUT)
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "cannot_connect"}


async def test_options_flow_stores_api_version(hass: HomeAssistant, client) -> None:
    entry = _entry(hass)
    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["step_id"] == "init"
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"api_version": "2.3"}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert entry.options == {"api_version": "2.3"}


async def test_options_flow_reports_errors(hass: HomeAssistant, client) -> None:
    entry = _entry(hass, api_version="9.9")
    client.connect.side_effect = VeeamAuthenticationError("no")
    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"api_version": "auto"}
    )
    assert result["errors"] == {"base": "invalid_auth"}
