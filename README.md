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

A Home Assistant custom integration for monitoring Veeam ONE using the Cenvora `veeam-one` Python client and Veeam ONE REST API 2.3.

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

Each resource returned by the monitoring API is represented as a Home Assistant device. Resource entities are created dynamically as resources appear and include the fields that are available for that resource.

Common resource entities include:

- **Status** — Veeam ONE status, state, connection state or power state
- **Problem** — binary health indicator
- **Collection Health** — percentage of resources with a known healthy status
- **Collection Problem** — collection-level binary health indicator
- **Last Run** and **Last Run Duration** for workloads that report job sessions
- **Average Run Duration** and **Last Transferred Data** where available
- **Capacity**, **Free Space**, **Free Space Percentage**, **Running Tasks** and **Days Until Out of Space** for repositories/resources that expose those values
- **CPU, memory and host information** where reported
- **Configuration/diagnostic flags** such as immutable, ReFS, Cloud Connect and upgrade-required state
- The complete returned resource payload is also retained as attributes on the resource Status entity, so API fields not promoted to their own entity remain available

Aggregate diagnostic sensors are also provided for every monitored collection, including total and not-healthy counts.

### Licensing

The Veeam ONE device exposes:

- License type and package
- Licensed instances and sockets
- License company
- License expiration and support-expiration countdowns
- Current license-unit usage: used, available, licensed and utilization percentage
- License Expired and License Support Expired binary health indicators

### Veeam ONE service

The Veeam ONE device also exposes service/about information including service status, version and build when returned by the API.

### Alarms

Triggered alarms are exposed individually and receive a **Resolve** button. Aggregate critical, warning and informational alarm counts are also provided. Resolving an alarm uses the Veeam ONE REST API and refreshes the integration afterward.

## Actions

Veeam ONE 2.3 exposes alarm-resolution operations, so alarm resolve buttons are implemented.

The Veeam ONE 2.3 API does **not** expose the VBR job start/stop/retry/enable/disable or repository-rescan operations. Those actions therefore are not fabricated in this integration; use the Veeam Backup & Replication API/integration for operational VBR controls.

## Installation

Install through HACS as a custom repository, or copy `custom_components/veeam_one` into Home Assistant.

The integration installs `veeam-one>=0.1.0,<1.0.0` automatically.

## Configuration

Add **Veeam ONE** from Settings → Devices & services.

The Veeam ONE REST API defaults to HTTPS port **1239**. Use the port configured for Veeam ONE Web Services if it has been changed.

## License

MIT
