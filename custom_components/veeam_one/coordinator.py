"""Veeam ONE data coordinator."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from veeam_one import VeeamAuthenticationError, VeeamClient

from .const import DOMAIN, MAX_CONCURRENT_REQUESTS, PAGE_LIMIT, UPDATE_INTERVAL, UPDATE_TIMEOUT
from .sdk import fetch

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class Collection:
    """A Veeam ONE collection endpoint.

    Collections with an `id_key` give each resource its own device; the rest are only
    counted. `status_key` names the field holding the resource's health.
    """

    label: str
    operation: str
    model: str | None = None
    id_key: str | None = None
    status_key: str | None = None


COLLECTIONS: dict[str, Collection] = {
    "jobs": Collection(
        "VBR Backup Jobs",
        "veeam_backup_replication_jobs.vbr_jobs_get_vm_backup_jobs",
        "VBR Backup Job",
        "vmBackupJobUid",
        "status",
    ),
    "replication_jobs": Collection(
        "VBR Replication Jobs",
        "veeam_backup_replication_jobs.vbr_jobs_get_vm_replication_jobs",
        "VBR Replication Job",
        "vmReplicationJobUid",
        "status",
    ),
    "copy_jobs": Collection(
        "VBR Backup Copy Jobs",
        "veeam_backup_replication_jobs.vbr_jobs_get_backup_copy_jobs",
        "VBR Backup Copy Job",
        "backupCopyJobUid",
        "status",
    ),
    "repositories": Collection(
        "VBR Repositories",
        "veeam_backup_replication_infrastructure.vbr_get_regular_repositories",
        "VBR Repository",
        "repositoryId",
        "state",
    ),
    "servers": Collection(
        "VBR Backup Servers",
        "veeam_backup_replication_infrastructure.vbr_get_backup_servers",
        "VBR Backup Server",
        "backupServerId",
        "connectionState",
    ),
    "cloud_connect_tenants": Collection(
        "Cloud Connect Tenants", "veeam_cloud_connect.cloud_connect_get_cloud_tenants"
    ),
    "cloud_connect_gateways": Collection(
        "Cloud Connect Gateways", "veeam_cloud_connect.cloud_connect_get_cloud_gateways"
    ),
    "cloud_connect_gateway_pools": Collection(
        "Cloud Connect Gateway Pools", "veeam_cloud_connect.cloud_connect_get_cloud_gateway_pools"
    ),
    "m365_organizations": Collection(
        "Microsoft 365 Organizations",
        "veeam_backup_for_microsoft_365_infrastructure.vb_get_vbm_365_organizations",
    ),
    "m365_servers": Collection(
        "Microsoft 365 Servers",
        "veeam_backup_for_microsoft_365_infrastructure.vb_get_vbm_365_servers",
        "Microsoft 365 Server",
        "vb365ServerId",
        "connectionState",
    ),
    "m365_proxies": Collection(
        "Microsoft 365 Backup Proxies",
        "veeam_backup_for_microsoft_365_infrastructure.vb_get_vbm_365_backup_proxies",
        "Microsoft 365 Backup Proxy",
        "backupProxyId",
        "status",
    ),
    "m365_repositories": Collection(
        "Microsoft 365 Repositories",
        "veeam_backup_for_microsoft_365_infrastructure.vb_get_vbm_365_backup_repositories",
        "Microsoft 365 Repository",
        "backupRepositoryId",
    ),
    "m365_object_storage": Collection(
        "Microsoft 365 Object Storage Repositories",
        "veeam_backup_for_microsoft_365_infrastructure.vb_get_vbm_365_object_storage_repositories",
        "Microsoft 365 Object Storage Repository",
        "objectStorageRepositoryId",
    ),
    "m365_backup_jobs": Collection(
        "Microsoft 365 Backup Jobs",
        "veeam_backup_for_microsoft_365_jobs.vb_365_jobs_get_vbm_365_backup_jobs",
        "Microsoft 365 Backup Job",
        "backupJobUid",
        "status",
    ),
    "m365_copy_jobs": Collection(
        "Microsoft 365 Copy Jobs",
        "veeam_backup_for_microsoft_365_jobs.vb_365_jobs_get_vbm_365_copy_jobs",
        "Microsoft 365 Copy Job",
        "copyJobUid",
        "status",
    ),
    "m365_users": Collection(
        "Microsoft 365 Users",
        "veeam_backup_for_microsoft_365_infrastructure.vb_get_all_vbm_365_users",
    ),
    "m365_groups": Collection(
        "Microsoft 365 Groups",
        "veeam_backup_for_microsoft_365_infrastructure.vb_get_all_vbm_365_groups",
    ),
    "m365_sites": Collection(
        "Microsoft 365 Sites",
        "veeam_backup_for_microsoft_365_infrastructure.vb_get_all_vbm_365_sites",
    ),
    "m365_teams": Collection(
        "Microsoft 365 Teams",
        "veeam_backup_for_microsoft_365_infrastructure.vb_get_all_vbm_365_teams",
    ),
    "m365_protected_users": Collection(
        "Protected Microsoft 365 Users",
        "veeam_backup_for_microsoft_365_protected_data.protected_data_vb_get_all_vbm_365_protected_users",
    ),
    "m365_protected_groups": Collection(
        "Protected Microsoft 365 Groups",
        "veeam_backup_for_microsoft_365_protected_data.protected_data_vb_get_all_vbm_365_protected_groups",
    ),
    "m365_protected_sites": Collection(
        "Protected Microsoft 365 Sites",
        "veeam_backup_for_microsoft_365_protected_data.protected_data_vb_get_all_vbm_365_protected_sites",
    ),
    "m365_protected_teams": Collection(
        "Protected Microsoft 365 Teams",
        "veeam_backup_for_microsoft_365_protected_data.protected_data_vb_get_all_vbm_365_protected_teams",
    ),
    "vsphere_vcenters": Collection(
        "vSphere vCenters",
        "v_mware_v_sphere_infrastructure.v_sphere_get_v_sphere_virtual_centers",
    ),
    "vsphere_hosts": Collection(
        "vSphere Hosts", "v_mware_v_sphere_infrastructure.v_sphere_get_v_sphere_hosts"
    ),
    "vsphere_clusters": Collection(
        "vSphere Clusters", "v_mware_v_sphere_infrastructure.v_sphere_get_v_sphere_host_clusters"
    ),
    "vsphere_datastores": Collection(
        "vSphere Datastores", "v_mware_v_sphere_infrastructure.v_sphere_get_v_sphere_datastores"
    ),
    "vsphere_datastore_clusters": Collection(
        "vSphere Datastore Clusters",
        "v_mware_v_sphere_infrastructure.v_sphere_get_v_sphere_datastore_clusters",
    ),
    "vsphere_resource_pools": Collection(
        "vSphere Resource Pools",
        "v_mware_v_sphere_infrastructure.v_sphere_get_v_sphere_resource_pools",
    ),
    "vsphere_vms": Collection(
        "vSphere VMs", "v_mware_v_sphere_infrastructure.v_sphere_get_v_sphere_vms"
    ),
    "vsphere_vapps": Collection(
        "vSphere vApps", "v_mware_v_sphere_infrastructure.v_sphere_get_v_sphere_v_apps"
    ),
    "vcd_servers": Collection(
        "Cloud Director Servers",
        "v_mware_cloud_director_infrastructure.cloud_director_get_cloud_directors",
    ),
    "vcd_organizations": Collection(
        "Cloud Director Organizations",
        "v_mware_cloud_director_infrastructure.cloud_director_get_vcd_organizations",
    ),
    "vcd_org_vdcs": Collection(
        "Cloud Director Organization VDCs",
        "v_mware_cloud_director_infrastructure.cloud_director_get_vcd_organization_vdcs",
    ),
    "vcd_provider_vdcs": Collection(
        "Cloud Director Provider VDCs",
        "v_mware_cloud_director_infrastructure.cloud_director_get_vcd_provider_vdcs",
    ),
    "vcd_datastores": Collection(
        "Cloud Director Datastores",
        "v_mware_cloud_director_infrastructure.cloud_director_get_vcd_datastores",
    ),
    "vcd_vapps": Collection(
        "Cloud Director vApps",
        "v_mware_cloud_director_infrastructure.cloud_director_get_vcd_v_apps",
    ),
    "hyperv_hosts": Collection(
        "Hyper-V Hosts", "microsoft_hyper_v_infrastructure.hyper_v_get_hyper_v_hosts"
    ),
    "hyperv_clusters": Collection(
        "Hyper-V Clusters", "microsoft_hyper_v_infrastructure.hyper_v_get_hyper_v_clusters"
    ),
    "hyperv_vms": Collection(
        "Hyper-V VMs", "microsoft_hyper_v_infrastructure.hyper_v_get_hyper_v_vms"
    ),
    "hyperv_file_servers": Collection(
        "Hyper-V File Servers",
        "microsoft_hyper_v_infrastructure.hyper_v_get_hyper_v_file_servers",
    ),
    "hyperv_file_shares": Collection(
        "Hyper-V File Shares", "microsoft_hyper_v_infrastructure.hyper_v_get_hyper_v_file_shares"
    ),
    "hyperv_physical_disks": Collection(
        "Hyper-V Physical Disks",
        "microsoft_hyper_v_infrastructure.hyper_v_get_hyper_v_physical_disks",
    ),
    "hyperv_sc_vmm_servers": Collection(
        "SCVMM Servers", "microsoft_hyper_v_infrastructure.hyper_v_get_hyper_v_sc_vmm_servers"
    ),
    "public_cloud_vms": Collection(
        "Public Cloud VMs", "public_cloud.public_cloud_get_public_cloud_vms"
    ),
    "public_cloud_databases": Collection(
        "Public Cloud Databases", "public_cloud.public_cloud_get_public_cloud_databases"
    ),
    "public_cloud_file_shares": Collection(
        "Public Cloud File Shares", "public_cloud.public_cloud_get_public_cloud_file_shares"
    ),
    "public_cloud_vm_backups": Collection(
        "Protected Public Cloud VMs",
        "public_cloud_protected_data.protected_data_public_cloud_get_all_cloud_virtual_machine_backups",
    ),
    "public_cloud_db_backups": Collection(
        "Protected Public Cloud Databases",
        "public_cloud_protected_data.protected_data_public_cloud_get_all_protected_cloud_databases",
    ),
    "public_cloud_file_backups": Collection(
        "Protected Public Cloud File Shares",
        "public_cloud_protected_data.protected_data_public_cloud_get_all_protected_cloud_file_shares",
    ),
    "public_cloud_network_backups": Collection(
        "Protected Public Cloud Networks",
        "public_cloud_protected_data.protected_data_public_cloud_get_all_protected_cloud_networks",
    ),
}

SERVICE_INFO = "about.about_get_service_info"
LICENSE_INFO = "licensing.licensing_get_info"
LICENSE_USAGE = "licensing.licensing_get_current_usage"
TRIGGERED_ALARMS = "alarms.alarms_get_triggered_alarms"
RESOLVE_ALARMS = "alarms.alarms_resolve_triggered_alarms"

OPERATIONS = (
    SERVICE_INFO,
    LICENSE_INFO,
    LICENSE_USAGE,
    TRIGGERED_ALARMS,
    RESOLVE_ALARMS,
    *(collection.operation for collection in COLLECTIONS.values()),
)

# Statuses across the job, repository, server and proxy enums that mean something is wrong.
# "Unknown" (and a missing status) is neither healthy nor a problem.
PROBLEM_STATUSES = frozenset(
    {
        "error",
        "failed",
        "warning",
        "disconnected",
        "inaccessible",
        "outofdate",
        "notresponding",
        "offline",
    }
)


def as_dict(value: Any) -> dict[str, Any]:
    """Convert an SDK model to a dictionary."""
    if value is None:
        return {}
    if hasattr(value, "to_dict"):
        return value.to_dict()
    return value if isinstance(value, dict) else {}


def is_problem(status: Any) -> bool | None:
    """Classify a status value: True for a problem, False when fine, None when unknown."""
    if status is None or str(status).lower() in {"", "unknown"}:
        return None
    return str(status).lower() in PROBLEM_STATUSES


def resource_name(item: dict[str, Any], fallback: str) -> str:
    """Return a human-readable resource name."""
    for key in ("name", "hostName"):
        value = item.get(key)
        if isinstance(value, str) and value:
            return value
    return fallback


class VeeamOneCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Fetch Veeam ONE monitoring data.

    `data` holds `service`, `license` and `license_usage` dicts, the `alarms` list,
    `totals` (collection key → resource count) and `resources` (key → {id: item}) for
    collections whose resources get devices.
    """

    config_entry: ConfigEntry

    def __init__(
        self, hass: HomeAssistant, entry: ConfigEntry, client: VeeamClient, api_version: str
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=DOMAIN,
            update_interval=timedelta(seconds=UPDATE_INTERVAL),
        )
        self.entry_id = entry.entry_id
        self.client = client
        self.api_version = api_version
        # Why each endpoint failed on the latest update, for diagnostics
        self.errors: dict[str, str] = {}
        # Collections fetched successfully in the latest update; only these are pruned.
        self.fetched: set[str] = set()
        # Unique IDs of entities currently added, so listeners only add new ones.
        self.known_ids: set[str] = set()
        # Device registry ID of the Veeam ONE server device, which resource devices hang off.
        self.device_id = ""
        self._semaphore = asyncio.Semaphore(MAX_CONCURRENT_REQUESTS)

    async def _fetch(self, operation: str, **kwargs: Any) -> Any:
        async with self._semaphore:
            return await fetch(self.client, operation, **kwargs)

    async def _fetch_all(self, operation: str, *, all_pages: bool) -> tuple[list[dict], int]:
        """Fetch a collection's items and its total count, following pages if asked."""
        items: list[dict[str, Any]] = []
        offset = 0
        while True:
            page = as_dict(await self._fetch(operation, limit=PAGE_LIMIT, offset=offset))
            batch = page.get("items") or []
            items.extend(batch)
            total = page.get("totalCount")
            total = total if isinstance(total, int) else len(items)
            offset += len(batch)
            if not all_pages or not batch or offset >= total:
                return items, total

    async def _alarms(self) -> list[dict[str, Any]]:
        items, _ = await self._fetch_all(TRIGGERED_ALARMS, all_pages=True)
        return items

    async def _optional(self, name: str, request: Any, default: Any) -> Any:
        """Await a request, keeping the previous value if it fails."""
        try:
            return await request
        except VeeamAuthenticationError:
            raise
        except Exception as err:  # noqa: BLE001 - one endpoint must not fail the update
            _LOGGER.debug("Veeam ONE %s request failed: %s", name, err)
            self.errors[name] = repr(err)
            return (self.data or {}).get(name, default)

    async def _collection(self, key: str, collection: Collection) -> tuple[list[dict], int] | None:
        try:
            return await self._fetch_all(collection.operation, all_pages=bool(collection.id_key))
        except VeeamAuthenticationError:
            raise
        except Exception as err:  # noqa: BLE001 - an unlicensed or absent platform is normal
            _LOGGER.debug("Veeam ONE collection %s failed: %s", key, err)
            self.errors[key] = repr(err)
            return None

    async def _async_update_data(self) -> dict[str, Any]:
        previous = self.data or {}
        self.errors = {}
        try:
            async with asyncio.timeout(UPDATE_TIMEOUT):
                service, license_info, license_usage, alarms, results = await asyncio.gather(
                    self._fetch(SERVICE_INFO),
                    self._optional("license", self._fetch(LICENSE_INFO), {}),
                    self._optional("license_usage", self._fetch(LICENSE_USAGE), {}),
                    self._optional("alarms", self._alarms(), []),
                    asyncio.gather(
                        *(self._collection(key, spec) for key, spec in COLLECTIONS.items())
                    ),
                )
        except VeeamAuthenticationError as err:
            raise ConfigEntryAuthFailed(
                translation_domain=DOMAIN, translation_key="authentication_failed"
            ) from err
        except Exception as err:
            raise UpdateFailed(
                translation_domain=DOMAIN,
                translation_key="update_failed",
                translation_placeholders={"error": str(err) or type(err).__name__},
            ) from err

        totals: dict[str, int] = dict(previous.get("totals", {}))
        resources: dict[str, dict[str, dict[str, Any]]] = dict(previous.get("resources", {}))
        self.fetched = set()
        for (key, spec), result in zip(COLLECTIONS.items(), results, strict=True):
            if result is None:
                continue
            items, total = result
            self.fetched.add(key)
            totals[key] = total
            if spec.id_key:
                resources[key] = {
                    str(item[spec.id_key]): item
                    for item in items
                    if item.get(spec.id_key) is not None
                }

        return {
            "service": as_dict(service),
            "license": as_dict(license_info),
            "license_usage": as_dict(license_usage),
            "alarms": alarms,
            "totals": totals,
            "resources": resources,
        }
