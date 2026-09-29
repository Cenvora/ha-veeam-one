"""Veeam ONE buttons."""
from __future__ import annotations
from homeassistant.components.button import ButtonEntity
from veeam_one.v2_3.models.resolve_multiple_triggered_alarms_request import ResolveMultipleTriggeredAlarmsRequest
from .entity import VeeamOneEntity

class ResolveAlarm(VeeamOneEntity,ButtonEntity):
    _attr_name="Resolve"
    def __init__(self,c,oid,name):super().__init__(c,"alarms",oid);self._attr_name=f"Resolve {name}";self._attr_unique_id=f"{c.entry_id}_alarm_{oid}_resolve"
    async def async_press(self):
        await self.coordinator.client.call(self.coordinator.client.api("alarms.alarms_resolve_triggered_alarms"),
            body=ResolveMultipleTriggeredAlarmsRequest(triggered_alarm_ids=[int(self.object_id)],comment="Resolved from Home Assistant"))
        await self.coordinator.async_request_refresh()
async def async_setup_entry(hass,entry,async_add_entities):
    c=entry.runtime_data
    async_add_entities([ResolveAlarm(c,str(x["triggeredAlarmId"]),x.get("name") or str(x["triggeredAlarmId"])) for x in c.data.get("alarms",[]) if x.get("triggeredAlarmId") is not None])
