"""Veeam ONE data coordinator."""

from __future__ import annotations

import asyncio
import logging
from datetime import timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from veeam_one import VeeamAuthenticationError, VeeamClient

from .const import DOMAIN, PAGE_LIMIT, UPDATE_INTERVAL, UPDATE_TIMEOUT

_LOGGER = logging.getLogger(__name__)

COLLECTIONS: dict[str, tuple[str, str]] = {
    "jobs": ("VBR Backup Jobs", "veeam_backup_replication_jobs.vbr_jobs_get_vm_backup_jobs"),
    "replication_jobs": (
        "VBR Replication Jobs",
        "veeam_backup_replication_jobs.vbr_jobs_get_vm_replication_jobs",
    ),
    "copy_jobs": (
        "VBR Backup Copy Jobs",
        "veeam_backup_replication_jobs.vbr_jobs_get_backup_copy_jobs",
    ),
    "repositories": (
        "VBR Repositories",
        "veeam_backup_replication_infrastructure.vbr_get_regular_repositories",
    ),
    "servers": (
        "VBR Backup Servers",
        "veeam_backup_replication_infrastructure.vbr_get_backup_servers",
    ),
    "cloud_connect_tenants": (
        "Cloud Connect Tenants",
        "veeam_cloud_connect.cloud_connect_get_cloud_tenants",
    ),
    "cloud_connect_gateways": (
        "Cloud Connect Gateways",
        "veeam_cloud_connect.cloud_connect_get_cloud_gateways",
    ),
    "cloud_connect_gateway_pools": (
        "Cloud Connect Gateway Pools",
        "veeam_cloud_connect.cloud_connect_get_cloud_gateway_pools",
    ),
    "m365_organizations": (
        "Microsoft 365 Organizations",
        "veeam_backup_for_microsoft_365_infrastructure.vb_get_vbm_365_organizations",
    ),
    "m365_servers": (
        "Microsoft 365 Servers",
        "veeam_backup_for_microsoft_365_infrastructure.vb_get_vbm_365_servers",
    ),
    "m365_proxies": (
        "Microsoft 365 Backup Proxies",
        "veeam_backup_for_microsoft_365_infrastructure.vb_get_vbm_365_backup_proxies",
    ),
    "m365_repositories": (
        "Microsoft 365 Repositories",
        "veeam_backup_for_microsoft_365_infrastructure.vb_get_vbm_365_backup_repositories",
    ),
    "m365_object_storage": (
        "Microsoft 365 Object Storage Repositories",
        "veeam_backup_for_microsoft_365_infrastructure.vb_get_vbm_365_object_storage_repositories",
    ),
    "m365_backup_jobs": (
        "Microsoft 365 Backup Jobs",
        "veeam_backup_for_microsoft_365_jobs.vb_365_jobs_get_vbm_365_backup_jobs",
    ),
    "m365_copy_jobs": (
        "Microsoft 365 Copy Jobs",
        "veeam_backup_for_microsoft_365_jobs.vb_365_jobs_get_vbm_365_copy_jobs",
    ),
    "m365_users": (
        "Microsoft 365 Users",
        "veeam_backup_for_microsoft_365_infrastructure.vb_get_all_vbm_365_users",
    ),
    "m365_groups": (
        "Microsoft 365 Groups",
        "veeam_backup_for_microsoft_365_infrastructure.vb_get_all_vbm_365_groups",
    ),
    "m365_sites": (
        "Microsoft 365 Sites",
        "veeam_backup_for_microsoft_365_infrastructure.vb_get_all_vbm_365_sites",
    ),
    "m365_teams": (
        "Microsoft 365 Teams",
        "veeam_backup_for_microsoft_365_infrastructure.vb_get_all_vbm_365_teams",
    ),
    "m365_protected_users": (
        "Protected Microsoft 365 Users",
        "veeam_backup_for_microsoft_365_protected_data.protected_data_vb_get_all_vbm_365_protected_users",
    ),
    "m365_protected_groups": (
        "Protected Microsoft 365 Groups",
        "veeam_backup_for_microsoft_365_protected_data.protected_data_vb_get_all_vbm_365_protected_groups",
    ),
    "m365_protected_sites": (
        "Protected Microsoft 365 Sites",
        "veeam_backup_for_microsoft_365_protected_data.protected_data_vb_get_all_vbm_365_protected_sites",
    ),
    "m365_protected_teams": (
        "Protected Microsoft 365 Teams",
        "veeam_backup_for_microsoft_365_protected_data.protected_data_vb_get_all_vbm_365_protected_teams",
    ),
    "vsphere_vcenters": (
        "vSphere vCenters",
        "v_mware_v_sphere_infrastructure.v_sphere_get_v_sphere_virtual_centers",
    ),
    "vsphere_hosts": (
        "vSphere Hosts",
        "v_mware_v_sphere_infrastructure.v_sphere_get_v_sphere_hosts",
    ),
    "vsphere_clusters": (
        "vSphere Clusters",
        "v_mware_v_sphere_infrastructure.v_sphere_get_v_sphere_host_clusters",
    ),
    "vsphere_datastores": (
        "vSphere Datastores",
        "v_mware_v_sphere_infrastructure.v_sphere_get_v_sphere_datastores",
    ),
    "vsphere_datastore_clusters": (
        "vSphere Datastore Clusters",
        "v_mware_v_sphere_infrastructure.v_sphere_get_v_sphere_datastore_clusters",
    ),
    "vsphere_resource_pools": (
        "vSphere Resource Pools",
        "v_mware_v_sphere_infrastructure.v_sphere_get_v_sphere_resource_pools",
    ),
    "vsphere_vms": ("vSphere VMs", "v_mware_v_sphere_infrastructure.v_sphere_get_v_sphere_vms"),
    "vsphere_vapps": (
        "vSphere vApps",
        "v_mware_v_sphere_infrastructure.v_sphere_get_v_sphere_v_apps",
    ),
    "vcd_servers": (
        "Cloud Director Servers",
        "v_mware_cloud_director_infrastructure.cloud_director_get_cloud_directors",
    ),
    "vcd_organizations": (
        "Cloud Director Organizations",
        "v_mware_cloud_director_infrastructure.cloud_director_get_vcd_organizations",
    ),
    "vcd_org_vdcs": (
        "Cloud Director Organization VDCs",
        "v_mware_cloud_director_infrastructure.cloud_director_get_vcd_organization_vdcs",
    ),
    "vcd_provider_vdcs": (
        "Cloud Director Provider VDCs",
        "v_mware_cloud_director_infrastructure.cloud_director_get_vcd_provider_vdcs",
    ),
    "vcd_datastores": (
        "Cloud Director Datastores",
        "v_mware_cloud_director_infrastructure.cloud_director_get_vcd_datastores",
    ),
    "vcd_vapps": (
        "Cloud Director vApps",
        "v_mware_cloud_director_infrastructure.cloud_director_get_vcd_v_apps",
    ),
    "hyperv_hosts": ("Hyper-V Hosts", "microsoft_hyper_v_infrastructure.hyper_v_get_hyper_v_hosts"),
    "hyperv_clusters": (
        "Hyper-V Clusters",
        "microsoft_hyper_v_infrastructure.hyper_v_get_hyper_v_clusters",
    ),
    "hyperv_vms": ("Hyper-V VMs", "microsoft_hyper_v_infrastructure.hyper_v_get_hyper_v_vms"),
    "hyperv_file_servers": (
        "Hyper-V File Servers",
        "microsoft_hyper_v_infrastructure.hyper_v_get_hyper_v_file_servers",
    ),
    "hyperv_file_shares": (
        "Hyper-V File Shares",
        "microsoft_hyper_v_infrastructure.hyper_v_get_hyper_v_file_shares",
    ),
    "hyperv_physical_disks": (
        "Hyper-V Physical Disks",
        "microsoft_hyper_v_infrastructure.hyper_v_get_hyper_v_physical_disks",
    ),
    "hyperv_sc_vmm_servers": (
        "SCVMM Servers",
        "microsoft_hyper_v_infrastructure.hyper_v_get_hyper_v_sc_vmm_servers",
    ),
    "public_cloud_vms": ("Public Cloud VMs", "public_cloud.public_cloud_get_public_cloud_vms"),
    "public_cloud_databases": (
        "Public Cloud Databases",
        "public_cloud.public_cloud_get_public_cloud_databases",
    ),
    "public_cloud_file_shares": (
        "Public Cloud File Shares",
        "public_cloud.public_cloud_get_public_cloud_file_shares",
    ),
    "public_cloud_vm_backups": (
        "Protected Public Cloud VMs",
        "public_cloud_protected_data.protected_data_public_cloud_get_all_cloud_virtual_machine_backups",
    ),
    "public_cloud_db_backups": (
        "Protected Public Cloud Databases",
        "public_cloud_protected_data.protected_data_public_cloud_get_all_protected_cloud_databases",
    ),
    "public_cloud_file_backups": (
        "Protected Public Cloud File Shares",
        "public_cloud_protected_data.protected_data_public_cloud_get_all_protected_cloud_file_shares",
    ),
    "public_cloud_network_backups": (
        "Protected Public Cloud Networks",
        "public_cloud_protected_data.protected_data_public_cloud_get_all_protected_cloud_networks",
    ),
}


def as_dict(value: Any) -> dict[str, Any]:
    """Convert an SDK model to a dictionary."""
    if value is None:
        return {}
    if hasattr(value, "to_dict"):
        return value.to_dict()
    return value if isinstance(value, dict) else {}


def items(value: Any) -> list[dict[str, Any]]:
    """Extract collection items from a generated SDK page."""
    data = as_dict(value).get("items", [])
    return data if isinstance(data, list) else []


class VeeamOneCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Fetch Veeam ONE monitoring data."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, client: VeeamClient) -> None:
        self.entry_id = entry.entry_id
        self.client = client
        super().__init__(
            hass,
            self._async_update_data,
            name=DOMAIN,
            update_interval=timedelta(seconds=UPDATE_INTERVAL),
        )

    async def _collection(self, key: str, operation: str) -> list[dict[str, Any]]:
        """Fetch one collection without making an optional endpoint failure fatal."""
        try:
            result = await self.client.call(self.client.api(operation), limit=PAGE_LIMIT, offset=0)
            return items(result)
        except VeeamAuthenticationError:
            raise
        except Exception as err:
            _LOGGER.debug("Veeam ONE collection %s failed: %s", key, err)
            return []

    async def _async_update_data(self) -> dict[str, Any]:
        try:
            async with asyncio.timeout(UPDATE_TIMEOUT):
                (
                    about,
                    service,
                    license_info,
                    license_usage,
                    alarms,
                    collections,
                ) = await asyncio.gather(
                    self.client.call(self.client.api("about.about_get_about")),
                    self.client.call(self.client.api("about.about_get_service_info")),
                    self.client.call(self.client.api("licensing.licensing_get_info")),
                    self.client.call(self.client.api("licensing.licensing_get_current_usage")),
                    self._collection("alarms", "alarms.alarms_get_triggered_alarms"),
                    asyncio.gather(
                        *(
                            self._collection(key, operation)
                            for key, (_, operation) in COLLECTIONS.items()
                        )
                    ),
                )
                return {
                    "about": as_dict(about),
                    "service": as_dict(service),
                    "license": as_dict(license_info),
                    "license_usage": as_dict(license_usage),
                    "alarms": alarms,
                    "collections": dict(zip(COLLECTIONS, collections, strict=True)),
                }
        except VeeamAuthenticationError as err:
            raise UpdateFailed("Authentication failed") from err
        except Exception as err:
            raise UpdateFailed(str(err)) from err
