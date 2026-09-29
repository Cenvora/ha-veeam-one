"""Veeam ONE binary sensors."""
from __future__ import annotations

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import VeeamOneCoordinator


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
    def device_info(self):
        return {
            "identifiers": {(DOMAIN, self.coordinator.entry_id)},
            "name": "Veeam ONE",
            "manufacturer": "Veeam",
            "model": "Veeam ONE",
        }


async def async_setup_entry(hass, entry, async_add_entities):
    """Set up the connectivity sensor."""
    async_add_entities([Connected(entry.runtime_data)])
