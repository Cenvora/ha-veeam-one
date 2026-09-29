"""Veeam ONE binary sensors."""

from __future__ import annotations

from typing import Any

from homeassistant.components.binary_sensor import BinarySensorDeviceClass, BinarySensorEntity
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import COLLECTIONS, VeeamOneCoordinator
from .entity import VeeamOneEntity, resource_id, resource_name
from .monitoring_binary_sensor import (\n    CollectionProblemSensor,\n    LicenseExpiredSensor,\n    LicenseSupportExpiredSensor,\n)


def _status(item: dict[str, Any]) -> str:
    for key in ("status", "state", "connectionState", "powerState", "bestPracticeCheckStatus"):
        if item.get(key) is not None:
            return str(item[key]).lower()
    return ""


def _healthy(status: str) -> bool:
    if not status:
        return True
    return any(
        value in status
        for value in (
            "success",
            "successful",
            "normal",
            "connected",
            "online",
            "available",
            "ok",
            "ready",
            "running",
        )
    )


class Connected(CoordinatorEntity[VeeamOneCoordinator], BinarySensorEntity):
    """Veeam ONE API connectivity."""

    _attr_has_entity_name = True
    _attr_name = "Connected"
    _attr_icon = "mdi:lan-connect"

    def __init__(self, coordinator: VeeamOneCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.entry_id}_connected"

    @property
    def is_on(self) -> bool:
        return self.coordinator.last_update_success

    @property
    def device_info(self) -> dict[str, Any]:
        return {
            "identifiers": {(DOMAIN, self.coordinator.entry_id)},
            "name": "Veeam ONE",
            "manufacturer": "Veeam",
            "model": "Veeam ONE",
        }


class ResourceProblemSensor(VeeamOneEntity, BinarySensorEntity):
    """Whether an individual Veeam ONE resource reports a problem."""

    _attr_device_class = BinarySensorDeviceClass.PROBLEM
    _attr_icon = "mdi:shield-check"

    def __init__(
        self, coordinator: VeeamOneCoordinator, kind: str, object_id: str, name: str
    ) -> None:
        super().__init__(coordinator, kind, object_id, name)
        self._attr_name = "Problem"
        self._attr_unique_id = f"{coordinator.entry_id}_{kind}_{object_id}_problem"

    @property
    def is_on(self) -> bool:
        status = _status(self.item())
        problem = not _healthy(status)
        self._attr_icon = "mdi:alert-circle" if problem else "mdi:shield-check"
        return problem


def _resource_entities(coordinator: VeeamOneCoordinator) -> list[ResourceProblemSensor]:
    entities = []
    for kind in COLLECTIONS:
        for item in coordinator.data.get("collections", {}).get(kind, []):
            object_id = resource_id(item)
            if object_id:
                entities.append(
                    ResourceProblemSensor(
                        coordinator, kind, object_id, resource_name(item, object_id)
                    )
                )
    return entities


async def async_setup_entry(hass: Any, entry: Any, async_add_entities: Any) -> None:
    """Set up connectivity and per-resource problem sensors."""
    coordinator: VeeamOneCoordinator = entry.runtime_data
    async_add_entities([
        Connected(coordinator),
        LicenseExpiredSensor(coordinator),
        LicenseSupportExpiredSensor(coordinator),
        *(CollectionProblemSensor(coordinator, key) for key in COLLECTIONS),
    ])

    entities = _resource_entities(coordinator)
    async_add_entities(entities)
    known = {entity.unique_id for entity in entities if entity.unique_id}

    def _sync() -> None:
        new_entities = []
        for entity in _resource_entities(coordinator):
            if entity.unique_id and entity.unique_id not in known:
                known.add(entity.unique_id)
                new_entities.append(entity)
        if new_entities:
            async_add_entities(new_entities)

    entry.async_on_unload(coordinator.async_add_listener(_sync))
