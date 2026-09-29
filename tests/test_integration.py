"""Set up the integration against a fake Veeam ONE and check what it creates."""

from __future__ import annotations

import copy
from datetime import timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers import issue_registry as ir
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
)

from custom_components.veeam_one.const import DOMAIN, UPDATE_INTERVAL
from custom_components.veeam_one.coordinator import (
    COLLECTIONS,
    LICENSE_INFO,
    LICENSE_USAGE,
    RESOLVE_ALARMS,
    SERVICE_INFO,
    TRIGGERED_ALARMS,
)
from custom_components.veeam_one.sdk import VeeamOneApiError

ENTRY_DATA = {
    "host": "one.example",
    "port": 1239,
    "username": "user",
    "password": "pass",
    "verify_ssl": False,
}


def _page(items):
    return {"items": items, "totalCount": len(items)}


def _responses():
    # All three repositories share proxyId 408, which 0.1.0 mistook for their ID.
    repositories = [
        {
            "backupRepositoryId": 409 + index,
            "proxyId": 408,
            "vb365ServerId": 407,
            "name": f"Repository {index}",
            "capacityBytes": 1000,
            "freeSpaceBytes": 250,
        }
        for index in range(3)
    ]
    return {
        SERVICE_INFO: {"product": "Veeam ONE", "version": "13.0.1.5924"},
        LICENSE_INFO: {
            "type": "Nfr",
            "package": "Suite",
            "expirationDate": "2020-01-01T00:00:00Z",
            "supportExpirationDate": None,
        },
        LICENSE_USAGE: {
            "units": [{"licenseUnit": "Instances", "used": "3", "licensed": "10", "available": "7"}]
        },
        TRIGGERED_ALARMS: _page(
            [
                {"triggeredAlarmId": 1, "name": "Job failed", "status": "Error"},
                {"triggeredAlarmId": 2, "name": "Proxy slow", "status": "Warning"},
                {"triggeredAlarmId": 3, "name": "Old", "status": "Resolved"},
            ]
        ),
        COLLECTIONS["m365_repositories"].operation: _page(repositories),
        COLLECTIONS["m365_backup_jobs"].operation: _page(
            [
                {
                    "backupJobUid": "b1",
                    "name": "Main Job",
                    "status": "Failed",
                    "lastRun": "2026-09-28T22:01:42Z",
                }
            ]
        ),
        COLLECTIONS["m365_users"].operation: {"items": [{"name": "u"}], "totalCount": 5},
    }


class FakeVeeamOne:
    """Stands in for sdk.fetch."""

    def __init__(self) -> None:
        self.responses = _responses()
        self.calls: list[tuple[str, dict]] = []
        self.failing = {COLLECTIONS["vsphere_vms"].operation}

    async def __call__(self, client, operation, **kwargs):
        self.calls.append((operation, kwargs))
        if operation in self.failing:
            raise VeeamOneApiError(f"{operation} returned HTTP 404")
        if operation == RESOLVE_ALARMS:
            return None
        return copy.deepcopy(self.responses.get(operation, _page([])))


@pytest.fixture
def fake():
    fake = FakeVeeamOne()
    client = MagicMock()
    client.connect = AsyncMock()
    client.close = AsyncMock()
    client.package = "veeam_one.v2_3"
    with (
        patch("custom_components.veeam_one.coordinator.fetch", fake),
        patch("custom_components.veeam_one.services.fetch", fake),
        patch("custom_components.veeam_one.create_client", return_value=client),
        patch(
            "custom_components.veeam_one.api_version.detect_api_version",
            AsyncMock(return_value="2.3"),
        ),
    ):
        yield fake


async def _setup(hass: HomeAssistant, **kwargs) -> MockConfigEntry:
    entry = MockConfigEntry(
        domain=DOMAIN, data=ENTRY_DATA, unique_id="one.example:1239", minor_version=2, **kwargs
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


async def _poll(hass: HomeAssistant) -> None:
    """Run the next scheduled coordinator update, which runs as a background task."""
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=UPDATE_INTERVAL + 1))
    await hass.async_block_till_done(wait_background_tasks=True)


def _state(hass: HomeAssistant, entity_id: str):
    state = hass.states.get(entity_id)
    assert state is not None, f"{entity_id} missing"
    return state


async def test_alarms_count_only_active_ones(hass: HomeAssistant, fake) -> None:
    await _setup(hass)
    active = _state(hass, "sensor.veeam_one_active_alarms")
    assert active.state == "2"
    assert [alarm["id"] for alarm in active.attributes["alarms"]] == [1, 2]
    assert _state(hass, "sensor.veeam_one_error_alarms").state == "1"
    assert _state(hass, "sensor.veeam_one_warning_alarms").state == "1"
    # No per-alarm devices or buttons.
    assert not hass.states.async_entity_ids("button")


async def test_license_and_version(hass: HomeAssistant, fake) -> None:
    await _setup(hass)
    assert _state(hass, "sensor.veeam_one_version").state == "13.0.1.5924"
    assert _state(hass, "sensor.veeam_one_license_instances_used").state == "3"
    assert _state(hass, "sensor.veeam_one_license_instances_used_percentage").state == "30.0"
    assert _state(hass, "binary_sensor.veeam_one_license_expired").state == "on"
    assert int(_state(hass, "sensor.veeam_one_license_days_remaining").state) < 0


async def test_resources_get_their_own_ids(hass: HomeAssistant, fake) -> None:
    entry = await _setup(hass)
    devices = dr.async_entries_for_config_entry(dr.async_get(hass), entry.entry_id)
    names = {device.name for device in devices}
    assert {"Veeam ONE Repository 0", "Veeam ONE Repository 1", "Veeam ONE Repository 2"} <= names
    assert _state(hass, "sensor.veeam_one_repository_2_free_space_percentage").state == "25.0"
    assert _state(hass, "binary_sensor.veeam_one_main_job_problem").state == "on"
    assert _state(hass, "sensor.veeam_one_main_job_status").state == "Failed"


async def test_only_populated_collections_get_entities(hass: HomeAssistant, fake) -> None:
    await _setup(hass)
    assert _state(hass, "sensor.veeam_one_microsoft_365_users").state == "5"
    assert _state(hass, "binary_sensor.veeam_one_microsoft_365_backup_jobs_problem").state == "on"
    entity_ids = hass.states.async_entity_ids()
    assert not [entity_id for entity_id in entity_ids if "vsphere" in entity_id]
    assert not [entity_id for entity_id in entity_ids if "hyper_v" in entity_id]


async def test_vanished_resource_device_is_removed(hass: HomeAssistant, fake) -> None:
    entry = await _setup(hass)
    operation = COLLECTIONS["m365_repositories"].operation
    fake.responses[operation]["items"].pop()
    fake.responses[operation]["totalCount"] = 2
    await _poll(hass)
    names = {
        device.name
        for device in dr.async_entries_for_config_entry(dr.async_get(hass), entry.entry_id)
    }
    assert "Veeam ONE Repository 2" not in names
    assert "Veeam ONE Repository 1" in names


async def test_failed_collection_keeps_its_devices(hass: HomeAssistant, fake) -> None:
    entry = await _setup(hass)
    fake.failing.add(COLLECTIONS["m365_repositories"].operation)
    await _poll(hass)
    names = {
        device.name
        for device in dr.async_entries_for_config_entry(dr.async_get(hass), entry.entry_id)
    }
    assert "Veeam ONE Repository 2" in names


async def test_new_resources_are_added(hass: HomeAssistant, fake) -> None:
    await _setup(hass)
    operation = COLLECTIONS["m365_backup_jobs"].operation
    fake.responses[operation]["items"].append(
        {"backupJobUid": "b2", "name": "Second Job", "status": "Success"}
    )
    await _poll(hass)
    assert _state(hass, "sensor.veeam_one_second_job_status").state == "Success"


async def test_resolve_alarm_service(hass: HomeAssistant, fake) -> None:
    await _setup(hass)
    await hass.services.async_call(DOMAIN, "resolve_alarm", {"alarm_ids": [1]}, blocking=True)
    operation, kwargs = next(call for call in fake.calls if call[0] == RESOLVE_ALARMS)
    assert kwargs["body"].triggered_alarm_ids == [1]


async def test_migration_clears_old_registry_entries(hass: HomeAssistant, fake) -> None:
    entry = MockConfigEntry(
        domain=DOMAIN, data=ENTRY_DATA, unique_id="one.example:1239", minor_version=1
    )
    entry.add_to_hass(hass)
    old_device = dr.async_get(hass).async_get_or_create(
        config_entry_id=entry.entry_id, identifiers={(DOMAIN, "old-alarm-device")}
    )
    er.async_get(hass).async_get_or_create(
        "button",
        DOMAIN,
        f"{entry.entry_id}_alarm_1_resolve",
        config_entry=entry,
        device_id=old_device.id,
    )
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.LOADED
    assert entry.minor_version == 2
    assert dr.async_get(hass).async_get(old_device.id) is None
    assert not hass.states.async_entity_ids("button")


async def test_diagnostics_redact_secrets(hass: HomeAssistant, fake) -> None:
    from custom_components.veeam_one.diagnostics import async_get_config_entry_diagnostics

    fake.responses[LICENSE_INFO]["company"] = "Secret Corp"
    entry = await _setup(hass)
    diagnostics = await async_get_config_entry_diagnostics(hass, entry)
    assert diagnostics["entry"]["data"]["password"] == "**REDACTED**"
    assert diagnostics["entry"]["data"]["host"] == "**REDACTED**"
    assert diagnostics["license"]["company"] == "**REDACTED**"
    assert diagnostics["entry"]["resolved_api_version"] == "2.3"
    assert diagnostics["alarms_by_status"] == {"Error": 1, "Warning": 1, "Resolved": 1}
    assert diagnostics["collections"]["m365_repositories"] == {
        "total": 3,
        "devices": 3,
        "fetched": True,
    }
    assert "vsphere_vms" in diagnostics["coordinator"]["errors"]


async def test_expired_license_raises_a_repair_issue(hass: HomeAssistant, fake) -> None:
    entry = await _setup(hass)
    issue = ir.async_get(hass).async_get_issue(DOMAIN, f"license_expiration_{entry.entry_id}")
    assert issue is not None
    assert issue.translation_key == "license_expired"

    # Renewed: the issue clears on the next poll
    fake.responses[LICENSE_INFO]["expirationDate"] = "2099-01-01T00:00:00Z"
    await _poll(hass)
    assert (
        ir.async_get(hass).async_get_issue(DOMAIN, f"license_expiration_{entry.entry_id}") is None
    )


async def test_expiring_license_warns(hass: HomeAssistant, fake) -> None:
    soon = (dt_util.utcnow() + timedelta(days=10)).isoformat()
    fake.responses[LICENSE_INFO]["expirationDate"] = soon
    entry = await _setup(hass)
    issue = ir.async_get(hass).async_get_issue(DOMAIN, f"license_expiration_{entry.entry_id}")
    assert issue.translation_key == "license_expiring"
    await hass.config_entries.async_remove(entry.entry_id)
    assert (
        ir.async_get(hass).async_get_issue(DOMAIN, f"license_expiration_{entry.entry_id}") is None
    )


async def test_rejected_credentials_start_reauth(hass: HomeAssistant, fake) -> None:
    from veeam_one import VeeamAuthenticationError

    client = MagicMock()
    client.connect = AsyncMock(side_effect=VeeamAuthenticationError("no"))
    client.close = AsyncMock()
    with patch("custom_components.veeam_one.create_client", return_value=client):
        entry = MockConfigEntry(domain=DOMAIN, data=ENTRY_DATA, minor_version=2)
        entry.add_to_hass(hass)
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.SETUP_ERROR
    assert [flow["context"]["source"] for flow in hass.config_entries.flow.async_progress()] == [
        "reauth"
    ]


async def test_unreachable_server_retries(hass: HomeAssistant, fake) -> None:
    client = MagicMock()
    client.connect = AsyncMock(side_effect=OSError("refused"))
    client.close = AsyncMock()
    with patch("custom_components.veeam_one.create_client", return_value=client):
        entry = MockConfigEntry(domain=DOMAIN, data=ENTRY_DATA, minor_version=2)
        entry.add_to_hass(hass)
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.SETUP_RETRY
    client.close.assert_awaited()


async def test_failed_poll_marks_entities_unavailable(hass: HomeAssistant, fake) -> None:
    await _setup(hass)
    fake.failing.add(SERVICE_INFO)
    await _poll(hass)
    assert _state(hass, "sensor.veeam_one_active_alarms").state == "unavailable"
    assert _state(hass, "binary_sensor.veeam_one_connected").state == "off"


async def test_unload_closes_the_client(hass: HomeAssistant, fake) -> None:
    entry = await _setup(hass)
    client = entry.runtime_data.client
    assert await hass.config_entries.async_unload(entry.entry_id)
    assert entry.state is ConfigEntryState.NOT_LOADED
    client.close.assert_awaited()


async def test_only_vanished_devices_can_be_deleted(hass: HomeAssistant, fake) -> None:
    from custom_components.veeam_one import async_remove_config_entry_device

    entry = await _setup(hass)
    registry = dr.async_get(hass)
    current = next(
        device
        for device in dr.async_entries_for_config_entry(registry, entry.entry_id)
        if device.name == "Veeam ONE Repository 0"
    )
    stale = registry.async_get_or_create(
        config_entry_id=entry.entry_id, identifiers={(DOMAIN, f"{entry.entry_id}:jobs:gone")}
    )
    assert not await async_remove_config_entry_device(hass, entry, current)
    assert await async_remove_config_entry_device(hass, entry, stale)


async def test_resolve_alarm_errors(hass: HomeAssistant, fake) -> None:
    from homeassistant.exceptions import HomeAssistantError, ServiceValidationError

    entry = await _setup(hass)
    fake.failing.add(RESOLVE_ALARMS)
    with pytest.raises(HomeAssistantError, match="HTTP 404"):
        await hass.services.async_call(DOMAIN, "resolve_alarm", {"alarm_ids": [1]}, blocking=True)

    await hass.config_entries.async_unload(entry.entry_id)
    with pytest.raises(ServiceValidationError, match="No loaded Veeam ONE server"):
        await hass.services.async_call(DOMAIN, "resolve_alarm", {"alarm_ids": [1]}, blocking=True)
