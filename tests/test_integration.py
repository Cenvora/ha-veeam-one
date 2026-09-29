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
    with (
        patch("custom_components.veeam_one.coordinator.fetch", fake),
        patch("custom_components.veeam_one.services.fetch", fake),
        patch("custom_components.veeam_one.create_client", return_value=client),
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
