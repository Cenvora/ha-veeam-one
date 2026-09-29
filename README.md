# Veeam ONE for Home Assistant

Home Assistant integration for Veeam ONE using the Cenvora `veeam-one` Python client and Veeam ONE REST API 2.3.

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

The integration exposes collection counts and "not healthy" counts as Home Assistant sensors, plus the overall Veeam ONE connectivity and triggered-alarm state.

## Installation

Install through HACS as a custom repository, or copy `custom_components/veeam_one` into Home Assistant.

The integration installs `veeam-one>=0.1.0,<1.0.0` automatically.

## Configuration

Add **Veeam ONE** from Settings → Devices & services.

The Veeam ONE REST API defaults to HTTPS port **1239**. Use the port configured for Veeam ONE Web Services if it has been changed.

## License

MIT
