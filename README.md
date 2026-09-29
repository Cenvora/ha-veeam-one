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

A Home Assistant custom integration for monitoring Veeam ONE: triggered alarms, licensing, and the health of the jobs, repositories and servers Veeam ONE watches. It uses the Cenvora `veeam-one` Python client and the Veeam ONE REST API.

This project is an independent, open source project. It is not affiliated with, endorsed by, or sponsored by Veeam Software.

## Monitoring coverage

The integration reads Veeam ONE's monitoring API across:

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
- **Active alarms** — triggered alarms with status Error or Warning; the `alarms` attribute lists them (ID, name, status, time, object, description), newest first, up to 50
- **Error alarms** and **Warning alarms** — the same, split by status
- **License type**, **package**, **company**, **Licensed instances** and **Licensed sockets**
- **License days remaining** and **License support days remaining** (negative once expired), with **License expired** and **License support expired** problem sensors
- For each license unit (instances, sockets, points): **used**, **licensed** and **used percentage**
- For each monitored collection that has returned resources: a resource **count**. Collections that report health (jobs, repositories, servers, proxies) also get a **Health** percentage and a **Problem** sensor.

Collections that are empty — platforms Veeam ONE doesn't monitor in your environment — create no entities. They appear automatically if resources show up later.

### Resource devices

Jobs, repositories, backup servers and Microsoft 365 servers and proxies each get their own device, linked to the Veeam ONE device:

| Collection | Entities |
| --- | --- |
| VBR backup, replication and backup copy jobs | Status, Problem, Last run, Last run duration, Average run duration¹, Last transferred data |
| VBR repositories | Status, Problem, Capacity, Free space, Free space percentage, Running tasks¹, Days until out of space |
| VBR backup servers, Microsoft 365 servers and proxies | Status, Problem |
| Microsoft 365 backup and copy jobs | Status, Problem, Last run, Last run duration, Last transferred data, Processed items¹ |
| Microsoft 365 repositories and object storage | Capacity, Free space, Used space, Free space percentage |

¹ Disabled by default; enable it from the entity's settings. **Licensed sockets** is disabled by default too.

An entity is only created when Veeam ONE returns its field. The Status sensor carries the rest of the resource's fields as attributes. **Problem** is on for Failed, Warning, Error, Disconnected, Inaccessible, OutOfDate, NotResponding and Offline, and unknown when the status is Unknown.

Users, groups, sites, teams, VMs, hosts, datastores, Cloud Director, Hyper-V, public cloud and protected objects are counted but don't get devices, so a large tenant doesn't create thousands of them.

When Veeam ONE stops returning a resource, its device is removed. A collection that fails to load keeps its devices until it loads again.

## Actions

### `veeam_one.resolve_alarm`

Resolves triggered alarms by ID. The IDs are in the `alarms` attribute of **Active alarms**.

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

## Supported versions

- Veeam ONE servers that serve REST API 2.3, which `veeam-one` 0.2 speaks. Tested against Veeam ONE 13.0.1. Older servers that only serve 2.1 or 2.2 aren't supported yet.
- Home Assistant 2026.8 or later.

## Installation

Install through HACS as a custom repository, or copy `custom_components/veeam_one` into Home Assistant, then restart. The integration installs `veeam-one>=0.2.0,<1.0.0` automatically.

Veeam ONE needs an account that can sign in to the Veeam ONE Web Client. A read-only role is enough for monitoring; resolving alarms needs a role that can resolve alarms in Veeam ONE.

## Configuration

Add **Veeam ONE** from **Settings → Devices & services → Add integration**.

| Field | Description |
| --- | --- |
| Host | Hostname or IP address of the Veeam ONE Web Services server |
| Port | REST API port. Veeam ONE Web Services uses **1239** unless it was changed at install time. If nothing answers on the port you enter but Veeam ONE does answer on 1239, the form says so. |
| Username / Password | A Veeam ONE account, e.g. `DOMAIN\user` |
| Verify SSL certificate | Turn off only if the server uses a certificate Home Assistant doesn't trust, such as the self-signed one Veeam ONE installs |
| API version | **Automatic** (the default) probes the server on every start and uses the newest REST API version that both the server and the installed `veeam-one` library support. Pick a version only to pin it. |

After setup:

- **Configure** changes the API version (Automatic or a fixed version) and reloads the integration.
- **Reconfigure** (the ⋮ menu on the integration entry) changes the host, port, credentials or SSL setting without removing the integration.
- If Veeam ONE rejects the stored credentials, Home Assistant shows a **Reauthenticate** prompt.

## Data updates

The integration polls Veeam ONE every 60 seconds: service information, licensing, triggered alarms and every monitored collection. At most six requests run at a time, so a poll doesn't load the Veeam ONE database heavily. Veeam ONE collects from the servers it monitors on its own schedule, so a change can take a few minutes to appear.

If one collection fails to load, for example because Veeam ONE doesn't monitor that platform, the rest still update and that collection keeps its last values. If the whole API is unreachable, every entity becomes unavailable and **Connected** turns off.

## Repairs

When the Veeam ONE license is within 30 days of expiring, or has expired, a repair issue appears under **Settings → Repairs**. It clears on its own once Veeam ONE reports a renewed license.

## Examples

Notify when a backup job reports a problem:

```yaml
triggers:
  - trigger: state
    entity_id: binary_sensor.veeam_one_main_org_backup_problem
    to: "on"
actions:
  - action: notify.mobile_app_phone
    data:
      message: "{{ trigger.to_state.name }} is on"
```

Resolve every active alarm each morning:

```yaml
triggers:
  - trigger: time
    at: "08:00:00"
conditions:
  - condition: numeric_state
    entity_id: sensor.veeam_one_active_alarms
    above: 0
actions:
  - action: veeam_one.resolve_alarm
    data:
      alarm_ids: "{{ state_attr('sensor.veeam_one_active_alarms', 'alarms') | map(attribute='id') | list }}"
      comment: Cleared by Home Assistant
```

Other uses: a dashboard of repository free space, a warning when **Days until out of space** drops below a week, or tracking license usage.

## Known limitations

- The Veeam ONE REST API can't start, stop, enable or disable jobs or rescan repositories. Use the Veeam Backup & Replication or Veeam Backup for Microsoft 365 integrations for that.
- Veeam ONE doesn't announce itself on the network, so it can't be discovered automatically; add it by hand.
- VMs, hosts, datastores, Microsoft 365 users and protected objects are counted, not given their own devices.
- The `alarms` attribute lists at most 50 alarms.

## Troubleshooting

- **Cannot connect**: check that Home Assistant can reach the Veeam ONE Web Services server on the configured port (1239 by default). Opening `https://<host>:1239/api/v2.3/about` from the same network should give a 401 response, which means the API is up.
- **Wrong port**: use the port the error message names.
- **Invalid authentication**: confirm the account can sign in to the Veeam ONE Web Client, and include the domain, e.g. `DOMAIN\user`.
- **SSL errors**: Veeam ONE installs a self-signed certificate. Turn off **Verify SSL certificate**, or install a trusted certificate on the server.
- **Entities missing for a platform**: the collection is empty, or Veeam ONE refused it. **Download diagnostics** on the integration entry shows each collection's count and the error for any that failed.
- **Debug logs**: choose **Enable debug logging** on the integration entry, reproduce the problem, then disable it to download the log.

## Removal

Go to **Settings → Devices & services → Veeam ONE**, open the ⋮ menu on the entry and choose **Delete**. To remove the files as well, remove the repository in HACS (or delete `custom_components/veeam_one`) and restart Home Assistant.

## License

MIT
