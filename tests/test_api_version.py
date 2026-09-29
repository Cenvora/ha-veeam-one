"""API version resolution and the wrong-port probe."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from homeassistant.core import HomeAssistant
from veeam_one.discovery import RestApiEndpoint

from custom_components.veeam_one.api_version import (
    async_find_other_port,
    async_resolve_api_version,
)
from custom_components.veeam_one.sdk import revoke

DATA = {"host": "one.example", "port": 1239, "verify_ssl": False}
DETECT = "custom_components.veeam_one.api_version.detect_api_version"
PROBE = "custom_components.veeam_one.api_version.detect_rest_api"


async def test_explicit_version_skips_detection(hass: HomeAssistant) -> None:
    with patch(DETECT, AsyncMock()) as detect:
        assert await async_resolve_api_version(hass, DATA, "2.3") == "2.3"
    detect.assert_not_called()


async def test_auto_uses_the_detected_version(hass: HomeAssistant) -> None:
    with patch(DETECT, AsyncMock(return_value="2.3")) as detect:
        assert await async_resolve_api_version(hass, {**DATA, "api_version": "auto"}) == "2.3"
    assert detect.call_args.args == ("https://one.example:1239",)


async def test_unsupported_version_falls_back_to_detection(hass: HomeAssistant) -> None:
    with patch(DETECT, AsyncMock(return_value="2.3")) as detect:
        assert await async_resolve_api_version(hass, DATA, "9.9") == "2.3"
    detect.assert_awaited()


async def test_detection_failure_uses_the_default(hass: HomeAssistant) -> None:
    with patch(DETECT, AsyncMock(return_value=None)):
        assert await async_resolve_api_version(hass, DATA) == "2.3"
    with patch(DETECT, AsyncMock(side_effect=OSError("down"))):
        assert await async_resolve_api_version(hass, DATA) == "2.3"


async def test_other_port_is_reported(hass: HomeAssistant) -> None:
    endpoint = RestApiEndpoint(port=1239, api_version="2.3")
    with patch(PROBE, AsyncMock(return_value=endpoint)) as probe:
        assert await async_find_other_port(hass, {**DATA, "port": 443}) == 1239
    assert probe.call_args.kwargs["ports"] == [1239]


async def test_other_port_probe_is_best_effort(hass: HomeAssistant) -> None:
    # Already on the default port: nothing else to try
    with patch(PROBE, AsyncMock()) as probe:
        assert await async_find_other_port(hass, DATA) is None
    probe.assert_not_called()
    with patch(PROBE, AsyncMock(return_value=None)):
        assert await async_find_other_port(hass, {**DATA, "port": 443}) is None
    with patch(PROBE, AsyncMock(side_effect=OSError("down"))):
        assert await async_find_other_port(hass, {**DATA, "port": 443}) is None


async def test_revoke_sends_the_refresh_token() -> None:
    with patch("custom_components.veeam_one.sdk.fetch", AsyncMock()) as fetch:
        await revoke(SimpleNamespace(_refresh_token="r", package="veeam_one.v2_3"))
        assert fetch.call_args.kwargs["body"].token == "r"
        # A failure is swallowed; so is having no token at all
        fetch.side_effect = OSError("down")
        await revoke(SimpleNamespace(_refresh_token="r", package="veeam_one.v2_3"))
        fetch.reset_mock()
        await revoke(SimpleNamespace(_refresh_token=None, package="veeam_one.v2_3"))
        fetch.assert_not_called()
