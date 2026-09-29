"""Veeam ONE data coordinator."""
from __future__ import annotations
import asyncio
from datetime import timedelta
from typing import Any
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator,UpdateFailed
from veeam_one import VeeamAuthenticationError,VeeamClient
from .const import DOMAIN,PAGE_LIMIT,UPDATE_INTERVAL,UPDATE_TIMEOUT

def as_dict(value:Any)->dict[str,Any]:
    if value is None:return {}
    if hasattr(value,"to_dict"):return value.to_dict()
    return value if isinstance(value,dict) else {}

def items(value:Any)->list[dict[str,Any]]:
    data=as_dict(value).get("items",[])
    return data if isinstance(data,list) else []

class VeeamOneCoordinator(DataUpdateCoordinator[dict[str,Any]]):
    """Fetch Veeam ONE monitoring data."""
    def __init__(self,hass:HomeAssistant,entry:ConfigEntry,client:VeeamClient)->None:
        self.entry_id=entry.entry_id
        self.client=client
        super().__init__(hass,lambda *args:None,name=DOMAIN,
            update_interval=timedelta(seconds=UPDATE_INTERVAL),
            update_method=self._async_update_data)

    async def _page(self,operation:str)->list[dict[str,Any]]:
        return items(await self.client.call(self.client.api(operation),limit=PAGE_LIMIT,offset=0))

    async def _async_update_data(self)->dict[str,Any]:
        try:
            async with asyncio.timeout(UPDATE_TIMEOUT):
                about,service,license_info,collections=await asyncio.gather(
                    self.client.call(self.client.api("about.about_get_about")),
                    self.client.call(self.client.api("about.about_get_service_info")),
                    self.client.call(self.client.api("licensing.licensing_get_info")),
                    asyncio.gather(
                        self._page("veeam_backup_replication_jobs.vbr_jobs_get_vm_backup_jobs"),
                        self._page("veeam_backup_replication_jobs.vbr_jobs_get_vm_replication_jobs"),
                        self._page("veeam_backup_replication_jobs.vbr_jobs_get_backup_copy_jobs"),
                        self._page("veeam_backup_replication_infrastructure.vbr_get_regular_repositories"),
                        self._page("veeam_backup_replication_infrastructure.vbr_get_backup_servers"),
                        self._page("alarms.alarms_get_triggered_alarms"),
                    ),
                )
                jobs,replication_jobs,copy_jobs,repositories,servers,alarms=collections
                return {"about":as_dict(about),"service":as_dict(service),"license":as_dict(license_info),
                        "jobs":jobs,"replication_jobs":replication_jobs,"copy_jobs":copy_jobs,
                        "repositories":repositories,"servers":servers,"alarms":alarms}
        except VeeamAuthenticationError as err:
            raise UpdateFailed("Authentication failed") from err
        except Exception as err:
            raise UpdateFailed(str(err)) from err
