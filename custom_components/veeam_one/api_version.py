"""Resolving which REST API version to talk to a server with.

The API Version option can hold AUTO_API_VERSION, an intent rather than a version: "use the
newest version this server serves". It is stored as-is and resolved during setup, so a
server upgrade — or a veeam-one release that adds a newer version — is picked up on the next
restart without anyone editing the entry.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.core import HomeAssistant
from homeassistant.helpers.httpx_client import get_async_client

from veeam_one.discovery import DEFAULT_PORTS, detect_api_version, detect_rest_api

from .const import (
    AUTO_API_VERSION,
    CONF_API_VERSION,
    CONF_VERIFY_SSL,
    DEFAULT_API_VERSION,
    DEFAULT_PORT,
    DEFAULT_VERIFY_SSL,
)
from .sdk import API_VERSIONS

_LOGGER = logging.getLogger(__name__)


def configured_api_version(entry: ConfigEntry) -> str:
    """The API version setting of an entry: options win over data. May be "auto"."""
    return entry.options.get(CONF_API_VERSION, entry.data.get(CONF_API_VERSION, AUTO_API_VERSION))


async def async_resolve_api_version(
    hass: HomeAssistant, data: Mapping[str, Any], configured: str | None = None
) -> str:
    """Resolve an API version setting, detecting it when it is auto.

    Detection probes the server's versioned paths without credentials, so it can run before
    the connection is validated. It is best-effort: when nothing useful answers, the static
    default is used rather than failing setup.
    """
    configured = configured or data.get(CONF_API_VERSION, AUTO_API_VERSION)
    if configured != AUTO_API_VERSION:
        if configured in API_VERSIONS:
            return configured
        _LOGGER.warning(
            "API version %s is not supported by the installed veeam-one; detecting instead",
            configured,
        )

    verify_ssl = data.get(CONF_VERIFY_SSL, DEFAULT_VERIFY_SSL)
    try:
        detected = await detect_api_version(
            f"https://{data[CONF_HOST]}:{data.get(CONF_PORT, DEFAULT_PORT)}",
            client=get_async_client(hass, verify_ssl=verify_ssl),
            versions=list(API_VERSIONS),
        )
    except Exception as err:  # noqa: BLE001 - detection must never fail setup
        _LOGGER.debug("API version detection failed: %r", err)
        detected = None

    if detected is None:
        _LOGGER.info(
            "Could not detect the API version of %s; using %s",
            data[CONF_HOST],
            DEFAULT_API_VERSION,
        )
        return DEFAULT_API_VERSION
    _LOGGER.debug("Detected API version %s on %s", detected, data[CONF_HOST])
    return detected


async def async_find_other_port(hass: HomeAssistant, data: Mapping[str, Any]) -> int | None:
    """Return a different port the Veeam ONE API answers on, or None.

    "Cannot connect" is often the wrong port rather than a wrong host or a firewall, so it
    is worth one probe to be able to say which.
    """
    others = [port for port in DEFAULT_PORTS if port != data[CONF_PORT]]
    if not others:
        return None
    verify_ssl = data.get(CONF_VERIFY_SSL, DEFAULT_VERIFY_SSL)
    try:
        endpoint = await detect_rest_api(
            data[CONF_HOST],
            ports=others,
            versions=list(API_VERSIONS),
            client=get_async_client(hass, verify_ssl=verify_ssl),
        )
    except Exception as err:  # noqa: BLE001 - a failed probe just means no advice to give
        _LOGGER.debug("Port probe failed: %r", err)
        return None
    return endpoint.port if endpoint else None
