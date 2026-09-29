"""Veeam ONE SDK helpers."""

from __future__ import annotations

import importlib
import logging
from collections.abc import Iterable, Mapping
from typing import Any

from veeam_one import VeeamAuthenticationError, VeeamClient
from veeam_one.versions import VERSION_TO_PACKAGE

from .const import API_VERSION

_LOGGER = logging.getLogger(__name__)

PACKAGE = VERSION_TO_PACKAGE[API_VERSION]


class VeeamOneApiError(Exception):
    """Veeam ONE answered a request with a non-success status."""


def create_client(data: Mapping[str, Any]) -> VeeamClient:
    """Create the Veeam ONE smart client."""
    return VeeamClient(
        host=f"https://{data['host']}:{data['port']}",
        username=data["username"],
        password=data["password"],
        api_version=API_VERSION,
        verify_ssl=data.get("verify_ssl", True),
        timeout=30.0,
    )


def prepare_sdk(operations: Iterable[str] = ()) -> None:
    """Import the SDK modules the integration uses.

    Blocking — imports read the filesystem — so it runs in an executor. The SDK resolves
    modules with importlib at call time, which would otherwise land on the event loop.
    """
    modules = [
        f"{PACKAGE}.client",
        f"{PACKAGE}.models",  # imports every model module eagerly
        f"{PACKAGE}.api.authentication.authentication_create_token",
        *(f"{PACKAGE}.api.{operation}" for operation in operations),
    ]
    for module in modules:
        try:
            importlib.import_module(module)
        except ImportError as err:
            _LOGGER.debug("Could not pre-import %s: %s", module, err)


async def fetch(client: VeeamClient, operation: str, **kwargs: Any) -> Any:
    """Call an operation and return its parsed body, raising on any non-2xx status.

    The generated `asyncio` functions return None for an error status instead of raising,
    which makes a failed endpoint indistinguishable from an empty one.
    """
    function = importlib.import_module(f"{PACKAGE}.api.{operation}").asyncio_detailed
    response = await client.call(function, **kwargs)
    status = int(response.status_code)
    if status == 401:
        raise VeeamAuthenticationError(f"{operation} returned HTTP 401")
    if not 200 <= status < 300:
        raise VeeamOneApiError(f"{operation} returned HTTP {status}")
    return response.parsed
