"""Veeam ONE sensors."""

from __future__ import annotations

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

# Alarm list attribute is capped so a flood of alarms can't bloat the recorder.
MAX_ALARM_ATTRIBUTES = 50


class VersionSensor(VeeamOneEntity, SensorEntity):
    """Installed Veeam ONE version."""

    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_icon = "mdi:information-outline"

    def __init__(self, coordinator: VeeamOneCoordinator) -> None:
        super().__init__(coordinator, "version", "Version")

    @property
    def native_value(self) -> str | None:
        return self.coordinator.data.get("service", {}).get("version")


class AlarmCountSensor(VeeamOneEntity, SensorEntity):
    """Triggered alarms still needing attention, overall or for one status."""

    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:alarm-light"

    def __init__(self, coordinator: VeeamOneCoordinator, status: str | None) -> None:
        label = status or "Active"
        super().__init__(coordinator, f"{label.lower()}_alarms", f"{label} Alarms")
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
    _attr_icon = "mdi:license"

    def __init__(self, coordinator: VeeamOneCoordinator, field: str, name: str) -> None:
        super().__init__(coordinator, f"license_{field}", name)
        self.field = field

    @property
    def native_value(self) -> Any:
        value = self.coordinator.data.get("license", {}).get(self.field)
        return value if isinstance(value, (str, int, float)) else None


class LicenseDaysRemainingSensor(VeeamOneEntity, SensorEntity):
    """Days until the license or its support expires; negative once expired."""

    _attr_device_class = SensorDeviceClass.DURATION
    _attr_native_unit_of_measurement = UnitOfTime.DAYS
    _attr_icon = "mdi:calendar-clock"

    def __init__(self, coordinator: VeeamOneCoordinator, field: str, key: str, name: str) -> None:
        super().__init__(coordinator, key, name)
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
    _attr_icon = "mdi:counter"

    def __init__(self, coordinator: VeeamOneCoordinator, unit: str, field: str) -> None:
        super().__init__(
            coordinator,
            f"license_{unit.lower()}_{field}",
            f"License {unit} {field.capitalize()}",
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
    _attr_icon = "mdi:percent"

    def __init__(self, coordinator: VeeamOneCoordinator, unit: str) -> None:
        super().__init__(
            coordinator, f"license_{unit.lower()}_percentage", f"License {unit} Used Percentage"
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
    _attr_icon = "mdi:database-outline"

    def __init__(self, coordinator: VeeamOneCoordinator, key: str) -> None:
        super().__init__(coordinator, f"{key}_count", COLLECTIONS[key].label)
        self.key = key

    @property
    def native_value(self) -> int | None:
        return self.coordinator.data.get("totals", {}).get(self.key)


class CollectionHealthSensor(VeeamOneEntity, SensorEntity):
    """Share of a collection's resources with a known, healthy status."""

    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:heart-pulse"

    def __init__(self, coordinator: VeeamOneCoordinator, key: str) -> None:
        super().__init__(coordinator, f"{key}_health", f"{COLLECTIONS[key].label} Health")
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

    _attr_icon = "mdi:information-outline"

    def __init__(self, coordinator: VeeamOneCoordinator, key: str, object_id: str) -> None:
        super().__init__(coordinator, key, object_id, "status", "Status")

    @property
    def native_value(self) -> str | None:
        value = self.item().get(self.collection.status_key or "")
        return None if value is None else str(value)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        promoted = {self.collection.status_key, *FIELDS}
        return {key: value for key, value in self.item().items() if key not in promoted}


# API field → (name, unit, device class, entity category)
FIELDS: dict[str, tuple[str, str | None, SensorDeviceClass | None, EntityCategory | None]] = {
    "lastRun": ("Last Run", None, SensorDeviceClass.TIMESTAMP, None),
    "lastRunDurationSec": (
        "Last Run Duration",
        UnitOfTime.SECONDS,
        SensorDeviceClass.DURATION,
        None,
    ),
    "avgDurationSec": (
        "Average Run Duration",
        UnitOfTime.SECONDS,
        SensorDeviceClass.DURATION,
        EntityCategory.DIAGNOSTIC,
    ),
    "lastTransferredDataBytes": (
        "Last Transferred Data",
        UnitOfInformation.BYTES,
        SensorDeviceClass.DATA_SIZE,
        None,
    ),
    "processedItems": ("Processed Items", None, None, EntityCategory.DIAGNOSTIC),
    "capacityBytes": ("Capacity", UnitOfInformation.BYTES, SensorDeviceClass.DATA_SIZE, None),
    "freeSpaceBytes": ("Free Space", UnitOfInformation.BYTES, SensorDeviceClass.DATA_SIZE, None),
    "usedSpaceBytes": ("Used Space", UnitOfInformation.BYTES, SensorDeviceClass.DATA_SIZE, None),
    "runningTasks": ("Running Tasks", None, None, EntityCategory.DIAGNOSTIC),
    "outOfSpaceInDays": (
        "Days Until Out of Space",
        UnitOfTime.DAYS,
        SensorDeviceClass.DURATION,
        None,
    ),
}


class ResourceFieldSensor(ResourceEntity, SensorEntity):
    """A numeric or timestamp field of a resource."""

    def __init__(
        self, coordinator: VeeamOneCoordinator, key: str, object_id: str, field: str
    ) -> None:
        name, unit, device_class, category = FIELDS[field]
        super().__init__(coordinator, key, object_id, field, name)
        self.field = field
        self._attr_native_unit_of_measurement = unit
        self._attr_device_class = device_class
        self._attr_entity_category = category
        if device_class != SensorDeviceClass.TIMESTAMP:
            self._attr_state_class = SensorStateClass.MEASUREMENT
        if device_class == SensorDeviceClass.DATA_SIZE:
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
    _attr_icon = "mdi:harddisk"

    def __init__(self, coordinator: VeeamOneCoordinator, key: str, object_id: str) -> None:
        super().__init__(coordinator, key, object_id, "free_percent", "Free Space Percentage")

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
        LicenseSensor(coordinator, "type", "License Type"),
        LicenseSensor(coordinator, "package", "License Package"),
        LicenseSensor(coordinator, "company", "License Company"),
        LicenseSensor(coordinator, "instances", "Licensed Instances"),
        LicenseSensor(coordinator, "sockets", "Licensed Sockets"),
        LicenseDaysRemainingSensor(
            coordinator, "expirationDate", "license_expiration_days", "License Days Remaining"
        ),
        LicenseDaysRemainingSensor(
            coordinator,
            "supportExpirationDate",
            "license_support_expiration_days",
            "License Support Days Remaining",
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
