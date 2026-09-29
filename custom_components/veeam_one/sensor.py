"""Veeam ONE sensors."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorStateClass
from homeassistant.const import EntityCategory
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import COLLECTIONS, VeeamOneCoordinator
from .entity import VeeamOneEntity, resource_id, resource_name


def _status(item: dict[str, Any]) -> str | None:
    for key in ("status", "state", "connectionState", "powerState", "bestPracticeCheckStatus"):
        value = item.get(key)
        if value is not None:
            return str(value)
    return None


def _timestamp(value: Any) -> datetime | None:
    if not value:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    try:
        result = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return result if result.tzinfo else result.replace(tzinfo=timezone.utc)


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
        return {"identifiers": {(DOMAIN, self.coordinator.entry_id)}, "name": "Veeam ONE",
                "manufacturer": "Veeam", "model": "Veeam ONE"}


class CollectionSensor(CoordinatorEntity[VeeamOneCoordinator], SensorEntity):
    """Count resources exposed by a collection."""

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
        return {"identifiers": {(DOMAIN, self.coordinator.entry_id)}, "name": "Veeam ONE",
                "manufacturer": "Veeam", "model": "Veeam ONE"}


class FailedCollectionSensor(CollectionSensor):
    """Count resources whose reported state is unhealthy."""

    def __init__(self, coordinator: VeeamOneCoordinator, key: str) -> None:
        super().__init__(coordinator, key)
        self._attr_name = f"{self.label} Not Healthy"
        self._attr_unique_id = f"{coordinator.entry_id}_{key}_not_healthy"
        self._attr_icon = "mdi:alert-circle-outline"

    @property
    def native_value(self) -> int:
        resources = self.coordinator.data.get("collections", {}).get(self.key, [])
        healthy = ("success", "successful", "normal", "connected", "online", "available", "ok", "ready")
        return sum(1 for item in resources if (state := _status(item)) and not any(x in state.lower() for x in healthy))


class ResourceStatusSensor(VeeamOneEntity, SensorEntity):
    """Status of an individual Veeam ONE resource."""

    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_icon = "mdi:information-outline"

    def __init__(self, coordinator: VeeamOneCoordinator, kind: str, object_id: str, name: str) -> None:
        super().__init__(coordinator, kind, object_id, name)
        self._attr_name = "Status"
        self._attr_unique_id = f"{coordinator.entry_id}_{kind}_{object_id}_status"

    @property
    def native_value(self) -> str | None:
        return _status(self.item())

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        item = self.item()
        return {key: value for key, value in item.items() if key not in {"status", "state", "connectionState", "powerState"}}


class ResourceFieldSensor(VeeamOneEntity, SensorEntity):
    """A useful numeric/timestamp field on an individual resource."""

    _attr_entity_category = EntityCategory.DIAGNOSTIC

    DEFINITIONS: dict[str, tuple[str, str | None, SensorDeviceClass | None]] = {
        "lastRun": ("Last Run", None, SensorDeviceClass.TIMESTAMP),
        "lastBestPracticeCheckDate": ("Last Best Practice Check", None, SensorDeviceClass.TIMESTAMP),
        "lastRunDurationSec": ("Last Run Duration", "s", SensorDeviceClass.DURATION),
        "avgDurationSec": ("Average Run Duration", "s", SensorDeviceClass.DURATION),
        "lastTransferredDataBytes": ("Last Transferred Data", "B", SensorDeviceClass.DATA_SIZE),
        "capacityBytes": ("Capacity", "B", SensorDeviceClass.DATA_SIZE),
        "freeSpaceBytes": ("Free Space", "B", SensorDeviceClass.DATA_SIZE),
        "runningTasks": ("Running Tasks", None, None),
        "maxConcurrentTasks": ("Max Concurrent Tasks", None, None),
        "outOfSpaceInDays": ("Days Until Out of Space", "d", SensorDeviceClass.DURATION),
        "cpuCount": ("CPU Cores", None, None),
        "cpuFrequencyMhz": ("CPU Frequency", "MHz", SensorDeviceClass.FREQUENCY),
        "memorySizeBytes": ("Memory", "B", SensorDeviceClass.DATA_SIZE),
        "memoryReserveMb": ("Memory Reserve", "MB", SensorDeviceClass.DATA_SIZE),
    }

    def __init__(self, coordinator: VeeamOneCoordinator, kind: str, object_id: str, name: str, field: str) -> None:
        super().__init__(coordinator, kind, object_id, name)
        label, unit, device_class = self.DEFINITIONS[field]
        self.field = field
        self._attr_name = label
        self._attr_unique_id = f"{coordinator.entry_id}_{kind}_{object_id}_{field}"
        self._attr_native_unit_of_measurement = unit
        self._attr_device_class = device_class

    @property
    def native_value(self) -> Any:
        value = self.item().get(self.field)
        if self._attr_device_class == SensorDeviceClass.TIMESTAMP:
            return _timestamp(value)
        return value


class ResourcePercentageSensor(VeeamOneEntity, SensorEntity):
    """Free-space percentage for resources reporting capacity and free space."""

    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_native_unit_of_measurement = "%"

    def __init__(self, coordinator: VeeamOneCoordinator, kind: str, object_id: str, name: str) -> None:
        super().__init__(coordinator, kind, object_id, name)
        self._attr_name = "Free Space"
        self._attr_unique_id = f"{coordinator.entry_id}_{kind}_{object_id}_free_percent"

    @property
    def native_value(self) -> float | None:
        item = self.item()
        capacity, free = item.get("capacityBytes"), item.get("freeSpaceBytes")
        if not isinstance(capacity, (int, float)) or not capacity:
            return None
        if not isinstance(free, (int, float)):
            return None
        return round(free * 100 / capacity, 1)


class ResourceBooleanSensor(VeeamOneEntity, SensorEntity):
    """Expose useful boolean resource properties."""

    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_icon = "mdi:toggle-switch-outline"

    FIELDS = {
        "isImmutable": "Immutable",
        "upgradeRequired": "Upgrade Required",
        "isReFs": "ReFS",
        "isCloudConnect": "Cloud Connect",
        "isConfigurationBackupEnabled": "Configuration Backup Enabled",
        "intelligentDiagnosticsEnabled": "Intelligent Diagnostics Enabled",
        "remediationActionsEnabled": "Remediation Actions Enabled",
    }

    def __init__(self, coordinator: VeeamOneCoordinator, kind: str, object_id: str, name: str, field: str) -> None:
        super().__init__(coordinator, kind, object_id, name)
        self.field = field
        self._attr_name = self.FIELDS[field]
        self._attr_unique_id = f"{coordinator.entry_id}_{kind}_{object_id}_{field}"

    @property
    def native_value(self) -> int | None:
        value = self.item().get(self.field)
        return None if value is None else int(bool(value))


class LicenseSensor(CoordinatorEntity[VeeamOneCoordinator], SensorEntity):
    """Expose a Veeam ONE license field."""

    _attr_has_entity_name = True
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator: VeeamOneCoordinator, key: str, name: str) -> None:
        super().__init__(coordinator)
        self.key = key
        self._attr_name = name
        self._attr_unique_id = f"{coordinator.entry_id}_license_{key}"
        self._attr_icon = "mdi:license"

    @property
    def native_value(self) -> Any:
        value = self.coordinator.data.get("license", {}).get(self.key)
        return None if isinstance(value, dict) else value

    @property
    def device_info(self) -> dict[str, Any]:
        return {"identifiers": {(DOMAIN, self.coordinator.entry_id)}, "name": "Veeam ONE",
                "manufacturer": "Veeam", "model": "Veeam ONE"}


class LicenseSupportExpirationSensor(LicenseSensor):
    """Days remaining until support expires."""

    def __init__(self, coordinator: VeeamOneCoordinator) -> None:
        super().__init__(coordinator, "support_expiration_days", "License Support Days Remaining")
        self._attr_native_unit_of_measurement = "d"

    @property
    def native_value(self) -> int | None:
        expiration = _timestamp(self.coordinator.data.get("license", {}).get("supportExpirationDate"))
        if expiration is None:
            return None
        return max(0, (expiration - datetime.now(timezone.utc)).days)


class LicenseExpirationSensor(LicenseSensor):
    """Days remaining until license expiration."""

    def __init__(self, coordinator: VeeamOneCoordinator) -> None:
        super().__init__(coordinator, "expiration_days", "License Days Remaining")
        self._attr_native_unit_of_measurement = "d"

    @property
    def native_value(self) -> int | None:
        value = self.coordinator.data.get("license", {}).get("expirationDate")
        expiration = _timestamp(value)
        if expiration is None:
            return None
        return max(0, (expiration - datetime.now(timezone.utc)).days)


class LicenseUsageSensor(CoordinatorEntity[VeeamOneCoordinator], SensorEntity):
    """Expose current license usage."""

    _attr_has_entity_name = True
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator: VeeamOneCoordinator, unit: dict[str, Any], field: str) -> None:
        super().__init__(coordinator)
        self.unit = str(unit.get("licenseUnit") or "Unknown")
        self.field = field
        self._attr_name = f"License {self.unit} {field.capitalize()}"
        self._attr_unique_id = f"{coordinator.entry_id}_license_{self.unit.lower().replace(' ', '_')}_{field}"
        self._attr_icon = "mdi:counter"

    @property
    def native_value(self) -> int | None:
        for unit in self.coordinator.data.get("license_usage", {}).get("units", []) or []:
            if str(unit.get("licenseUnit") or "Unknown") == self.unit:
                value = unit.get(self.field)
                return int(value) if isinstance(value, (int, float)) else None
        return None

    @property
    def device_info(self) -> dict[str, Any]:
        return {"identifiers": {(DOMAIN, self.coordinator.entry_id)}, "name": "Veeam ONE",
                "manufacturer": "Veeam", "model": "Veeam ONE"}


def _resource_entities(coordinator: VeeamOneCoordinator) -> list[SensorEntity]:
    entities: list[SensorEntity] = []
    for kind in COLLECTIONS:
        for item in coordinator.data.get("collections", {}).get(kind, []):
            object_id = resource_id(item)
            if not object_id:
                continue
            name = resource_name(item, object_id)
            entities.append(ResourceStatusSensor(coordinator, kind, object_id, name))
            for field in ResourceFieldSensor.DEFINITIONS:
                if item.get(field) is not None:
                    entities.append(ResourceFieldSensor(coordinator, kind, object_id, name, field))
            if item.get("capacityBytes") is not None and item.get("freeSpaceBytes") is not None:
                entities.append(ResourcePercentageSensor(coordinator, kind, object_id, name))
            for field in ResourceBooleanSensor.FIELDS:
                if item.get(field) is not None:
                    entities.append(ResourceBooleanSensor(coordinator, kind, object_id, name, field))
    return entities


async def async_setup_entry(hass: Any, entry: Any, async_add_entities: Any) -> None:
    """Set up Veeam ONE sensors."""
    coordinator: VeeamOneCoordinator = entry.runtime_data
    entities: list[SensorEntity] = [OverviewSensor(coordinator)]
    for key in ("type", "package", "instances", "sockets"):
        entities.append(LicenseSensor(coordinator, key, f"License {key.capitalize()}"))
    entities.append(LicenseExpirationSensor(coordinator))
    for unit in coordinator.data.get("license_usage", {}).get("units", []) or []:
        if isinstance(unit, dict):
            for field in ("used", "available", "licensed"):
                entities.append(LicenseUsageSensor(coordinator, unit, field))
    for key in COLLECTIONS:
        entities.extend((CollectionSensor(coordinator, key), FailedCollectionSensor(coordinator, key)))
    entities.extend(_resource_entities(coordinator))
    async_add_entities(entities)

    known: set[str] = {entity.unique_id for entity in entities if entity.unique_id}
    async def _sync() -> None:
        nonlocal known
        new_entities = []
        for entity in _resource_entities(coordinator):
            if entity.unique_id and entity.unique_id not in known:
                known.add(entity.unique_id)
                new_entities.append(entity)
        if new_entities:
            async_add_entities(new_entities)
    entry.async_on_unload(coordinator.async_add_listener(_sync))
