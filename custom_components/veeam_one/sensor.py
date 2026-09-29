"""Veeam ONE sensors."""
from __future__ import annotations
from typing import Any
from homeassistant.components.sensor import SensorEntity
from homeassistant.const import UnitOfInformation
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from .coordinator import VeeamOneCoordinator
from .entity import VeeamOneEntity

IDS={"jobs":"vmBackupJobUid","replication_jobs":"vmReplicationJobUid","copy_jobs":"backupCopyJobUid",
     "repositories":"repositoryId","servers":"backupServerId","alarms":"triggeredAlarmId"}

class OverviewSensor(CoordinatorEntity[VeeamOneCoordinator],SensorEntity):
    _attr_has_entity_name=True;_attr_name="Triggered Alarms";_attr_icon="mdi:alarm-light"
    def __init__(self,c):super().__init__(c);self._attr_unique_id=f"{c.entry_id}_alarms"
    @property
    def native_value(self):return len(self.coordinator.data.get("alarms",[]))
    @property
    def device_info(self):return {"identifiers":{("veeam_one",self.coordinator.entry_id)},"name":"Veeam ONE","manufacturer":"Veeam","model":"Veeam ONE"}

class ObjectSensor(VeeamOneEntity,SensorEntity):
    def __init__(self,c,kind,oid,name,field,unit=None):
        super().__init__(c,kind,oid);self._attr_name=name;self.field=field
        self._attr_unique_id=f"{c.entry_id}_{kind}_{oid}_{field}";self._attr_native_unit_of_measurement=unit
    def _item(self):
        if self.kind=="license":return self.coordinator.data.get("license",{})
        return next((x for x in self.coordinator.data.get(self.kind,[]) if str(x.get(IDS[self.kind]))==self.object_id),{})
    @property
    def native_value(self):return self._item().get(self.field)
    @property
    def extra_state_attributes(self):
        x=self._item();return {k:v for k,v in x.items() if k not in {self.field,"name"}}

async def async_setup_entry(hass,entry,async_add_entities):
    c:VeeamOneCoordinator=entry.runtime_data;e=[OverviewSensor(c)]
    for kind,fields in {
        "jobs":[("Status","status"),("Last Run","lastRun"),("Last Run Duration","lastRunDurationSec","s"),("Last Transferred","lastTransferredDataBytes",UnitOfInformation.BYTES)],
        "replication_jobs":[("Status","status")],"copy_jobs":[("Status","status")],
        "repositories":[("Free Space","freeSpaceBytes",UnitOfInformation.BYTES),("Capacity","capacityBytes",UnitOfInformation.BYTES),("Running Tasks","runningTasks"),("Out of Space In","outOfSpaceInDays","d"),("State","state")],
        "servers":[("Version","version"),("Connection State","connectionState"),("Platform","platform")],
        "alarms":[("Status","status"),("Triggered","triggeredTime"),("Repeat Count","repeatCount")],
    }.items():
        for x in c.data.get(kind,[]):
            oid=str(x.get(IDS[kind]))
            if oid!="None":e.extend(ObjectSensor(c,kind,oid,n,f,unit if len(spec)>2 else None) for spec in fields for n,f,*rest in [spec] for unit in [rest[0] if rest else None])
    for f,n in [("type","License Type"),("package","License Package"),("company","Licensed To"),("instances","Licensed Instances"),("sockets","Licensed Sockets"),("expirationDate","License Expiration"),("supportExpirationDate","Support Expiration")]:
        if f in c.data.get("license",{}):e.append(ObjectSensor(c,"license","license",n,f))
    async_add_entities(e)
