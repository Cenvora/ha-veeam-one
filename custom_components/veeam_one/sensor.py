"""Veeam ONE sensors."""
from __future__ import annotations

from typing import Any

from homeassistant.components.sensor import SensorEntity
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import COLLECTIONS, VeeamOneCoordinator
from .entity import VeeamOneEntity


def _status(item: dict[str, Any]) -> str:
    value = item.get("status") or item.get("state") or item.get("connectionState")
    return str(value).lower() if value is not None else ""


class OverviewSensor(CoordinatorEntity[VeeamOneCoordinator], SensorEntity):
    """Overall triggered alarm count."""

    _attr_has_entity_name = True
    _attr_name = "Triggered Alarms"
    _attr_icon = "mdi:alarm-light"

    def __init__(self, coordinator: VeeamOneCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.entry_id}_alarms"

    @property
    def native_value(self) -> int:
        return len(self.coordinator.data.get("alarms", []))

    @property
    def device_info(self) -> dict[str, Any]:
        return {
            "identifiers": {(DOMAIN, self.coordinator.entry_id)},
            "name": "Veeam ONE",
            "manufacturer": "Veeam",
            "model": "Veeam ONE",
        }


class CollectionSensor(CoordinatorEntity[VeeamOneCoordinator], SensorEntity):
    """Count resources exposed by a Veeam ONE API collection."""

    _attr_has_entity_name = True
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator: VeeamOneCoordinator, key: str) -> None:
        super().__init__(coordinator)
        self.key = key
        self.label = COLLECTIONS[key][0]
        self._attr_name = self.label
        self._attr_unique_id = f"{coordinator.entry_id}_{key}_count"
        self._attr_icon = "mdi:database-outline"

    @property
    def native_value(self) -> int:
        return len(self.coordinator.data.get("collections", {}).get(self.key, []))

    @property
    def device_info(self) -> dict[str, Any]:
        return {
            "identifiers": {(DOMAIN, self.coordinator.entry_id)},
            "name": "Veeam ONE",
            "manufacturer": "Veeam",
            "model": "Veeam ONE",
        }


class FailedCollectionSensor(CollectionSensor):
    """Count resources whose reported state is not successful/healthy."""

    def __init__(self, coordinator: VeeamOneCoordinator, key: str) -> None:
        super().__init__(coordinator, key)
        self._attr_name = f"{self.label} Not Healthy"
        self._attr_unique_id = f"{coordinator.entry_id}_{key}_not_healthy"
        self._attr_icon = "mdi:alert-circle-outline"

    @property
    def native_value(self) -> int:
        resources = self.coordinator.data.get("collections", {}).get(self.key, [])
        return sum(
            1
            for item in resources
            if _status(item)
            and not any(
                word in _status(item)
                for word in ("success", "successful", "normal", "connected", "online", "available", "ok")
            )
        )


class ObjectSensor(VeeamOneEntity, SensorEntity):
    """Detailed sensor for a selected resource."""

    def __init__(
        self,
        coordinator: VeeamOneCoordinator,
        kind: str,
        object_id: str,
        name: str,
        field: str,
        unit: str | None = None,
    ) -> None:
        super().__init__(coordinator, kind, object_id)
        self._attr_name = name
        self.field = field
        self._attr_unique_id = f"{coordinator.entry_id}_{kind}_{object_id}_{field}"
        self._attr_native_unit_of_measurement = unit

    def _item(self) -> dict[str, Any]:
        return next(
            (
                item
                for item in self.coordinator.data.get("collections", {}).get(self.kind, [])
                if str(item.get("id") or item.get("uid") or item.get("resourceId")) == self.object_id
            ),
            {},
        )

    @property
    def native_value(self) -> Any:
        return self._item().get(self.field)


async def async_setup_entry(hass: Any, entry: Any, async_add_entities: Any) -> None:
    """Set up Veeam ONE sensors."""
    coordinator: VeeamOneCoordinator = entry.runtime_data
    entities: list[SensorEntity] = [OverviewSensor(coordinator)]

    for key in COLLECTIONS:
        entities.append(CollectionSensor(coordinator, key))
        entities.append(FailedCollectionSensor(coordinator, key))

    async_add_entities(entities)
