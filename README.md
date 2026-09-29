<h1 align="center">
<br>
<img src="https://raw.githubusercontent.com/Cenvora/ha-veeam-one/main/custom_components/veeam_one/brand/logo.png"
     alt="Veeam Logo"
     height="100">
<br>
<br>
Veeam ONE Integration for Home Assistant
</h1>

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/hacs/integration)

A Home Assistant custom integration (Home Assistant 2026.8 or later) for monitoring Veeam ONE using the Cenvora `veeam-one` Python client and Veeam ONE REST API 2.3.

This project is an independent, open source project. It is not affiliated with, endorsed by, or sponsored by Veeam Software.

## Monitoring coverage

The integration uses Veeam ONE's v2.3 monitoring API across:

- **Veeam Backup & Replication** — backup, replication and backup copy jobs; repositories; backup servers
- **Veeam Cloud Connect** — tenants, cloud gateways and gateway pools
- **Veeam Backup for Microsoft 365** — organizations, servers, proxies, repositories, object storage, backup/copy jobs and protected Microsoft 365 objects
- **VMware vSphere** — vCenters, hosts, clusters, datastores, datastore clusters, resource pools, VMs and vApps
- **VMware Cloud Director** — Cloud Director servers, organizations, organization/provider VDCs, datastores and vApps
- **Microsoft Hyper-V** — hosts, clusters, VMs, file servers/shares, physical disks and SCVMM servers
- **Public Cloud** — cloud VMs, databases, file shares and their protected/backup resources
- **Veeam ONE** — service/about information, licensing and triggered alarms

## Entities

### Veeam ONE server device

- **Connected** — whether the latest poll of the REST API succeeded
- **Version** — installed Veeam ONE version
- **Active Alarms** — triggered alarms with status Error or Warning; the `alarms` attribute lists them (ID, name, status, time, object, description), newest first, up to 50
- **Error Alarms** and **Warning Alarms** — the same, split by status
- **License Type**, **Package**, **Company**, **Licensed Instances** and **Licensed Sockets**
- **License Days Remaining** and **License Support Days Remaining** (negative once expired), with **License Expired** and **License Support Expired** problem sensors
- For each license unit (instances, sockets, points): **Used**, **Licensed** and **Used Percentage**
- For each monitored collection that has returned resources: a resource **count**. Collections that report health (jobs, repositories, servers, proxies) also get a **Health** percentage and a **Problem** sensor.

Collections that are empty — platforms Veeam ONE doesn't monitor in your environment — create no entities. They appear automatically if resources show up later.

### Resource devices

Jobs, repositories, backup servers and Microsoft 365 servers and proxies each get their own device, linked to the Veeam ONE device:

| Collection | Entities |
| --- | --- |
| VBR backup, replication and backup copy jobs | Status, Problem, Last Run, Last Run Duration, Average Run Duration, Last Transferred Data |
| VBR repositories | Status, Problem, Capacity, Free Space, Free Space Percentage, Running Tasks, Days Until Out of Space |
| VBR backup servers, Microsoft 365 servers and proxies | Status, Problem |
| Microsoft 365 backup and copy jobs | Status, Problem, Last Run, Last Run Duration, Last Transferred Data, Processed Items |
| Microsoft 365 repositories and object storage | Capacity, Free Space, Used Space, Free Space Percentage |

An entity is only created when Veeam ONE returns its field. The Status sensor carries the rest of the resource's fields as attributes. **Problem** is on for Failed, Warning, Error, Disconnected, Inaccessible, OutOfDate, NotResponding and Offline, and unknown when the status is Unknown.

Users, groups, sites, teams, VMs, hosts, datastores, Cloud Director, Hyper-V, public cloud and protected objects are counted but don't get devices, so a large tenant doesn't create thousands of them.

When Veeam ONE stops returning a resource, its device is removed. A collection that fails to load keeps its devices until it loads again.

## Actions

### `veeam_one.resolve_alarm`

Resolves triggered alarms by ID. The IDs are in the `alarms` attribute of **Active Alarms**.

```yaml
action: veeam_one.resolve_alarm
data:
  alarm_ids: [1234]
  comment: Fixed the proxy
```

`config_entry_id` is only needed when more than one Veeam ONE server is configured.

The Veeam ONE 2.3 API does **not** expose the VBR job start/stop/retry/enable/disable or repository-rescan operations. Use the Veeam Backup & Replication integration for those.

## Upgrading from 0.1.0

0.1.0 built resource IDs from the wrong fields and made a device for every triggered alarm. The first start after upgrading removes all of this integration's old entities and devices and recreates them, so entity IDs may change. Update any dashboards or automations that used them. The alarm **Resolve** buttons are replaced by the `veeam_one.resolve_alarm` action.

## Installation

Install through HACS as a custom repository, or copy `custom_components/veeam_one` into Home Assistant.

The integration installs `veeam-one>=0.1.0,<1.0.0` automatically.

## Configuration

Add **Veeam ONE** from Settings → Devices & services.

The Veeam ONE REST API defaults to HTTPS port **1239**. Use the port configured for Veeam ONE Web Services if it has been changed.

## License

MIT
