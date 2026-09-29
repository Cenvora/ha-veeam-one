"""Veeam ONE services."""

from __future__ import annotations

import voluptuous as vol
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import config_validation as cv

from .const import (
    ATTR_ALARM_IDS,
    ATTR_COMMENT,
    ATTR_CONFIG_ENTRY_ID,
    DEFAULT_RESOLVE_COMMENT,
    DOMAIN,
    SERVICE_RESOLVE_ALARM,
)
from .coordinator import RESOLVE_ALARMS, VeeamOneCoordinator
from .sdk import fetch, model

RESOLVE_ALARM_SCHEMA = vol.Schema(
    {
        vol.Optional(ATTR_CONFIG_ENTRY_ID): cv.string,
        vol.Required(ATTR_ALARM_IDS): vol.All(cv.ensure_list, [vol.Coerce(int)], vol.Length(min=1)),
        vol.Optional(ATTR_COMMENT, default=DEFAULT_RESOLVE_COMMENT): cv.string,
    }
)


def _coordinator(hass: HomeAssistant, entry_id: str | None) -> VeeamOneCoordinator:
    entries = [
        entry
        for entry in hass.config_entries.async_entries(DOMAIN)
        if entry.state is ConfigEntryState.LOADED
        and (entry_id is None or entry.entry_id == entry_id)
    ]
    if len(entries) != 1:
        raise ServiceValidationError(
            translation_domain=DOMAIN,
            translation_key="multiple_entries" if entries else "no_loaded_entry",
        )
    return entries[0].runtime_data


def async_setup_services(hass: HomeAssistant) -> None:
    """Register the resolve_alarm service."""

    async def resolve_alarm(call: ServiceCall) -> None:
        coordinator = _coordinator(hass, call.data.get(ATTR_CONFIG_ENTRY_ID))
        request = model(
            coordinator.client,
            "resolve_multiple_triggered_alarms_request",
            "ResolveMultipleTriggeredAlarmsRequest",
        )
        try:
            await fetch(
                coordinator.client,
                RESOLVE_ALARMS,
                body=request(
                    triggered_alarm_ids=call.data[ATTR_ALARM_IDS],
                    comment=call.data[ATTR_COMMENT],
                ),
            )
        except Exception as err:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="resolve_failed",
                translation_placeholders={"error": str(err)},
            ) from err
        await coordinator.async_request_refresh()

    hass.services.async_register(
        DOMAIN, SERVICE_RESOLVE_ALARM, resolve_alarm, schema=RESOLVE_ALARM_SCHEMA
    )
