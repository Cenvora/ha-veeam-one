"""Base Veeam ONE entity."""
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from .coordinator import VeeamOneCoordinator
from .const import DOMAIN

class VeeamOneEntity(CoordinatorEntity[VeeamOneCoordinator]):
    """Base entity."""
    _attr_has_entity_name=True
    def __init__(self,coordinator:VeeamOneCoordinator,kind:str,object_id:str)->None:
        super().__init__(coordinator);self.kind=kind;self.object_id=object_id
    @property
    def device_info(self):
        return {"identifiers":{(DOMAIN,self.coordinator.entry_id,self.kind,self.object_id)},
                "name":f"Veeam ONE {self.kind.replace('_',' ').title()} {self.object_id}",
                "manufacturer":"Veeam","model":"Veeam ONE"}
