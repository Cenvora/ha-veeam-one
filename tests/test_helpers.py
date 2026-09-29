from custom_components.veeam_one.coordinator import COLLECTIONS, as_dict, items


class Model:
    def to_dict(self):
        return {"items": [{"name": "Job"}], "totalCount": 1}


def test_as_dict():
    assert as_dict(Model())["totalCount"] == 1


def test_items():
    assert items(Model()) == [{"name": "Job"}]


def test_major_monitoring_domains_are_configured():
    keys = set(COLLECTIONS)
    assert {"cloud_connect_tenants", "m365_backup_jobs", "vsphere_vms", "vcd_organizations", "hyperv_vms", "public_cloud_vms"} <= keys
