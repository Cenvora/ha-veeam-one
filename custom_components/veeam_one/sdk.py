"""Veeam ONE SDK helpers."""

from __future__ import annotations

import importlib
import logging
import ssl
from collections.abc import Iterable, Mapping
from typing import Any

from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_PORT, CONF_USERNAME
from homeassistant.util.ssl import get_default_context, get_default_no_verify_context

from veeam_one import VeeamAuthenticationError, VeeamClient
from veeam_one.versions import VERSION_TO_PACKAGE

from .const import CONF_VERIFY_SSL, DEFAULT_VERIFY_SSL, REQUEST_TIMEOUT

_LOGGER = logging.getLogger(__name__)

# API versions this veeam-one can speak, newest last
API_VERSIONS = tuple(VERSION_TO_PACKAGE)

REVOKE_TOKEN = "authentication.authentication_revoke_token"


class VeeamOneApiError(Exception):
    """Veeam ONE answered a request with a non-success status."""


def ssl_context(verify_ssl: bool) -> ssl.SSLContext:
    """Home Assistant's shared SSL context.

    httpx would otherwise build its own and load the CA bundle from disk inside the
    event loop.
    """
    return get_default_context() if verify_ssl else get_default_no_verify_context()


def create_client(data: Mapping[str, Any], api_version: str) -> VeeamClient:
    """Create the Veeam ONE smart client."""
    return VeeamClient(
        host=f"https://{data[CONF_HOST]}:{data[CONF_PORT]}",
        username=data[CONF_USERNAME],
        password=data[CONF_PASSWORD],
        api_version=api_version,
        verify_ssl=ssl_context(data.get(CONF_VERIFY_SSL, DEFAULT_VERIFY_SSL)),
        timeout=REQUEST_TIMEOUT,
    )


def prepare_sdk(api_version: str, operations: Iterable[str] = ()) -> None:
    """Import the SDK modules the integration uses.

    Blocking — imports read the filesystem — so it runs in an executor. The SDK resolves
    modules with importlib at call time, which would otherwise land on the event loop.
    """
    package = VERSION_TO_PACKAGE[api_version]
    modules = [
        f"{package}.client",
        f"{package}.models",  # imports every model module eagerly
        f"{package}.api.authentication.authentication_create_token",
        f"{package}.api.{REVOKE_TOKEN}",
        *(f"{package}.api.{operation}" for operation in operations),
    ]
    for module in modules:
        try:
            importlib.import_module(module)
        except ImportError as err:
            _LOGGER.debug("Could not pre-import %s: %s", module, err)


def model(client: VeeamClient, name: str, cls: str) -> Any:
    """A generated model class from the client's API version (already imported)."""
    return getattr(importlib.import_module(f"{client.package}.models.{name}"), cls)


async def fetch(client: VeeamClient, operation: str, **kwargs: Any) -> Any:
    """Call an operation and return its parsed body, raising on any non-2xx status.

    The generated `asyncio` functions return None for an error status instead of raising,
    which makes a failed endpoint indistinguishable from an empty one.
    """
    function = importlib.import_module(f"{client.package}.api.{operation}").asyncio_detailed
    response = await client.call(function, **kwargs)
    status = int(response.status_code)
    if status == 401:
        raise VeeamAuthenticationError(f"{operation} returned HTTP 401")
    if not 200 <= status < 300:
        raise VeeamOneApiError(f"{operation} returned HTTP {status}")
    return response.parsed


async def revoke(client: VeeamClient) -> None:
    """Revoke the client's refresh token, so a validation login leaves no session behind."""
    token = getattr(client, "_refresh_token", None)
    if not token:
        return
    body = model(
        client, "authentication_revoke_token_data_body", "AuthenticationRevokeTokenDataBody"
    )
    try:
        await fetch(client, REVOKE_TOKEN, body=body(token=token))
    except Exception as err:  # noqa: BLE001 - revoking is a courtesy
        _LOGGER.debug("Could not revoke the validation token: %s", err)
