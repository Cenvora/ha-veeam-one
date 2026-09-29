"""Shared Veeam ONE entity helpers."""

from __future__ import annotations

import re
from typing import Any

from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import VeeamOneCoordinator


def resource_id(item: dict[str, Any]) -> str | None:
    """Return the stable identifier used by a Veeam ONE resource."""
    for key in (
        "id",
        "uid",
        "resourceId",
        "vmBackupJobUid",
        "vmReplicationJobUid",
        "vmCopyJobUid",
        "repositoryId",
        "backupJobId",
        "copyJobId",
        "hostId",
        "clusterId",
        "virtualMachineId",
        "vmId",
        "vCenterId",
        "datastoreId",
        "datastoreClusterId",
        "resourcePoolId",
        "vAppId",
        "organizationId",
        "orgVdcId",
        "providerVdcId",
        "serverId",
        "tenantId",
        "gatewayId",
        "gatewayPoolId",
        "proxyId",
        "objectStorageRepositoryId",
        "siteId",
        "teamId",
        "userId",
        "groupId",
        "fileServerId",
        "fileShareId",
        "physicalDiskId",
        "databaseId",
    ):
        value = item.get(key)
        if value is not None:
            return str(value)
    return None


def resource_name(item: dict[str, Any], fallback: str) -> str:
    """Return a human-readable resource name."""
    for key in ("name", "displayName", "hostName", "serverName"):
        value = item.get(key)
        if isinstance(value, str) and value:
            return value
    return fallback


def device_name(kind: str, name: str) -> str:
    """Name a resource device consistently."""
    if re.search(rf"\b{re.escape(kind)}\b", name, re.IGNORECASE):
        return f"Veeam ONE {name}"
    return f"Veeam ONE {kind} {name}"


def device_info(
    coordinator: VeeamOneCoordinator, kind: str, object_id: str, name: str
) -> dict[str, Any]:
    """Return Home Assistant device information for a resource."""
    return {
        "identifiers": {(DOMAIN, coordinator.entry_id, kind, object_id)},
        "name": device_name(kind.replace("_", " ").title(), name),
        "manufacturer": "Veeam",
        "model": f"Veeam ONE {kind.replace('_', ' ').title()}",
    }


class VeeamOneEntity(CoordinatorEntity[VeeamOneCoordinator]):
    """Base Veeam ONE entity."""

    _attr_has_entity_name = True

    def __init__(
        self, coordinator: VeeamOneCoordinator, kind: str, object_id: str, name: str
    ) -> None:
        super().__init__(coordinator)
        self.kind = kind
        self.object_id = object_id
        self.resource_name = name

    @property
    def device_info(self) -> dict[str, Any]:
        return device_info(self.coordinator, self.kind, self.object_id, self.resource_name)

    def item(self) -> dict[str, Any]:
        """Find this resource in the latest coordinator data."""
        for item in self.coordinator.data.get("collections", {}).get(self.kind, []):
            if resource_id(item) == self.object_id:
                return item
        return {}

    @property
    def available(self) -> bool:
        return super().available and bool(self.item())
