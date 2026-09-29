"""Veeam ONE binary sensors."""

from __future__ import annotations

from datetime import datetime, timezone

from homeassistant.components.binary_sensor import BinarySensorDeviceClass, BinarySensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import COLLECTIONS, VeeamOneCoordinator, is_problem
from .entity import (
    ResourceEntity,
    VeeamOneEntity,
    add_entities_dynamically,
    parse_timestamp,
    populated_collections,
    resources,
)

PARALLEL_UPDATES = 0


class ConnectedSensor(VeeamOneEntity, BinarySensorEntity):
    """Whether the latest poll of the Veeam ONE API succeeded."""

    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY

    def __init__(self, coordinator: VeeamOneCoordinator) -> None:
        super().__init__(coordinator, "connected", "connected")

    @property
    def available(self) -> bool:
        return True

    @property
    def is_on(self) -> bool:
        return self.coordinator.last_update_success


class LicenseExpiredSensor(VeeamOneEntity, BinarySensorEntity):
    """Whether the license, or its support, has expired."""

    _attr_device_class = BinarySensorDeviceClass.PROBLEM

    def __init__(self, coordinator: VeeamOneCoordinator, field: str, key: str) -> None:
        super().__init__(coordinator, key, key)
        self.field = field

    @property
    def is_on(self) -> bool | None:
        expiration = parse_timestamp(self.coordinator.data.get("license", {}).get(self.field))
        if expiration is None:
            return None
        return expiration <= datetime.now(timezone.utc)


class CollectionProblemSensor(VeeamOneEntity, BinarySensorEntity):
    """Whether any resource in a collection reports a problem."""

    _attr_device_class = BinarySensorDeviceClass.PROBLEM

    def __init__(self, coordinator: VeeamOneCoordinator, key: str) -> None:
        super().__init__(
            coordinator,
            f"{key}_problem",
            "collection_problem",
            {"collection": COLLECTIONS[key].label},
        )
        self.key = key

    @property
    def is_on(self) -> bool | None:
        status_key = COLLECTIONS[self.key].status_key
        items = self.coordinator.data.get("resources", {}).get(self.key, {}).values()
        known = [p for item in items if (p := is_problem(item.get(status_key))) is not None]
        return any(known) if known else None


class ResourceProblemSensor(ResourceEntity, BinarySensorEntity):
    """Whether a resource's status reports a problem."""

    _attr_device_class = BinarySensorDeviceClass.PROBLEM

    def __init__(self, coordinator: VeeamOneCoordinator, key: str, object_id: str) -> None:
        super().__init__(coordinator, key, object_id, "problem", "problem")

    @property
    def is_on(self) -> bool | None:
        return is_problem(self.item().get(self.collection.status_key or ""))


def _entities(coordinator: VeeamOneCoordinator) -> list[VeeamOneEntity]:
    entities: list[VeeamOneEntity] = [
        ConnectedSensor(coordinator),
        LicenseExpiredSensor(coordinator, "expirationDate", "license_expired"),
        LicenseExpiredSensor(coordinator, "supportExpirationDate", "license_support_expired"),
    ]
    entities.extend(
        CollectionProblemSensor(coordinator, key)
        for key in populated_collections(coordinator)
        if COLLECTIONS[key].status_key
    )
    entities.extend(
        ResourceProblemSensor(coordinator, key, object_id)
        for key, object_id, _ in resources(coordinator)
        if COLLECTIONS[key].status_key
    )
    return entities


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up Veeam ONE binary sensors."""
    coordinator: VeeamOneCoordinator = entry.runtime_data
    add_entities_dynamically(coordinator, entry, async_add_entities, lambda: _entities(coordinator))
