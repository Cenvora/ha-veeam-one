"""Shared Veeam ONE entity helpers."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from datetime import datetime, timezone
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DEFAULT_NAME, DOMAIN
from .coordinator import COLLECTIONS, VeeamOneCoordinator, resource_name

# Alarm statuses that still need attention; Resolved, Success and Remediated alarms don't.
ACTIVE_ALARM_STATUSES = ("Error", "Warning")


def resource_identifier(entry_id: str, key: str, object_id: str) -> str:
    """Device identifier for a resource. Entry IDs and collection keys never contain ':'."""
    return f"{entry_id}:{key}:{object_id}"


def parse_timestamp(value: Any) -> datetime | None:
    """Parse an API timestamp, assuming UTC when it carries no zone."""
    if not value:
        return None
    if isinstance(value, datetime):
        result = value
    else:
        try:
            result = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except ValueError:
            return None
    return result if result.tzinfo else result.replace(tzinfo=timezone.utc)


def active_alarms(data: dict[str, Any], status: str | None = None) -> list[dict[str, Any]]:
    """Alarms still needing attention, optionally only those with one status."""
    wanted = (status,) if status else ACTIVE_ALARM_STATUSES
    return [alarm for alarm in data.get("alarms", []) if alarm.get("status") in wanted]


def add_entities_dynamically(
    coordinator: VeeamOneCoordinator,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
    build: Callable[[], Iterable[VeeamOneEntity]],
) -> None:
    """Add the entities `build` returns now and whenever an update brings new ones."""

    @callback
    def _add() -> None:
        new = [entity for entity in build() if entity.unique_id not in coordinator.known_ids]
        if new:
            coordinator.known_ids.update(entity.unique_id for entity in new if entity.unique_id)
            async_add_entities(new)

    _add()
    entry.async_on_unload(coordinator.async_add_listener(_add))


class VeeamOneEntity(CoordinatorEntity[VeeamOneCoordinator], Entity):
    """An entity on the Veeam ONE server device."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: VeeamOneCoordinator,
        key: str,
        translation_key: str,
        placeholders: dict[str, str] | None = None,
    ) -> None:
        super().__init__(coordinator)
        self._attr_translation_key = translation_key
        if placeholders:
            self._attr_translation_placeholders = placeholders
        self._attr_unique_id = f"{coordinator.entry_id}_{key}"

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={(DOMAIN, self.coordinator.entry_id)},
            name=DEFAULT_NAME,
            manufacturer="Veeam",
            model=DEFAULT_NAME,
            sw_version=self.coordinator.data.get("service", {}).get("version"),
        )

    async def async_will_remove_from_hass(self) -> None:
        # Forget the entity so it is re-added if its resource comes back.
        self.coordinator.known_ids.discard(self.unique_id or "")
        await super().async_will_remove_from_hass()


class ResourceEntity(VeeamOneEntity):
    """An entity on a resource's own device."""

    def __init__(
        self,
        coordinator: VeeamOneCoordinator,
        key: str,
        object_id: str,
        suffix: str,
        translation_key: str,
    ) -> None:
        super().__init__(coordinator, f"{key}_{object_id}_{suffix}", translation_key)
        self.collection_key = key
        self.collection = COLLECTIONS[key]
        self.object_id = object_id

    @property
    def device_info(self) -> DeviceInfo:
        item = self.item()
        return DeviceInfo(
            identifiers={
                (
                    DOMAIN,
                    resource_identifier(
                        self.coordinator.entry_id, self.collection_key, self.object_id
                    ),
                )
            },
            name=f"{DEFAULT_NAME} {resource_name(item, self.object_id)}",
            manufacturer="Veeam",
            model=self.collection.model,
            via_device_id=self.coordinator.device_id,
        )

    def item(self) -> dict[str, Any]:
        """This resource in the latest coordinator data."""
        resources = self.coordinator.data.get("resources", {}).get(self.collection_key, {})
        return resources.get(self.object_id, {})

    @property
    def available(self) -> bool:
        return super().available and bool(self.item())


def resources(coordinator: VeeamOneCoordinator) -> Iterable[tuple[str, str, dict[str, Any]]]:
    """Every (collection key, object ID, item) with its own device."""
    for key, items in coordinator.data.get("resources", {}).items():
        for object_id, item in items.items():
            yield key, object_id, item


def populated_collections(coordinator: VeeamOneCoordinator) -> list[str]:
    """Collections that have returned at least one resource."""
    totals = coordinator.data.get("totals", {})
    return [key for key in COLLECTIONS if totals.get(key)]
