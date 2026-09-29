"""Behavioural tests: the shipped blueprints running as automations in Home Assistant.

test_blueprints.py checks the files' structure; these load each blueprint through Home
Assistant's own blueprint machinery, create devices and entities the way the integration names
them ("Veeam ONE Nightly VMs", ...) without setting the integration up, drive the state and
attribute changes its polls produce, and check what the notification action receives — or
that it is not run at all.
"""

from __future__ import annotations

import shutil
from datetime import timedelta
from pathlib import Path
from typing import Any

import pytest

pytest.importorskip("pytest_homeassistant_custom_component")

from homeassistant.components import automation  # noqa: E402
from homeassistant.core import HomeAssistant, ServiceCall  # noqa: E402
from homeassistant.helpers import device_registry as dr  # noqa: E402
from homeassistant.helpers import entity_registry as er  # noqa: E402
from homeassistant.setup import async_setup_component  # noqa: E402
from homeassistant.util import dt as dt_util  # noqa: E402
from pytest_homeassistant_custom_component.common import (  # noqa: E402
    MockConfigEntry,
    async_fire_time_changed,
    async_mock_service,
)

from custom_components.veeam_one.const import DOMAIN  # noqa: E402

BLUEPRINT_DIR = Path(__file__).parent.parent / "blueprints" / "automation" / "veeam_one"

NOTIFY = [{"action": "test.notify", "data": {"title": "{{ title }}", "message": "{{ message }}"}}]
RECOVER = [{"action": "test.recover", "data": {"title": "{{ title }}", "message": "{{ message }}"}}]

ENTRY_ID = "entry-one01"
ALARMS = "sensor.veeam_one_active_alarms"


@pytest.fixture
async def entry(hass: HomeAssistant, tmp_path: Path) -> MockConfigEntry:
    """A config entry to hang devices on, titled as the config flow titles it. Never set up."""
    hass.config.config_dir = str(tmp_path)
    target = tmp_path / "blueprints" / "automation" / DOMAIN
    target.mkdir(parents=True)
    for path in BLUEPRINT_DIR.glob("*.yaml"):
        shutil.copy(path, target / path.name)

    # Times in these tests are written in UTC
    await hass.config.async_set_time_zone("UTC")

    config_entry = MockConfigEntry(
        domain=DOMAIN, title="Veeam ONE (one.example.com)", entry_id=ENTRY_ID
    )
    config_entry.add_to_hass(hass)
    yield config_entry

    # Time triggers and pending "for:" timers last as long as their automation is on
    if hass.services.has_service(automation.DOMAIN, "turn_off"):
        await hass.services.async_call(
            automation.DOMAIN, "turn_off", {"entity_id": "all"}, blocking=True
        )
        await hass.async_block_till_done()


@pytest.fixture
def notified(hass: HomeAssistant) -> list[ServiceCall]:
    return async_mock_service(hass, "test", "notify")


@pytest.fixture
def recovered(hass: HomeAssistant) -> list[ServiceCall]:
    return async_mock_service(hass, "test", "recover")


def add_entity(
    hass: HomeAssistant,
    entry: MockConfigEntry,
    entity_id: str,
    state: str,
    attributes: dict[str, Any] | None = None,
    *,
    device: str | None = None,
    model: str | None = None,
) -> str:
    """Register an entity on a device, as the integration would, and give it a state.

    Without `device` the entity goes on the Veeam ONE server device.
    """
    device_entry = dr.async_get(hass).async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, f"{entry.entry_id}:{device}" if device else entry.entry_id)},
        name=f"Veeam ONE {device}" if device else "Veeam ONE",
        model=model or "Veeam ONE",
        manufacturer="Veeam",
    )
    domain, object_id = entity_id.split(".")
    registered = er.async_get(hass).async_get_or_create(
        domain,
        DOMAIN,
        f"{entry.entry_id}_{object_id}",
        suggested_object_id=object_id,
        config_entry=entry,
        device_id=device_entry.id,
    )
    assert registered.entity_id == entity_id
    hass.states.async_set(entity_id, state, attributes or {})
    return entity_id


async def use_blueprint(hass: HomeAssistant, name: str, inputs: dict[str, Any]) -> None:
    """Create an automation from one shipped blueprint."""
    assert await async_setup_component(
        hass,
        automation.DOMAIN,
        {automation.DOMAIN: {"use_blueprint": {"path": f"{DOMAIN}/{name}", "input": inputs}}},
    )
    await hass.async_block_till_done()
    # A blueprint that fails to load leaves no automation behind rather than raising
    assert hass.states.async_entity_ids(automation.DOMAIN), f"{name} did not load"


async def set_state(hass, entity_id, state, attributes=None) -> None:
    hass.states.async_set(entity_id, state, attributes or {})
    await hass.async_block_till_done()


async def advance(hass, freezer, delta: timedelta) -> None:
    freezer.tick(delta)
    async_fire_time_changed(hass, dt_util.utcnow())
    await hass.async_block_till_done()


# ---------------------------------------------------------------------------
# Alarm triggered
# ---------------------------------------------------------------------------


def alarm(alarm_id: int, status: str = "Error", minute: int = 0, **overrides) -> dict:
    """One entry of the Active alarms sensor's `alarms` attribute."""
    return {
        "id": alarm_id,
        "name": f"Alarm {alarm_id}",
        "status": status,
        "triggered": f"2026-09-28T{8 + minute // 60:02d}:{minute % 60:02d}:00+00:00",
        "object": "Nightly VMs",
        "description": None,
        "repeat_count": 1,
        **overrides,
    }


async def set_alarms(hass, alarms: list[dict]) -> None:
    """Write the sensor as AlarmCountSensor does: the count, and the alarms newest first."""
    listed = sorted(alarms, key=lambda a: a["triggered"], reverse=True)[:50]
    await set_state(hass, ALARMS, str(len(alarms)), {"alarms": listed})


@pytest.fixture
def alarm_sensor(hass, entry) -> str:
    return add_entity(hass, entry, ALARMS, "0", {"alarms": []})


async def test_alarm_new_alarm_notifies(hass, entry, alarm_sensor, notified):
    action = [
        {
            "action": "test.notify",
            "data": {
                "title": "{{ title }}",
                "message": "{{ message }}",
                "alarm_ids": "{{ alarm_ids }}",
                "config_entry_id": "{{ entry_id }}",
            },
        }
    ]
    await use_blueprint(
        hass,
        "alarm_triggered.yaml",
        {"alarm_sensors": [alarm_sensor], "notification_action": action},
    )

    await set_alarms(
        hass,
        [alarm(7, name="Job state", description="Job Nightly VMs finished with error. ")],
    )

    assert len(notified) == 1
    data = notified[0].data
    assert data["title"] == "Veeam ONE error: Job state"
    assert data["message"] == (
        "Error: Job state on Nightly VMs. Job Nightly VMs finished with error.\n"
        "Server: one.example.com."
    )
    # What veeam_one.resolve_alarm takes
    assert data["alarm_ids"] == [7]
    assert data["config_entry_id"] == ENTRY_ID


async def test_alarm_several_in_one_poll_arrive_together(hass, entry, alarm_sensor, notified):
    await use_blueprint(
        hass,
        "alarm_triggered.yaml",
        {"alarm_sensors": [alarm_sensor], "notification_action": NOTIFY},
    )

    await set_alarms(hass, [alarm(1, minute=1), alarm(2, "Warning", minute=2, object=None)])

    assert len(notified) == 1
    assert notified[0].data["title"] == "Veeam ONE: 2 new alarms"
    assert notified[0].data["message"] == (
        "Warning: Alarm 2\nError: Alarm 1 on Nightly VMs\nServer: one.example.com."
    )


async def test_alarm_is_reported_once(hass, entry, alarm_sensor, notified):
    await use_blueprint(
        hass,
        "alarm_triggered.yaml",
        {"alarm_sensors": [alarm_sensor], "notification_action": NOTIFY},
    )

    await set_alarms(hass, [alarm(1)])
    # Next polls: the same alarm, repeating, then another alarm alongside it
    await set_alarms(hass, [alarm(1, repeat_count=4)])
    await set_alarms(hass, [alarm(1, repeat_count=4), alarm(2, minute=5)])

    assert [call.data["title"] for call in notified] == [
        "Veeam ONE error: Alarm 1",
        "Veeam ONE error: Alarm 2",
    ]


async def test_alarm_ignores_a_reload(hass, entry, alarm_sensor, notified, recovered):
    await set_alarms(hass, [alarm(1)])
    await use_blueprint(
        hass,
        "alarm_triggered.yaml",
        {
            "alarm_sensors": [alarm_sensor],
            "notification_action": NOTIFY,
            "recovery_action": RECOVER,
        },
    )

    # A failed poll or reload drops the attribute; the same alarms come back
    await set_state(hass, ALARMS, "unavailable")
    await set_alarms(hass, [alarm(1)])
    # A restart removes the state altogether
    hass.states.async_remove(ALARMS)
    await hass.async_block_till_done()
    await set_alarms(hass, [alarm(1)])

    assert notified == []
    assert recovered == []


async def test_alarm_escalation(hass, entry, alarm_sensor, notified):
    await use_blueprint(
        hass,
        "alarm_triggered.yaml",
        {"alarm_sensors": [alarm_sensor], "notification_action": NOTIFY},
    )

    await set_alarms(hass, [alarm(1, "Warning")])
    await set_alarms(hass, [alarm(1, "Error")])

    assert len(notified) == 2
    assert notified[1].data["title"] == "Veeam ONE alarm escalated: Alarm 1"
    assert notified[1].data["message"].startswith("Error (escalated): Alarm 1 on Nightly VMs")


async def test_alarm_escalation_can_be_turned_off(hass, entry, alarm_sensor, notified):
    await use_blueprint(
        hass,
        "alarm_triggered.yaml",
        {
            "alarm_sensors": [alarm_sensor],
            "notification_action": NOTIFY,
            "include_escalations": False,
        },
    )

    await set_alarms(hass, [alarm(1, "Warning")])
    await set_alarms(hass, [alarm(1, "Error")])

    assert len(notified) == 1


async def test_alarm_errors_only(hass, entry, alarm_sensor, notified):
    """A warning is skipped, and reported once it becomes an error."""
    await use_blueprint(
        hass,
        "alarm_triggered.yaml",
        {
            "alarm_sensors": [alarm_sensor],
            "notification_action": NOTIFY,
            "statuses": ["Error"],
            "include_escalations": False,
        },
    )

    await set_alarms(hass, [alarm(1, "Warning")])
    assert notified == []

    await set_alarms(hass, [alarm(1, "Error")])
    assert len(notified) == 1
    assert notified[0].data["title"] == "Veeam ONE alarm escalated: Alarm 1"


async def test_alarm_resolved(hass, entry, alarm_sensor, notified, recovered):
    await use_blueprint(
        hass,
        "alarm_triggered.yaml",
        {
            "alarm_sensors": [alarm_sensor],
            "notification_action": NOTIFY,
            "recovery_action": RECOVER,
        },
    )

    await set_alarms(hass, [alarm(1), alarm(2, minute=1)])
    await set_alarms(hass, [alarm(2, minute=1)])

    assert len(notified) == 1
    assert len(recovered) == 1
    assert recovered[0].data["title"] == "Veeam ONE alarm resolved: Alarm 1"
    assert recovered[0].data["message"] == (
        "Alarm 1 on Nightly VMs is no longer active.\nServer: one.example.com."
    )

    # Raised and resolved in the same poll: both actions run, each with its own text
    await set_alarms(hass, [alarm(3, minute=2)])
    assert notified[-1].data["title"] == "Veeam ONE error: Alarm 3"
    assert recovered[-1].data["title"] == "Veeam ONE alarm resolved: Alarm 2"


async def test_alarm_resolved_without_a_recovery_action(hass, entry, alarm_sensor, notified):
    await use_blueprint(
        hass,
        "alarm_triggered.yaml",
        {"alarm_sensors": [alarm_sensor], "notification_action": NOTIFY},
    )

    await set_alarms(hass, [alarm(1)])
    await set_alarms(hass, [])

    assert len(notified) == 1


async def test_alarm_list_cap_is_not_raising_or_resolving(
    hass, entry, alarm_sensor, notified, recovered
):
    """The attribute holds the newest 50; alarms sliding in and out of it are not news."""
    many = [alarm(i, minute=i) for i in range(1, 52)]  # 51 alarms, #1 the oldest
    await set_alarms(hass, many)
    await use_blueprint(
        hass,
        "alarm_triggered.yaml",
        {
            "alarm_sensors": [alarm_sensor],
            "notification_action": NOTIFY,
            "recovery_action": RECOVER,
        },
    )

    # #30 is resolved, so #1 slides into the list
    many = [a for a in many if a["id"] != 30]
    await set_alarms(hass, many)
    assert notified == []
    assert [call.data["title"] for call in recovered] == ["Veeam ONE alarm resolved: Alarm 30"]

    # A new alarm pushes #1 back out: the new one is reported, #1 is not "resolved"
    many.append(alarm(100, minute=100))
    await set_alarms(hass, many)
    assert [call.data["title"] for call in notified] == ["Veeam ONE error: Alarm 100"]
    assert len(recovered) == 1


# ---------------------------------------------------------------------------
# Server unreachable
# ---------------------------------------------------------------------------


@pytest.fixture
def connected(hass, entry) -> str:
    return add_entity(
        hass, entry, "binary_sensor.veeam_one_connected", "on", {"device_class": "connectivity"}
    )


async def test_server_unreachable_and_back(hass, freezer, connected, notified, recovered):
    await use_blueprint(
        hass,
        "server_unreachable.yaml",
        {
            "connected_sensors": [connected],
            "notification_action": NOTIFY,
            "recovery_action": RECOVER,
        },
    )

    await set_state(hass, connected, "off")
    await advance(hass, freezer, timedelta(minutes=4))
    assert notified == []
    await advance(hass, freezer, timedelta(minutes=2))

    assert len(notified) == 1
    assert notified[0].data["title"] == "Veeam ONE unreachable: one.example.com"
    assert "not been able to reach Veeam ONE on one.example.com" in notified[0].data["message"]

    await set_state(hass, connected, "on")
    assert len(recovered) == 1
    assert recovered[0].data == {
        "title": "Veeam ONE reachable again: one.example.com",
        "message": "Veeam ONE on one.example.com is answering again.",
    }


async def test_server_unreachable_blip(hass, freezer, connected, notified, recovered):
    """One failed poll raises neither an alert nor a recovery."""
    await use_blueprint(
        hass,
        "server_unreachable.yaml",
        {
            "connected_sensors": [connected],
            "notification_action": NOTIFY,
            "recovery_action": RECOVER,
        },
    )

    await set_state(hass, connected, "off")
    await advance(hass, freezer, timedelta(minutes=1))
    await set_state(hass, connected, "on")
    await advance(hass, freezer, timedelta(minutes=10))

    assert notified == []
    assert recovered == []


async def test_server_unreachable_uses_a_title_the_user_chose(
    hass, freezer, entry, connected, notified
):
    hass.config_entries.async_update_entry(entry, title="Head office")
    await use_blueprint(
        hass,
        "server_unreachable.yaml",
        {"connected_sensors": [connected], "notification_action": NOTIFY},
    )

    await set_state(hass, connected, "off")
    await advance(hass, freezer, timedelta(minutes=6))

    assert notified[0].data["title"] == "Veeam ONE unreachable: Head office"


# ---------------------------------------------------------------------------
# Resource problem
# ---------------------------------------------------------------------------


@pytest.fixture
def job(hass, entry) -> tuple[str, str]:
    problem = add_entity(
        hass,
        entry,
        "binary_sensor.veeam_one_nightly_vms_problem",
        "off",
        {"device_class": "problem", "friendly_name": "Veeam ONE Nightly VMs Problem"},
        device="Nightly VMs",
        model="VBR Backup Job",
    )
    status = add_entity(
        hass,
        entry,
        "sensor.veeam_one_nightly_vms_status",
        "Success",
        device="Nightly VMs",
        model="VBR Backup Job",
    )
    return problem, status


async def test_resource_problem_and_recovery(hass, job, notified, recovered):
    problem, status = job
    await use_blueprint(
        hass,
        "resource_problem.yaml",
        {
            "problem_sensors": [problem],
            "notification_action": NOTIFY,
            "recovery_action": RECOVER,
        },
    )

    # One poll updates both; the status sensor is written first, as it is created first
    await set_state(hass, status, "Failed")
    await set_state(hass, problem, "on", {"device_class": "problem"})

    assert len(notified) == 1
    assert notified[0].data == {
        "title": "Veeam ONE: Nightly VMs reports Failed",
        "message": "Nightly VMs (VBR Backup Job) reports status Failed in Veeam ONE.",
    }

    await set_state(hass, status, "Success")
    await set_state(hass, problem, "off", {"device_class": "problem"})

    assert len(recovered) == 1
    assert recovered[0].data == {
        "title": "Veeam ONE: Nightly VMs is OK again",
        "message": "Nightly VMs (VBR Backup Job) is back to Success.",
    }


async def test_resource_problem_ignores_a_reload(hass, job, notified, recovered):
    problem, status = job
    await set_state(hass, problem, "on", {"device_class": "problem"})
    await use_blueprint(
        hass,
        "resource_problem.yaml",
        {
            "problem_sensors": [problem],
            "notification_action": NOTIFY,
            "recovery_action": RECOVER,
        },
    )

    await set_state(hass, problem, "unavailable")
    await set_state(hass, problem, "on")
    # Status Unknown makes Problem unknown, which is neither
    await set_state(hass, problem, "unknown")
    await set_state(hass, problem, "on")
    await set_state(hass, problem, "unavailable")
    await set_state(hass, problem, "off")

    assert notified == []
    assert recovered == []


async def test_resource_problem_delay(hass, freezer, job, notified, recovered):
    problem, _ = job
    await use_blueprint(
        hass,
        "resource_problem.yaml",
        {
            "problem_sensors": [problem],
            "problem_for": {"minutes": 5},
            "notification_action": NOTIFY,
            "recovery_action": RECOVER,
        },
    )

    # Shorter than the delay: neither alert nor recovery
    await set_state(hass, problem, "on")
    await advance(hass, freezer, timedelta(minutes=2))
    await set_state(hass, problem, "off")
    await advance(hass, freezer, timedelta(minutes=10))
    assert notified == []
    assert recovered == []

    await set_state(hass, problem, "on")
    await advance(hass, freezer, timedelta(minutes=6))
    await set_state(hass, problem, "off")
    assert len(notified) == 1
    assert len(recovered) == 1


async def test_resource_problem_keeps_a_user_given_name(hass, job, notified):
    problem, status = job
    device_id = er.async_get(hass).async_get(problem).device_id
    dr.async_get(hass).async_update_device(device_id, name_by_user="Veeam ONE nightly")
    await use_blueprint(
        hass,
        "resource_problem.yaml",
        {"problem_sensors": [problem], "notification_action": NOTIFY},
    )

    await set_state(hass, status, "Warning")
    await set_state(hass, problem, "on")

    assert notified[0].data["title"] == "Veeam ONE: Veeam ONE nightly reports Warning"


async def test_collection_problem_on_the_server_device(hass, entry, notified):
    problem = add_entity(
        hass,
        entry,
        "binary_sensor.veeam_one_vbr_backup_jobs_problem",
        "off",
        {"device_class": "problem", "friendly_name": "Veeam ONE VBR Backup Jobs problem"},
    )
    add_entity(hass, entry, "sensor.veeam_one_version", "13.0.1.1071")
    await use_blueprint(
        hass,
        "resource_problem.yaml",
        {"problem_sensors": [problem], "notification_action": NOTIFY},
    )

    await set_state(
        hass,
        problem,
        "on",
        {"device_class": "problem", "friendly_name": "Veeam ONE VBR Backup Jobs problem"},
    )

    assert notified[0].data == {
        "title": "Veeam ONE: problem with VBR Backup Jobs",
        "message": "VBR Backup Jobs reports a problem in Veeam ONE.",
    }


# ---------------------------------------------------------------------------
# Repository running out of space, and its forecast
# ---------------------------------------------------------------------------


@pytest.fixture
def repository(hass, entry) -> tuple[str, str, str]:
    kwargs = {"device": "Default Backup Repository", "model": "VBR Repository"}
    percent = add_entity(
        hass,
        entry,
        "sensor.veeam_one_default_backup_repository_free_space_percentage",
        "30",
        {"unit_of_measurement": "%"},
        **kwargs,
    )
    free = add_entity(
        hass,
        entry,
        "sensor.veeam_one_default_backup_repository_free_space",
        "301.27",
        {"unit_of_measurement": "GiB"},
        **kwargs,
    )
    days = add_entity(
        hass,
        entry,
        "sensor.veeam_one_default_backup_repository_days_until_out_of_space",
        "40",
        {"unit_of_measurement": "d", "device_class": "duration"},
        **kwargs,
    )
    return percent, free, days


async def test_repository_space_low_and_back(hass, freezer, repository, notified, recovered):
    percent, free, _ = repository
    await use_blueprint(
        hass,
        "repository_space_low.yaml",
        {
            "free_space_sensors": [percent],
            "notification_action": NOTIFY,
            "recovery_action": RECOVER,
        },
    )

    await set_state(hass, free, "98.34", {"unit_of_measurement": "GiB"})
    await set_state(hass, percent, "9.8", {"unit_of_measurement": "%"})
    await advance(hass, freezer, timedelta(minutes=16))

    assert len(notified) == 1
    assert notified[0].data == {
        "title": "Veeam ONE: Default Backup Repository is low on space",
        "message": ("Default Backup Repository has 9.8% free (98.3 GiB), under the 15% threshold."),
    }

    await set_state(hass, percent, "40", {"unit_of_measurement": "%"})
    assert len(recovered) == 1
    assert recovered[0].data["title"] == "Veeam ONE: Default Backup Repository has space again"
    assert recovered[0].data["message"].endswith("— back over 15%.")


async def test_repository_space_low_ignores_a_reload(hass, freezer, repository, notified):
    percent, _, _ = repository
    await set_state(hass, percent, "9", {"unit_of_measurement": "%"})
    await use_blueprint(
        hass,
        "repository_space_low.yaml",
        {
            "free_space_sensors": [percent],
            "notification_action": NOTIFY,
            "sustained_for": {"seconds": 0},
        },
    )

    await set_state(hass, percent, "unavailable")
    await set_state(hass, percent, "9", {"unit_of_measurement": "%"})
    await advance(hass, freezer, timedelta(minutes=1))

    assert notified == []


async def test_repository_forecast(hass, repository, notified, recovered):
    _, _, days = repository
    await use_blueprint(
        hass,
        "repository_out_of_space_forecast.yaml",
        {
            "forecast_sensors": [days],
            "notification_action": NOTIFY,
            "recovery_action": RECOVER,
        },
    )

    attributes = {"unit_of_measurement": "d", "device_class": "duration"}
    await set_state(hass, days, "14", attributes)
    assert notified == []
    await set_state(hass, days, "9", attributes)

    assert len(notified) == 1
    assert notified[0].data == {
        "title": "Veeam ONE: Default Backup Repository full in 9 days",
        "message": (
            "Veeam ONE forecasts Default Backup Repository will run out of space in 9 days. "
            "Add capacity or shorten retention before then."
        ),
    }

    await set_state(hass, days, "1", attributes)
    assert len(notified) == 1

    await set_state(hass, days, "60", attributes)
    assert len(recovered) == 1
    assert recovered[0].data["message"] == (
        "Veeam ONE now forecasts 60 days before Default Backup Repository is full, over the "
        "14-day warning."
    )


async def test_repository_forecast_ignores_unknown(hass, repository, notified):
    """No forecast yet, or a reload, is not a forecast dropping."""
    _, _, days = repository
    await use_blueprint(
        hass,
        "repository_out_of_space_forecast.yaml",
        {"forecast_sensors": [days], "notification_action": NOTIFY},
    )

    await set_state(hass, days, "unknown")
    await set_state(hass, days, "3")
    await set_state(hass, days, "unavailable")
    await set_state(hass, days, "2")

    assert notified == []


# ---------------------------------------------------------------------------
# License expiring and license usage
# ---------------------------------------------------------------------------


async def fire_check(hass, freezer, when: str) -> None:
    freezer.move_to(when)
    async_fire_time_changed(hass, dt_util.utcnow())
    await hass.async_block_till_done()


@pytest.fixture
def license_days(hass, entry) -> tuple[str, str]:
    license_ = add_entity(
        hass,
        entry,
        "sensor.veeam_one_license_days_remaining",
        "120",
        {"friendly_name": "Veeam ONE License days remaining", "device_class": "duration"},
    )
    support = add_entity(
        hass,
        entry,
        "sensor.veeam_one_license_support_days_remaining",
        "unknown",
        {"friendly_name": "Veeam ONE License support days remaining", "device_class": "duration"},
    )
    return license_, support


async def test_license_expiring(hass, freezer, license_days, notified):
    license_, support = license_days
    freezer.move_to("2026-09-28 08:00:00+00:00")
    await use_blueprint(
        hass,
        "license_expiring.yaml",
        {"expiry_sensors": [license_, support], "notification_action": NOTIFY},
    )

    # Nothing within 30 days; the support sensor has no date
    await fire_check(hass, freezer, "2026-09-28 09:00:01+00:00")
    assert notified == []

    hass.states.async_set(license_, "12", {"friendly_name": "Veeam ONE License days remaining"})
    hass.states.async_set(
        support, "-3", {"friendly_name": "Veeam ONE License support days remaining"}
    )
    await fire_check(hass, freezer, "2026-09-29 09:00:01+00:00")

    assert len(notified) == 1
    assert notified[0].data["title"] == "Veeam ONE license has expired"
    assert notified[0].data["message"] == (
        "License: 12 day(s) left\nLicense support: expired 3 day(s) ago"
    )

    # It keeps reminding
    await fire_check(hass, freezer, "2026-09-30 09:00:01+00:00")
    assert len(notified) == 2


async def test_license_expiring_title_counts_down(hass, freezer, license_days, notified):
    license_, _ = license_days
    hass.states.async_set(license_, "1", {"friendly_name": "Veeam ONE License days remaining"})
    freezer.move_to("2026-09-28 08:00:00+00:00")
    await use_blueprint(
        hass,
        "license_expiring.yaml",
        {"expiry_sensors": [license_], "notification_action": NOTIFY},
    )

    await fire_check(hass, freezer, "2026-09-28 09:00:01+00:00")
    hass.states.async_set(license_, "0", {"friendly_name": "Veeam ONE License days remaining"})
    await fire_check(hass, freezer, "2026-09-29 09:00:01+00:00")

    assert [call.data["title"] for call in notified] == [
        "Veeam ONE license expires in 1 day",
        "Veeam ONE license expires today",
    ]
    assert notified[1].data["message"] == "License: expires today"


@pytest.fixture
def license_usage(hass, entry) -> tuple[str, str, str]:
    name = "Veeam ONE License Instances used percentage"
    percent = add_entity(
        hass,
        entry,
        "sensor.veeam_one_license_instances_used_percentage",
        "80",
        {"friendly_name": name, "unit_of_measurement": "%"},
    )
    used = add_entity(hass, entry, "sensor.veeam_one_license_instances_used", "80")
    licensed = add_entity(hass, entry, "sensor.veeam_one_license_instances_licensed", "100")
    return percent, used, licensed


async def test_license_usage_high_and_back(hass, license_usage, notified, recovered):
    percent, used, _ = license_usage
    await use_blueprint(
        hass,
        "license_usage_high.yaml",
        {
            "usage_sensors": [percent],
            "notification_action": NOTIFY,
            "recovery_action": RECOVER,
        },
    )
    attributes = {"friendly_name": "Veeam ONE License Instances used percentage"}

    await set_state(hass, used, "95")
    await set_state(hass, percent, "95.0", attributes)

    assert len(notified) == 1
    assert notified[0].data == {
        "title": "Veeam ONE licenses nearly used up: Instances",
        "message": "Instances: 95.0% in use (95 of 100), over the 90% threshold.",
    }

    await set_state(hass, used, "70")
    await set_state(hass, percent, "70.0", attributes)
    assert len(recovered) == 1
    assert recovered[0].data["message"] == ("Instances: 70.0% in use (70 of 100), back under 90%.")


async def test_license_usage_ignores_a_reload(hass, license_usage, notified):
    percent, _, _ = license_usage
    await set_state(hass, percent, "95")
    await use_blueprint(
        hass, "license_usage_high.yaml", {"usage_sensors": [percent], "notification_action": NOTIFY}
    )

    await set_state(hass, percent, "unavailable")
    await set_state(hass, percent, "95")

    assert notified == []
