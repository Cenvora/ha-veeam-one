"""Veeam ONE buttons."""
from __future__ import annotations

from typing import Any

from homeassistant.components.button import ButtonEntity
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from veeam_one.v2_3.models.resolve_multiple_triggered_alarms_request import ResolveMultipleTriggeredAlarmsRequest

from .const import DOMAIN
from .coordinator import VeeamOneCoordinator
from .entity import VeeamOneEntity


class ResolveAlarm(VeeamOneEntity, CoordinatorEntity[VeeamOneCoordinator], ButtonEntity):
    """Resolve one triggered Veeam ONE alarm."""

    _attr_name = "Resolve"
    _attr_icon = "mdi:alarm-off"
    _attr_entity_category = "config"

    def __init__(self, coordinator: VeeamOneCoordinator, object_id: str, name: str) -> None:
        VeeamOneEntity.__init__(self, coordinator, "alarms", object_id, name)
        self._attr_name = "Resolve"
        self._attr_unique_id = f"{coordinator.entry_id}_alarm_{object_id}_resolve"

    def item(self) -> dict[str, Any]:
        for alarm in self.coordinator.data.get("alarms", []):
            if str(alarm.get("triggeredAlarmId")) == self.object_id:
                return alarm
        return {}

    async def async_press(self) -> None:
        """Resolve this alarm through the ONE REST API."""
        try:
            await self.coordinator.client.call(
                self.coordinator.client.api("alarms.alarms_resolve_triggered_alarms"),
                body=ResolveMultipleTriggeredAlarmsRequest(
                    triggered_alarm_ids=[int(self.object_id)],
                    comment="Resolved from Home Assistant",
                ),
            )
        except Exception as err:
            raise HomeAssistantError(f"Unable to resolve Veeam ONE alarm: {err}") from err
        await self.coordinator.async_request_refresh()


async def async_setup_entry(hass: Any, entry: Any, async_add_entities: Any) -> None:
    """Set up alarm action buttons and add newly triggered alarms dynamically."""
    coordinator: VeeamOneCoordinator = entry.runtime_data
    known: set[str] = set()

    def add_current() -> None:
        new_entities = []
        for alarm in coordinator.data.get("alarms", []):
            alarm_id = alarm.get("triggeredAlarmId")
            if alarm_id is None or str(alarm_id) in known:
                continue
            object_id = str(alarm_id)
            name = str(alarm.get("name") or alarm.get("alarmName") or object_id)
            new_entities.append(ResolveAlarm(coordinator, object_id, name))
            known.add(object_id)
        if new_entities:
            async_add_entities(new_entities)

    add_current()
    entry.async_on_unload(coordinator.async_add_listener(add_current))
