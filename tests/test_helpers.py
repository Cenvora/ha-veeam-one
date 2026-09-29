"""Tests for pure helpers."""

from http import HTTPStatus
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from veeam_one import VeeamAuthenticationError

from custom_components.veeam_one.coordinator import (
    COLLECTIONS,
    OPERATIONS,
    as_dict,
    is_problem,
    resource_name,
)
from custom_components.veeam_one.entity import active_alarms, parse_timestamp
from custom_components.veeam_one.sdk import PACKAGE, VeeamOneApiError, fetch, prepare_sdk
from custom_components.veeam_one.sensor import _number


class Model:
    def to_dict(self):
        return {"items": [{"name": "Job"}], "totalCount": 1}


def test_as_dict():
    assert as_dict(Model())["totalCount"] == 1
    assert as_dict(None) == {}


def test_every_operation_exists_in_the_sdk():
    import importlib

    prepare_sdk(OPERATIONS)
    for operation in OPERATIONS:
        assert hasattr(importlib.import_module(f"{PACKAGE}.api.{operation}"), "asyncio_detailed")


def test_device_collections_name_their_own_id_and_status():
    assert COLLECTIONS["m365_repositories"].id_key == "backupRepositoryId"
    assert COLLECTIONS["copy_jobs"].id_key == "backupCopyJobUid"
    assert COLLECTIONS["servers"].status_key == "connectionState"
    # Users, VMs and protected objects are only counted.
    assert COLLECTIONS["m365_users"].id_key is None
    assert COLLECTIONS["vsphere_vms"].id_key is None


def test_is_problem_matches_whole_statuses():
    assert is_problem("Failed") is True
    assert is_problem("Disconnected") is True
    assert is_problem("NotResponding") is True
    assert is_problem("Connected") is False
    assert is_problem("Success") is False
    assert is_problem("Running") is False
    assert is_problem("Unknown") is None
    assert is_problem(None) is None


def test_resource_name_falls_back_cleanly():
    assert resource_name({"name": "Nightly"}, "fallback") == "Nightly"
    assert resource_name({}, "fallback") == "fallback"


def test_active_alarms_filter_on_status():
    data = {
        "alarms": [
            {"status": "Error"},
            {"status": "Warning"},
            {"status": "Resolved"},
            {"status": "Information"},
        ]
    }
    assert len(active_alarms(data)) == 2
    assert active_alarms(data, "Error") == [{"status": "Error"}]


def test_license_usage_strings_become_numbers():
    assert _number("12") == 12
    assert _number("2.5") == 2.5
    assert _number(None) is None
    assert _number("n/a") is None


def test_parse_timestamp_assumes_utc():
    assert parse_timestamp("2026-01-01T00:00:00").tzinfo is not None
    assert parse_timestamp("garbage") is None
    assert parse_timestamp(None) is None


def _client(status: int, parsed=None):
    response = SimpleNamespace(status_code=HTTPStatus(status), parsed=parsed)
    return SimpleNamespace(call=AsyncMock(return_value=response))


async def test_fetch_raises_on_error_status():
    with pytest.raises(VeeamOneApiError):
        await fetch(_client(403), "about.about_get_service_info")
    with pytest.raises(VeeamAuthenticationError):
        await fetch(_client(401), "about.about_get_service_info")
    assert await fetch(_client(200, {"version": "13"}), "about.about_get_service_info") == {
        "version": "13"
    }
