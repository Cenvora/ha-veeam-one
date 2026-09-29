from custom_components.veeam_one.coordinator import COLLECTIONS, as_dict, items
from custom_components.veeam_one.entity import resource_id, resource_name


class Model:
    def to_dict(self):
        return {"items": [{"name": "Job"}], "totalCount": 1}


def test_as_dict():
    assert as_dict(Model())["totalCount"] == 1


def test_items():
    assert items(Model()) == [{"name": "Job"}]


def test_major_monitoring_domains_are_configured():
    keys = set(COLLECTIONS)
    assert {
        "cloud_connect_tenants",
        "m365_backup_jobs",
        "vsphere_vms",
        "vcd_organizations",
        "hyperv_vms",
        "public_cloud_vms",
    } <= keys


def test_resource_id_supports_generated_sdk_identifiers():
    assert resource_id({"vmBackupJobUid": "abc"}) == "abc"
    assert resource_id({"repositoryId": 42}) == "42"
    assert resource_id({"datastoreId": 7}) == "7"


def test_resource_name_falls_back_cleanly():
    assert resource_name({"name": "Nightly"}, "fallback") == "Nightly"
    assert resource_name({}, "fallback") == "fallback"


from custom_components.veeam_one.monitoring import _healthy, _severity


def test_monitoring_health_requires_known_healthy_status():
    assert _healthy("Success")
    assert _healthy("running")
    assert not _healthy("Warning")
    assert not _healthy("Unknown")


def test_alarm_severity_supports_common_fields():
    assert _severity({"severity": "Critical"}) == "critical"
    assert _severity({"alarmSeverity": "Warning"}) == "warning"
    assert _severity({"level": "Info"}) == "info"
    assert _severity({}) is None
