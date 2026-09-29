"""The Veeam ONE integration."""

from __future__ import annotations

import asyncio
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.typing import ConfigType

from veeam_one import VeeamAuthenticationError

from .const import DEFAULT_NAME, DOMAIN, UPDATE_TIMEOUT
from .coordinator import OPERATIONS, VeeamOneCoordinator
from .entity import resource_identifier
from .sdk import create_client, prepare_sdk
from .services import async_setup_services

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [Platform.SENSOR, Platform.BINARY_SENSOR]

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Register the integration's services."""
    async_setup_services(hass)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Veeam ONE."""
    await hass.async_add_executor_job(prepare_sdk, OPERATIONS)
    client = create_client(entry.data)
    try:
        await asyncio.wait_for(client.connect(), timeout=UPDATE_TIMEOUT)
    except VeeamAuthenticationError as err:
        await client.close()
        raise ConfigEntryAuthFailed("Invalid Veeam ONE credentials") from err
    except Exception as err:
        await client.close()
        raise ConfigEntryNotReady(f"Unable to connect to Veeam ONE: {err}") from err
    coordinator = VeeamOneCoordinator(hass, entry, client)
    try:
        await coordinator.async_config_entry_first_refresh()
    except Exception:
        await client.close()
        raise
    entry.runtime_data = coordinator
    coordinator.device_id = (
        dr.async_get(hass)
        .async_get_or_create(
            config_entry_id=entry.entry_id,
            identifiers={(DOMAIN, entry.entry_id)},
            name=DEFAULT_NAME,
            manufacturer="Veeam",
            model=DEFAULT_NAME,
            sw_version=coordinator.data.get("service", {}).get("version"),
        )
        .id
    )
    entry.async_on_unload(coordinator.async_add_listener(_pruner(hass, coordinator)))
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload Veeam ONE."""
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        await entry.runtime_data.client.close()
    return unloaded


async def async_migrate_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Migrate an entry to the current version."""
    if entry.version > 1:
        return False
    if entry.minor_version < 2:
        # 1.1 derived resource IDs from foreign keys and made a device per alarm. Clear its
        # entities and devices; setup recreates what still exists under stable IDs.
        entity_registry = er.async_get(hass)
        for entity in er.async_entries_for_config_entry(entity_registry, entry.entry_id):
            entity_registry.async_remove(entity.entity_id)
        device_registry = dr.async_get(hass)
        for device in dr.async_entries_for_config_entry(device_registry, entry.entry_id):
            device_registry.async_remove_device(device.id)
        hass.config_entries.async_update_entry(entry, minor_version=2)
        _LOGGER.info("Migrated Veeam ONE entry %s to version 1.2", entry.title)
    return True


async def async_remove_config_entry_device(
    hass: HomeAssistant, entry: ConfigEntry, device: dr.DeviceEntry
) -> bool:
    """Allow removing a resource device that Veeam ONE no longer reports."""
    coordinator: VeeamOneCoordinator = entry.runtime_data
    return not device.identifiers & _current_identifiers(coordinator)


def _current_identifiers(coordinator: VeeamOneCoordinator) -> set[tuple[str, str]]:
    identifiers = {(DOMAIN, coordinator.entry_id)}
    for key, items in coordinator.data.get("resources", {}).items():
        identifiers.update(
            (DOMAIN, resource_identifier(coordinator.entry_id, key, object_id))
            for object_id in items
        )
    return identifiers


def _pruner(hass: HomeAssistant, coordinator: VeeamOneCoordinator):
    """Remove devices for resources a successful fetch no longer returns."""

    @callback
    def _prune() -> None:
        if not coordinator.last_update_success:
            return
        current = _current_identifiers(coordinator)
        device_registry = dr.async_get(hass)
        for device in dr.async_entries_for_config_entry(device_registry, coordinator.entry_id):
            for domain, identifier in device.identifiers:
                if domain != DOMAIN or (domain, identifier) in current:
                    continue
                parts = identifier.split(":", 2)
                # Only prune collections fetched this cycle; a failed fetch proves nothing.
                if len(parts) == 3 and parts[1] in coordinator.fetched:
                    device_registry.async_update_device(
                        device.id, remove_config_entry_id=coordinator.entry_id
                    )

    return _prune
