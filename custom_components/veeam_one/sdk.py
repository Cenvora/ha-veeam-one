"""Veeam ONE SDK helpers."""

from __future__ import annotations

from typing import Any

from veeam_one import VeeamClient


def create_client(data: dict[str, Any]) -> VeeamClient:
    """Create the Veeam ONE smart client."""
    return VeeamClient(
        host=f"https://{data['host']}:{data['port']}",
        username=data["username"],
        password=data["password"],
        api_version="2.3",
        verify_ssl=data.get("verify_ssl", True),
        timeout=30.0,
    )
