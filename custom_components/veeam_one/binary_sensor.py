"""Veeam ONE binary sensors."""
from __future__ import annotations
from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from .coordinator import VeeamOneCoordinator
from .entity import VeeamOneEntity
IDS={"jobs":"vmBackupJobUid","replication_jobs":"vmReplicationJobUid","copy_jobs":"backupCopyJobUid","repositories":"repositoryId","servers":"backupServerId"}
def good(v):return str(v).lower() in {"success","successful","connected","online","ok","normal","available"}
class Connected(CoordinatorEntity[VeeamOneCoordinator],BinarySensorEntity):
    _attr_has_entity_name=True;_attr_name="Connected";_attr_icon="mdi:lan-connect"
    def __init__(self,c):super().__init__(c);self._attr_unique_id=f"{c.entry_id}_connected"
    @property
    def is_on(self):return self.coordinator.last_update_success
    @property
    def device_info(self):return {"identifiers":{("veeam_one",self.coordinator.entry_id)},"name":"Veeam ONE","manufacturer":"Veeam","model":"Veeam ONE"}
class Status(VeeamOneEntity,BinarySensorEntity):
    def __init__(self,c,kind,oid,name,field):super().__init__(c,kind,oid);self._attr_name=name;self.field=field;self._attr_unique_id=f"{c.entry_id}_{kind}_{oid}_{field}_ok"
    def _item(self):return next((x for x in self.coordinator.data.get(self.kind,[]) if str(x.get(IDS[self.kind]))==self.object_id),{})
    @property
    def is_on(self):
        v=self._item().get(self.field);return None if v is None else good(v)
async def async_setup_entry(hass,entry,async_add_entities):
    c=entry.runtime_data;e=[Connected(c)]
    for kind,name,field in [("jobs","Successful","status"),("replication_jobs","Successful","status"),("copy_jobs","Successful","status"),("repositories","Accessible","state"),("servers","Connected","connectionState")]:
        for x in c.data.get(kind,[]):
            oid=str(x.get(IDS[kind]))
            if oid!="None":e.append(Status(c,kind,oid,name,field))
    async_add_entities(e)
