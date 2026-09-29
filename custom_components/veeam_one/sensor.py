"""Veeam ONE sensors."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorStateClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import PERCENTAGE, EntityCategory, UnitOfInformation, UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import COLLECTIONS, VeeamOneCoordinator, is_problem
from .entity import (
    ResourceEntity,
    VeeamOneEntity,
    active_alarms,
    add_entities_dynamically,
    parse_timestamp,
    populated_collections,
    resources,
)

PARALLEL_UPDATES = 0

# Licensed sockets are 0 on instance-based licenses, which is most of them
DISABLED_LICENSE_FIELDS = {"sockets"}

# Alarm list attribute is capped so a flood of alarms can't bloat the recorder.
MAX_ALARM_ATTRIBUTES = 50


class VersionSensor(VeeamOneEntity, SensorEntity):
    """Installed Veeam ONE version."""

    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator: VeeamOneCoordinator) -> None:
        super().__init__(coordinator, "version", "version")

    @property
    def native_value(self) -> str | None:
        return self.coordinator.data.get("service", {}).get("version")


class AlarmCountSensor(VeeamOneEntity, SensorEntity):
    """Triggered alarms still needing attention, overall or for one status."""

    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coordinator: VeeamOneCoordinator, status: str | None) -> None:
        label = status or "Active"
        super().__init__(coordinator, f"{label.lower()}_alarms", f"{label.lower()}_alarms")
        self.status = status

    @property
    def native_value(self) -> int:
        return len(active_alarms(self.coordinator.data, self.status))

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        if self.status:
            return None
        alarms = sorted(
            active_alarms(self.coordinator.data),
            key=lambda alarm: str(alarm.get("triggeredTime") or ""),
            reverse=True,
        )
        return {
            "alarms": [
                {
                    "id": alarm.get("triggeredAlarmId"),
                    "name": alarm.get("name"),
                    "status": alarm.get("status"),
                    "triggered": alarm.get("triggeredTime"),
                    "object": (alarm.get("alarmSource") or {}).get("objectName"),
                    "description": alarm.get("description"),
                    "repeat_count": alarm.get("repeatCount"),
                }
                for alarm in alarms[:MAX_ALARM_ATTRIBUTES]
            ]
        }


class LicenseSensor(VeeamOneEntity, SensorEntity):
    """A field of the installed Veeam ONE license."""

    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator: VeeamOneCoordinator, field: str) -> None:
        super().__init__(coordinator, f"license_{field}", f"license_{field}")
        if field in DISABLED_LICENSE_FIELDS:
            self._attr_entity_registry_enabled_default = False
        self.field = field

    @property
    def native_value(self) -> Any:
        value = self.coordinator.data.get("license", {}).get(self.field)
        return value if isinstance(value, (str, int, float)) else None


class LicenseDaysRemainingSensor(VeeamOneEntity, SensorEntity):
    """Days until the license or its support expires; negative once expired."""

    _attr_device_class = SensorDeviceClass.DURATION
    _attr_native_unit_of_measurement = UnitOfTime.DAYS

    def __init__(
        self, coordinator: VeeamOneCoordinator, field: str, key: str, translation_key: str
    ) -> None:
        super().__init__(coordinator, key, translation_key)
        self.field = field

    @property
    def native_value(self) -> int | None:
        expiration = parse_timestamp(self.coordinator.data.get("license", {}).get(self.field))
        if expiration is None:
            return None
        return (expiration - datetime.now(timezone.utc)).days


def _number(value: Any) -> float | int | None:
    """License usage values arrive as strings; convert them."""
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return int(number) if number.is_integer() else number


def _license_unit(data: dict[str, Any], unit: str) -> dict[str, Any]:
    for item in data.get("license_usage", {}).get("units") or []:
        if item.get("licenseUnit") == unit:
            return item
    return {}


class LicenseUsageSensor(VeeamOneEntity, SensorEntity):
    """Used or licensed amount of one license unit (instances, sockets, points)."""

    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coordinator: VeeamOneCoordinator, unit: str, field: str) -> None:
        super().__init__(
            coordinator, f"license_{unit.lower()}_{field}", f"license_unit_{field}", {"unit": unit}
        )
        self.unit = unit
        self.field = field

    @property
    def native_value(self) -> float | int | None:
        return _number(_license_unit(self.coordinator.data, self.unit).get(self.field))


class LicenseUsagePercentageSensor(VeeamOneEntity, SensorEntity):
    """Share of one license unit in use."""

    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coordinator: VeeamOneCoordinator, unit: str) -> None:
        super().__init__(
            coordinator,
            f"license_{unit.lower()}_percentage",
            "license_unit_used_percentage",
            {"unit": unit},
        )
        self.unit = unit

    @property
    def native_value(self) -> float | None:
        unit = _license_unit(self.coordinator.data, self.unit)
        used, licensed = _number(unit.get("used")), _number(unit.get("licensed"))
        if used is None or not licensed:
            return None
        return round(used * 100 / licensed, 1)


class CollectionCountSensor(VeeamOneEntity, SensorEntity):
    """Number of resources Veeam ONE reports in a collection."""

    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coordinator: VeeamOneCoordinator, key: str) -> None:
        super().__init__(
            coordinator, f"{key}_count", "collection_count", {"collection": COLLECTIONS[key].label}
        )
        self.key = key

    @property
    def native_value(self) -> int | None:
        return self.coordinator.data.get("totals", {}).get(self.key)


class CollectionHealthSensor(VeeamOneEntity, SensorEntity):
    """Share of a collection's resources with a known, healthy status."""

    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coordinator: VeeamOneCoordinator, key: str) -> None:
        super().__init__(
            coordinator,
            f"{key}_health",
            "collection_health",
            {"collection": COLLECTIONS[key].label},
        )
        self.key = key

    @property
    def native_value(self) -> float | None:
        status_key = COLLECTIONS[self.key].status_key
        items = self.coordinator.data.get("resources", {}).get(self.key, {}).values()
        known = [p for item in items if (p := is_problem(item.get(status_key))) is not None]
        if not known:
            return None
        return round(known.count(False) * 100 / len(known), 1)


class ResourceStatusSensor(ResourceEntity, SensorEntity):
    """Reported status of a resource; its remaining fields are attributes."""

    def __init__(self, coordinator: VeeamOneCoordinator, key: str, object_id: str) -> None:
        super().__init__(coordinator, key, object_id, "status", "status")

    @property
    def native_value(self) -> str | None:
        value = self.item().get(self.collection.status_key or "")
        return None if value is None else str(value)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        promoted = {self.collection.status_key, *FIELDS}
        return {key: value for key, value in self.item().items() if key not in promoted}


@dataclass(frozen=True, slots=True)
class Field:
    """A resource field promoted to its own sensor."""

    translation_key: str
    unit: str | None = None
    device_class: SensorDeviceClass | None = None
    category: EntityCategory | None = None
    enabled_default: bool = True


DURATION = SensorDeviceClass.DURATION
DATA_SIZE = SensorDeviceClass.DATA_SIZE
DIAGNOSTIC = EntityCategory.DIAGNOSTIC

FIELDS: dict[str, Field] = {
    "lastRun": Field("last_run", device_class=SensorDeviceClass.TIMESTAMP),
    "lastRunDurationSec": Field("last_run_duration", UnitOfTime.SECONDS, DURATION),
    "avgDurationSec": Field(
        "average_run_duration", UnitOfTime.SECONDS, DURATION, DIAGNOSTIC, enabled_default=False
    ),
    "lastTransferredDataBytes": Field("last_transferred_data", UnitOfInformation.BYTES, DATA_SIZE),
    "processedItems": Field("processed_items", category=DIAGNOSTIC, enabled_default=False),
    "capacityBytes": Field("capacity", UnitOfInformation.BYTES, DATA_SIZE),
    "freeSpaceBytes": Field("free_space", UnitOfInformation.BYTES, DATA_SIZE),
    "usedSpaceBytes": Field("used_space", UnitOfInformation.BYTES, DATA_SIZE),
    "runningTasks": Field("running_tasks", category=DIAGNOSTIC, enabled_default=False),
    "outOfSpaceInDays": Field("days_until_out_of_space", UnitOfTime.DAYS, DURATION),
}


class ResourceFieldSensor(ResourceEntity, SensorEntity):
    """A numeric or timestamp field of a resource."""

    def __init__(
        self, coordinator: VeeamOneCoordinator, key: str, object_id: str, field: str
    ) -> None:
        spec = FIELDS[field]
        super().__init__(coordinator, key, object_id, field, spec.translation_key)
        self.field = field
        self._attr_native_unit_of_measurement = spec.unit
        self._attr_device_class = spec.device_class
        self._attr_entity_category = spec.category
        self._attr_entity_registry_enabled_default = spec.enabled_default
        if spec.device_class != SensorDeviceClass.TIMESTAMP:
            self._attr_state_class = SensorStateClass.MEASUREMENT
        if spec.device_class == SensorDeviceClass.DATA_SIZE:
            self._attr_suggested_unit_of_measurement = UnitOfInformation.GIBIBYTES

    @property
    def native_value(self) -> Any:
        value = self.item().get(self.field)
        if self.device_class == SensorDeviceClass.TIMESTAMP:
            return parse_timestamp(value)
        return value if isinstance(value, (int, float)) else None


class ResourceFreePercentSensor(ResourceEntity, SensorEntity):
    """Free space as a share of capacity."""

    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coordinator: VeeamOneCoordinator, key: str, object_id: str) -> None:
        super().__init__(coordinator, key, object_id, "free_percent", "free_space_percentage")

    @property
    def native_value(self) -> float | None:
        item = self.item()
        capacity, free = item.get("capacityBytes"), item.get("freeSpaceBytes")
        if not isinstance(capacity, (int, float)) or not capacity:
            return None
        if not isinstance(free, (int, float)):
            return None
        return round(free * 100 / capacity, 1)


def _entities(coordinator: VeeamOneCoordinator) -> list[VeeamOneEntity]:
    entities: list[VeeamOneEntity] = [
        VersionSensor(coordinator),
        AlarmCountSensor(coordinator, None),
        *(AlarmCountSensor(coordinator, status) for status in ("Error", "Warning")),
        *(
            LicenseSensor(coordinator, field)
            for field in ("type", "package", "company", "instances", "sockets")
        ),
        LicenseDaysRemainingSensor(
            coordinator, "expirationDate", "license_expiration_days", "license_days_remaining"
        ),
        LicenseDaysRemainingSensor(
            coordinator,
            "supportExpirationDate",
            "license_support_expiration_days",
            "license_support_days_remaining",
        ),
    ]
    for unit in coordinator.data.get("license_usage", {}).get("units") or []:
        if name := unit.get("licenseUnit"):
            entities.extend(
                (
                    LicenseUsageSensor(coordinator, name, "used"),
                    LicenseUsageSensor(coordinator, name, "licensed"),
                    LicenseUsagePercentageSensor(coordinator, name),
                )
            )
    for key in populated_collections(coordinator):
        entities.append(CollectionCountSensor(coordinator, key))
        if COLLECTIONS[key].status_key:
            entities.append(CollectionHealthSensor(coordinator, key))
    for key, object_id, item in resources(coordinator):
        if COLLECTIONS[key].status_key:
            entities.append(ResourceStatusSensor(coordinator, key, object_id))
        entities.extend(
            ResourceFieldSensor(coordinator, key, object_id, field)
            for field in FIELDS
            if item.get(field) is not None
        )
        if item.get("capacityBytes") is not None and item.get("freeSpaceBytes") is not None:
            entities.append(ResourceFreePercentSensor(coordinator, key, object_id))
    return entities


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up Veeam ONE sensors."""
    coordinator: VeeamOneCoordinator = entry.runtime_data
    add_entities_dynamically(coordinator, entry, async_add_entities, lambda: _entities(coordinator))
