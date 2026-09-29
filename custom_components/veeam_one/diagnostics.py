"""Diagnostics support for Veeam ONE."""

from __future__ import annotations

from collections import Counter
from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant

from .api_version import configured_api_version
from .coordinator import COLLECTIONS, VeeamOneCoordinator

TO_REDACT = {
    CONF_HOST,
    CONF_PASSWORD,
    CONF_USERNAME,
    "title",
    "unique_id",
    # License fields that identify the customer
    "company",
    "email",
    "supportId",
    "licenseId",
    "installationUid",
}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    coordinator: VeeamOneCoordinator = entry.runtime_data
    data = coordinator.data or {}
    return {
        "entry": async_redact_data(
            {
                "title": entry.title,
                "unique_id": entry.unique_id,
                "version": f"{entry.version}.{entry.minor_version}",
                "data": dict(entry.data),
                "options": dict(entry.options),
                # Both, because "auto" on its own answers nothing in a bug report
                "configured_api_version": configured_api_version(entry),
                "resolved_api_version": coordinator.api_version,
            },
            TO_REDACT,
        ),
        "coordinator": {
            "last_update_success": coordinator.last_update_success,
            "last_exception": repr(coordinator.last_exception)
            if coordinator.last_exception
            else None,
            "errors": coordinator.errors,
        },
        "service": async_redact_data(data.get("service", {}), TO_REDACT),
        "license": async_redact_data(data.get("license", {}), TO_REDACT),
        "license_usage": data.get("license_usage", {}),
        "alarms_by_status": dict(Counter(str(a.get("status")) for a in data.get("alarms", []))),
        "collections": {
            key: {
                "total": data.get("totals", {}).get(key),
                "devices": len(data.get("resources", {}).get(key, {})),
                "fetched": key in coordinator.fetched,
            }
            for key in COLLECTIONS
        },
    }
