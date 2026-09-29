"""Additional Veeam ONE binary monitoring entities."""
from __future__ import annotations
from datetime import datetime, timezone
from typing import Any
from homeassistant.components.binary_sensor import BinarySensorDeviceClass, BinarySensorEntity
from homeassistant.const import EntityCategory
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from .const import DOMAIN
from .coordinator import VeeamOneCoordinator

class AggregateBinary(CoordinatorEntity[VeeamOneCoordinator], BinarySensorEntity):
    _attr_has_entity_name = True
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    @property
    def device_info(self) -> dict[str, Any]:
        return {"identifiers": {(DOMAIN, self.coordinator.entry_id)}, "name": "Veeam ONE", "manufacturer": "Veeam", "model": "Veeam ONE"}

class LicenseExpiredSensor(AggregateBinary):
    _attr_name = "License Expired"
    _attr_device_class = BinarySensorDeviceClass.PROBLEM
    _attr_icon = "mdi:license"
    def __init__(self, coordinator: VeeamOneCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.entry_id}_license_expired"
    @property
    def is_on(self) -> bool | None:
        value = self.coordinator.data.get("license", {}).get("expirationDate")
        if not value:
            return None
        try:
            expiration = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except ValueError:
            return None
        if expiration.tzinfo is None:
            expiration = expiration.replace(tzinfo=timezone.utc)
        return expiration <= datetime.now(timezone.utc)

class LicenseSupportExpiredSensor(AggregateBinary):
    _attr_name = "License Support Expired"
    _attr_device_class = BinarySensorDeviceClass.PROBLEM
    _attr_icon = "mdi:lifebuoy"
    def __init__(self, coordinator: VeeamOneCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.entry_id}_license_support_expired"
    @property
    def is_on(self) -> bool | None:
        value = self.coordinator.data.get("license", {}).get("supportExpirationDate")
        if not value:
            return None
        try:
            expiration = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except ValueError:
            return None
        if expiration.tzinfo is None:
            expiration = expiration.replace(tzinfo=timezone.utc)
        return expiration <= datetime.now(timezone.utc)
