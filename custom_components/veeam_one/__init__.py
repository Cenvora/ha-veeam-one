"""The Veeam ONE integration."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_PORT, CONF_USERNAME, Platform
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.typing import ConfigType

from veeam_one import VeeamAuthenticationError

from .api_version import async_resolve_api_version, configured_api_version
from .const import CONNECT_TIMEOUT, DEFAULT_NAME, DOMAIN, LICENSE_WARNING_DAYS
from .coordinator import OPERATIONS, VeeamOneCoordinator
from .entity import parse_timestamp, resource_identifier
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
    api_version = await async_resolve_api_version(hass, entry.data, configured_api_version(entry))
    await hass.async_add_executor_job(prepare_sdk, api_version, OPERATIONS)
    client = create_client(entry.data, api_version)
    try:
        async with asyncio.timeout(CONNECT_TIMEOUT):
            await client.connect()
    except VeeamAuthenticationError as err:
        await client.close()
        raise ConfigEntryAuthFailed(
            translation_domain=DOMAIN,
            translation_key="authentication_failed",
            translation_placeholders={"username": entry.data[CONF_USERNAME]},
        ) from err
    except Exception as err:
        await client.close()
        raise ConfigEntryNotReady(
            translation_domain=DOMAIN,
            translation_key="connection_error",
            translation_placeholders={
                "host": entry.data[CONF_HOST],
                "port": str(entry.data[CONF_PORT]),
                "error": str(err) or type(err).__name__,
            },
        ) from err
    coordinator = VeeamOneCoordinator(hass, entry, client, api_version)
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
    _check_license(hass, coordinator)
    entry.async_on_unload(coordinator.async_add_listener(lambda: _check_license(hass, coordinator)))
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload Veeam ONE."""
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        await entry.runtime_data.client.close()
    return unloaded


async def async_remove_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Clear the entry's repair issue. Not on unload, which also runs on every reload."""
    ir.async_delete_issue(hass, DOMAIN, license_issue_id(entry.entry_id))


def license_issue_id(entry_id: str) -> str:
    """Repair issue ID for one entry's license warning."""
    return f"license_expiration_{entry_id}"


@callback
def _check_license(hass: HomeAssistant, coordinator: VeeamOneCoordinator) -> None:
    """Raise a repair issue while the Veeam ONE license is expired or about to expire.

    Cleared automatically once the server reports a license that is good for longer.
    """
    issue_id = license_issue_id(coordinator.entry_id)
    expiration = parse_timestamp(coordinator.data.get("license", {}).get("expirationDate"))
    now = datetime.now(timezone.utc)
    if expiration is None or expiration - now > timedelta(days=LICENSE_WARNING_DAYS):
        ir.async_delete_issue(hass, DOMAIN, issue_id)
        return
    expired = expiration <= now
    ir.async_create_issue(
        hass,
        DOMAIN,
        issue_id,
        is_fixable=False,
        severity=ir.IssueSeverity.ERROR if expired else ir.IssueSeverity.WARNING,
        translation_key="license_expired" if expired else "license_expiring",
        translation_placeholders={
            "host": coordinator.config_entry.data[CONF_HOST],
            "date": expiration.date().isoformat(),
            "days": str((expiration - now).days),
        },
    )


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
