"""Additional Veeam ONE aggregate monitoring entities."""
from __future__ import annotations
from typing import Any
from homeassistant.components.sensor import SensorEntity
from homeassistant.const import EntityCategory
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from .const import DOMAIN
from .coordinator import COLLECTIONS, VeeamOneCoordinator

def _status(item: dict[str, Any]) -> str | None:
    for key in ("status", "state", "connectionState", "powerState", "bestPracticeCheckStatus"):
        value = item.get(key)
        if value is not None:
            return str(value)
    return None

def _healthy(status: str) -> bool:
    return status.lower() in {"success", "successful", "normal", "connected", "online", "available", "ok", "ready", "running"}

def _severity(alarm: dict[str, Any]) -> str | None:
    for key in ("severity", "alarmSeverity", "level", "priority"):
        value = alarm.get(key)
        if value is not None:
            return str(value).lower()
    return None

class AggregateEntity(CoordinatorEntity[VeeamOneCoordinator]):
    _attr_has_entity_name = True
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    @property
    def device_info(self) -> dict[str, Any]:
        return {"identifiers": {(DOMAIN, self.coordinator.entry_id)}, "name": "Veeam ONE", "manufacturer": "Veeam", "model": "Veeam ONE"}

class ServiceSensor(AggregateEntity, SensorEntity):
    _attr_icon = "mdi:server-check"
    def __init__(self, coordinator: VeeamOneCoordinator, key: str, name: str) -> None:
        super().__init__(coordinator)
        self.key = key
        self._attr_name = name
        self._attr_unique_id = f"{coordinator.entry_id}_service_{key}"
    @property
    def native_value(self) -> Any:
        for source in ("service", "about"):
            value = self.coordinator.data.get(source, {}).get(self.key)
            if value is not None:
                return value
        return None

class AlarmSeveritySensor(AggregateEntity, SensorEntity):
    _attr_icon = "mdi:alarm-light-outline"
    def __init__(self, coordinator: VeeamOneCoordinator, severity: str) -> None:
        super().__init__(coordinator)
        self.severity = severity
        self._attr_name = f"{severity.capitalize()} Alarms"
        self._attr_unique_id = f"{coordinator.entry_id}_alarms_{severity}"
    @property
    def native_value(self) -> int:
        return sum(1 for alarm in self.coordinator.data.get("alarms", []) if _severity(alarm) == self.severity)

class CollectionHealthSensor(AggregateEntity, SensorEntity):
    _attr_native_unit_of_measurement = "%"
    _attr_icon = "mdi:heart-pulse"
    def __init__(self, coordinator: VeeamOneCoordinator, key: str) -> None:
        super().__init__(coordinator)
        self.key = key
        self.label = COLLECTIONS[key][0]
        self._attr_name = f"{self.label} Health"
        self._attr_unique_id = f"{coordinator.entry_id}_{key}_health"
    @property
    def native_value(self) -> float | None:
        resources = self.coordinator.data.get("collections", {}).get(self.key, [])
        known = [item for item in resources if _status(item)]
        if not known:
            return None
        healthy = sum(1 for item in known if _healthy(_status(item) or ""))
        return round(healthy * 100 / len(known), 1)

class LicenseUsagePercentageSensor(AggregateEntity, SensorEntity):
    _attr_native_unit_of_measurement = "%"
    _attr_icon = "mdi:percent"
    def __init__(self, coordinator: VeeamOneCoordinator, unit: dict[str, Any]) -> None:
        super().__init__(coordinator)
        self.unit = str(unit.get("licenseUnit") or "Unknown")
        self._attr_name = f"License {self.unit} Used Percentage"
        self._attr_unique_id = f"{coordinator.entry_id}_license_{self.unit.lower().replace(chr(32), chr(95))}_percentage"
    @property
    def native_value(self) -> float | None:
        for unit in self.coordinator.data.get("license_usage", {}).get("units", []) or []:
            if str(unit.get("licenseUnit") or "Unknown") != self.unit:
                continue
            used, licensed = unit.get("used"), unit.get("licensed")
            if not isinstance(used, (int, float)) or not isinstance(licensed, (int, float)) or licensed <= 0:
                return None
            return round(used * 100 / licensed, 1)
        return None
