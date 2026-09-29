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

A Home Assistant custom integration that monitors Veeam ONE: triggered alarms, licensing, and
the health of the jobs, repositories and servers Veeam ONE watches.

This project is an independent, open source project. It is not affiliated with, endorsed by, or sponsored by Veeam Software.

## Features

- 🔧 **UI Configuration Flow**: Easy setup through Home Assistant's UI
- 🔎 **API Version Auto-Detection**: Finds the newest REST API version your server serves
- 🚨 **Alarm Monitoring**: Triggered alarms as sensors, with an action to resolve them
- 📊 **Job & Repository Health**: Status, problems, run times and free space for what Veeam ONE watches
- 🪪 **License Tracking**: Days remaining, usage per license unit, and a repair issue before it expires
- 🌐 **Broad Coverage**: Counts and health for every platform Veeam ONE monitors, from vSphere to Microsoft 365
- 🔄 **Automatic Updates**: Polls Veeam ONE every 60 seconds
- 🧹 **Device Cleanup**: Jobs and repositories Veeam ONE stops reporting are removed from Home Assistant

## Requirements

- Home Assistant 2026.8 or newer
- Veeam ONE with Veeam ONE Web Services (the REST API) installed
- A Veeam ONE account that can sign in to the Veeam ONE Web Client. A read-only role is enough
  for monitoring; resolving alarms needs a role that can resolve alarms in Veeam ONE

### Supported API Versions

The **API Version** option selects the REST API version used against your server. It defaults
to **Automatic**, which probes the server on every start and uses the newest version that both
the server and the installed [veeam-one](https://github.com/Cenvora/veeam-one) library support.
Pick a specific version to pin it instead.

| Veeam ONE Version | API Version | Notes |
| ----------------- | ----------- | ----- |
| 13.0.1            | `2.3`       | Default |

Servers that only serve API 2.1 or 2.2 aren't supported yet.

## Installation
### HACS (Recommended)

Have [HACS](https://hacs.xyz/) installed, this will allow you to update easily.

* Adding ha-veeam-one to HACS can be using this button:

[![image](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=Cenvora&repository=ha-veeam-one&category=integration)

> [!NOTE]
> If the button above doesn't work, add `https://github.com/Cenvora/ha-veeam-one` as a custom repository of type Integration in HACS.

* Click install on the `Veeam ONE` integration.
* Restart Home Assistant.

<details><summary>Manual Install</summary>

* Copy the `custom_components/veeam_one` folder from the [latest release](https://github.com/Cenvora/ha-veeam-one/releases/latest) to the [`custom_components` folder](https://developers.home-assistant.io/docs/creating_integration_file_structure/#where-home-assistant-looks-for-integrations) in your config directory.
* Restart Home Assistant.
</details>

The required `veeam-one` Python library is installed automatically by Home Assistant.

## Configuration

### Configuration Parameters

The integration supports the following configuration options:

#### Required Parameters
- **Host**: Hostname or IP address of the Veeam ONE Web Services server
- **Port**: REST API port (default: 1239). Veeam ONE Web Services uses 1239 unless it was
  changed at install time. If nothing answers on the port you enter but Veeam ONE does answer
  on 1239, the form says so
- **Username**: A Veeam ONE account, e.g. `DOMAIN\user`
- **Password**: Password for the specified account

#### Optional Parameters
- **Verify SSL**: Enable/disable SSL certificate verification (default: enabled)
  - Turn off only if the server uses a certificate Home Assistant doesn't trust, such as the
    self-signed one Veeam ONE installs
- **API Version**: REST API version to use. Defaults to *Automatic*, which detects the newest
  version the server serves (also changeable later via integration options)

### Via UI (Recommended)

1. Go to **Settings** → **Devices & Services**
2. Click **+ Add Integration**
3. Search for "Veeam ONE"
4. Enter your Veeam ONE server details:
   - **Host**: Your Veeam ONE Web Services hostname or IP address
   - **Port**: REST API port (default: 1239)
   - **Username**: Veeam ONE account, e.g. `DOMAIN\user`
   - **Password**: Password for the account
   - **Verify SSL**: Whether to verify SSL certificates (recommended: enabled)
   - **API Version**: Leave on *Automatic* unless you want to pin a version
5. Click **Submit**

### Options

**Configure** on the integration entry changes the API version (Automatic or a fixed version)
and reloads the integration.

### Reconfiguration

To update the connection settings:

1. Go to **Settings** → **Devices & Services**
2. Find the **Veeam ONE** integration
3. Click the three dots menu (⋮) and select **Reconfigure**
4. Update the host, port, credentials or SSL setting as needed
5. Click **Submit**

### Re-authentication

If credentials expire or change:

1. Home Assistant will automatically prompt for re-authentication
2. Enter the new **Username** and **Password**
3. Click **Submit**

The integration will reconnect without losing any device or entity configurations.

## Data Updates

The integration polls Veeam ONE every **60 seconds** to retrieve:
- Service information and version
- License details and usage
- Triggered alarms
- Every monitored collection (jobs, repositories, servers, VMs, hosts, …)

**Update Behavior:**
- **Load**: At most six requests run at a time, so a poll doesn't load the Veeam ONE database heavily
- **Collection delay**: Veeam ONE collects from the servers it monitors on its own schedule, so
  a change can take a few minutes to appear
- **Failed collections**: If one collection fails to load, for example because Veeam ONE
  doesn't monitor that platform, the rest still update and that collection keeps its last values
- **Failed connections**: If the whole API is unreachable, every entity becomes unavailable and
  **Connected** turns off
- **Connection recovery**: Entities automatically become available when the connection is restored

## Entities

The integration creates a device for the Veeam ONE server, plus a device for each job,
repository and backup server it reports.

### Veeam ONE Server Device

- **Connected**: whether the latest poll of the REST API succeeded
- **Version**: installed Veeam ONE version
- **Active alarms**: triggered alarms with status Error or Warning; the `alarms` attribute lists
  them (ID, name, status, time, object, description), newest first, up to 50
- **Error alarms** and **Warning alarms**: the same, split by status
- **License type**, **package**, **company**, **Licensed instances** and **Licensed sockets**
- **License days remaining** and **License support days remaining** (negative once expired),
  with **License expired** and **License support expired** problem sensors
- For each license unit (instances, sockets, points): **used**, **licensed** and **used percentage**
- For each monitored collection that has returned resources: a resource **count**. Collections
  that report health (jobs, repositories, servers, proxies) also get a **Health** percentage and
  a **Problem** sensor

Collections that are empty (platforms Veeam ONE doesn't monitor in your environment) create no
entities. They appear automatically if resources show up later.

### Resource Devices

Jobs, repositories, backup servers and Microsoft 365 servers and proxies each get their own
device, linked to the Veeam ONE device:

| Collection | Entities |
| --- | --- |
| VBR backup, replication and backup copy jobs | Status, Problem, Last run, Last run duration, Average run duration¹, Last transferred data |
| VBR repositories | Status, Problem, Capacity, Free space, Free space percentage, Running tasks¹, Days until out of space |
| VBR backup servers, Microsoft 365 servers and proxies | Status, Problem |
| Microsoft 365 backup and copy jobs | Status, Problem, Last run, Last run duration, Last transferred data, Processed items¹ |
| Microsoft 365 repositories and object storage | Capacity, Free space, Used space, Free space percentage |

¹ Disabled by default; enable it from the entity's settings. **Licensed sockets** is disabled by default too.

An entity is only created when Veeam ONE returns its field. The Status sensor carries the rest
of the resource's fields as attributes. **Problem** is on for Failed, Warning, Error,
Disconnected, Inaccessible, OutOfDate, NotResponding and Offline, and unknown when the status is
Unknown.

Users, groups, sites, teams, VMs, hosts, datastores, Cloud Director, Hyper-V, public cloud and
protected objects are counted but don't get devices, so a large tenant doesn't create thousands
of them.

When Veeam ONE stops returning a resource, its device is removed. A collection that fails to
load keeps its devices until it loads again.

## Alarms

### The `veeam_one.resolve_alarm` action

Resolves triggered alarms by ID. The IDs are in the `alarms` attribute of **Active alarms**.

```yaml
action: veeam_one.resolve_alarm
data:
  alarm_ids: [1234]
  comment: Fixed the proxy
```

`config_entry_id` is only needed when more than one Veeam ONE server is configured.

## Repairs

When the Veeam ONE license is within 30 days of expiring, or has expired, a repair issue
appears under **Settings → Repairs**. It clears on its own once Veeam ONE reports a renewed
license.

## Automation Blueprints

Ready-made automations for the entities this integration creates. Each one asks you to pick
the entities to watch and what to do about it — a notification, a script, anything Home
Assistant can run — so they work with whatever notifier you already use.

Click **Import blueprint**, then create automations from it under
**Settings → Automations & scenes → Blueprints**.

> [!NOTE]
> Blueprints are not installed by HACS — Home Assistant has no mechanism for an integration to
> ship them, and HACS has no blueprint category. The import links below fetch them from this
> repository directly.

### Alarm triggered

Fires when Veeam ONE raises a new alarm or one escalates from Warning to Error, and optionally when alarms are resolved. Watches the `alarms` attribute of **Active alarms**, so each alarm is reported once. Hands your action the `alarm_ids` and `entry_id` that [`veeam_one.resolve_alarm`](#the-veeam_oneresolve_alarm-action) needs.

[![Import blueprint](https://my.home-assistant.io/badges/blueprint_import.svg)](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fraw.githubusercontent.com%2FCenvora%2Fha-veeam-one%2Fmain%2Fblueprints%2Fautomation%2Fveeam_one%2Falarm_triggered.yaml)

<sub>Source: [`alarm_triggered.yaml`](blueprints/automation/veeam_one/alarm_triggered.yaml)</sub>

### Server unreachable

Fires when the **Connected** sensor stays off — Home Assistant can't reach the Veeam ONE REST API — and optionally when it answers again.

[![Import blueprint](https://my.home-assistant.io/badges/blueprint_import.svg)](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fraw.githubusercontent.com%2FCenvora%2Fha-veeam-one%2Fmain%2Fblueprints%2Fautomation%2Fveeam_one%2Fserver_unreachable.yaml)

<sub>Source: [`server_unreachable.yaml`](blueprints/automation/veeam_one/server_unreachable.yaml)</sub>

### Resource problem

Fires when a job, repository or server's **Problem** sensor turns on, saying which status Veeam ONE reported (Failed, Disconnected, ...), and optionally when it clears.

[![Import blueprint](https://my.home-assistant.io/badges/blueprint_import.svg)](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fraw.githubusercontent.com%2FCenvora%2Fha-veeam-one%2Fmain%2Fblueprints%2Fautomation%2Fveeam_one%2Fresource_problem.yaml)

<sub>Source: [`resource_problem.yaml`](blueprints/automation/veeam_one/resource_problem.yaml)</sub>

### Repository running out of space

Fires when a repository's **Free space percentage** stays below a threshold, with an optional recovery notification.

[![Import blueprint](https://my.home-assistant.io/badges/blueprint_import.svg)](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fraw.githubusercontent.com%2FCenvora%2Fha-veeam-one%2Fmain%2Fblueprints%2Fautomation%2Fveeam_one%2Frepository_space_low.yaml)

<sub>Source: [`repository_space_low.yaml`](blueprints/automation/veeam_one/repository_space_low.yaml)</sub>

### Repository out-of-space forecast

Fires when Veeam ONE's **Days until out of space** forecast for a repository drops below a number of days, so there is time to add capacity.

[![Import blueprint](https://my.home-assistant.io/badges/blueprint_import.svg)](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fraw.githubusercontent.com%2FCenvora%2Fha-veeam-one%2Fmain%2Fblueprints%2Fautomation%2Fveeam_one%2Frepository_out_of_space_forecast.yaml)

<sub>Source: [`repository_out_of_space_forecast.yaml`](blueprints/automation/veeam_one/repository_out_of_space_forecast.yaml)</sub>

### License expiring soon

Daily reminder once the license or its support contract is within N days of expiring, or has expired.

[![Import blueprint](https://my.home-assistant.io/badges/blueprint_import.svg)](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fraw.githubusercontent.com%2FCenvora%2Fha-veeam-one%2Fmain%2Fblueprints%2Fautomation%2Fveeam_one%2Flicense_expiring.yaml)

<sub>Source: [`license_expiring.yaml`](blueprints/automation/veeam_one/license_expiring.yaml)</sub>

### Running out of licenses

Fires when a license unit's **used percentage** crosses a threshold, and optionally when it drops back.

[![Import blueprint](https://my.home-assistant.io/badges/blueprint_import.svg)](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fraw.githubusercontent.com%2FCenvora%2Fha-veeam-one%2Fmain%2Fblueprints%2Fautomation%2Fveeam_one%2Flicense_usage_high.yaml)

<sub>Source: [`license_usage_high.yaml`](blueprints/automation/veeam_one/license_usage_high.yaml)</sub>

Veeam ONE fires no events of its own, so every blueprint reacts to entity states. Reloading
the integration or restarting Home Assistant takes the entities through unavailable; none of
the blueprints treat coming back from that as something new to report.

## Example Automations

### Notify on a Job Problem

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

### Resolve Every Active Alarm Each Morning

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

## Removal

To remove the integration from Home Assistant:

1. Go to **Settings** → **Devices & Services**
2. Find the **Veeam ONE** integration
3. Click the three dots menu (⋮) and select **Delete**
4. Confirm the deletion

All devices and entities associated with this integration will be removed. To remove the files
as well, remove the repository in HACS (or delete `custom_components/veeam_one`) and restart
Home Assistant.

## Troubleshooting

### Connection Issues

**Problem**: Integration fails to connect to Veeam ONE

**Solutions**:
- Check that Home Assistant can reach the Veeam ONE Web Services server on the configured port
  (1239 by default). Opening `https://<host>:1239/api/v2.3/about` from the same network should
  give a 401 response, which means the API is up
- If the form reports a wrong port, use the port the error message names
- Ensure firewall rules allow traffic on the REST API port
- Veeam ONE installs a self-signed certificate: turn off **Verify SSL**, or install a trusted
  certificate on the server

### Authentication Failures

**Problem**: Invalid credentials error during setup or re-authentication

**Solutions**:
- Confirm the account can sign in to the Veeam ONE Web Client
- Include the domain in the username, e.g. `DOMAIN\user`
- Check if the account is locked or its password has expired

### Missing Entities

**Problem**: Entities are missing for a platform

**Solutions**:
- The collection may be empty, or Veeam ONE refused it. **Download diagnostics** on the
  integration entry shows each collection's count and the error for any that failed
- Veeam ONE collects on its own schedule, so new resources can take a few minutes to appear
- Some entities are disabled by default; enable them from the entity's settings

### Debug Logs

Choose **Enable debug logging** on the integration entry, reproduce the problem, then disable
it to download the log.

## Known Limitations

- **No job control**: The Veeam ONE REST API can't start, stop, enable or disable jobs or rescan
  repositories. Use the [Veeam Backup & Replication](https://github.com/Cenvora/ha-veeam-br) or
  [Veeam Backup for Microsoft 365](https://github.com/Cenvora/ha-veeam-365) integrations for that
- **No discovery**: Veeam ONE doesn't announce itself on the network, so add it by hand
- **Counted, not devices**: VMs, hosts, datastores, Microsoft 365 users and protected objects are
  counted, not given their own devices
- **Alarm list**: The `alarms` attribute lists at most 50 alarms
- **Real-time Updates**: Changes are reflected every 60 seconds, after Veeam ONE has collected them

## Supported Devices & Functions

### Monitored Platforms

The integration reads Veeam ONE's monitoring API across:

- ✅ **Veeam Backup & Replication** - backup, replication and backup copy jobs; repositories; backup servers
- ✅ **Veeam Cloud Connect** - tenants, cloud gateways and gateway pools
- ✅ **Veeam Backup for Microsoft 365** - organizations, servers, proxies, repositories, object
  storage, backup/copy jobs and protected Microsoft 365 objects
- ✅ **VMware vSphere** - vCenters, hosts, clusters, datastores, datastore clusters, resource pools, VMs and vApps
- ✅ **VMware Cloud Director** - Cloud Director servers, organizations, organization/provider VDCs, datastores and vApps
- ✅ **Microsoft Hyper-V** - hosts, clusters, VMs, file servers/shares, physical disks and SCVMM servers
- ✅ **Public Cloud** - cloud VMs, databases, file shares and their protected/backup resources
- ✅ **Veeam ONE** - service/about information, licensing and triggered alarms

### Supported Entities

- **Sensors**: Status, alarm counts, run times, capacity, free space, license details and usage, collection counts and health
- **Binary Sensors**: Connected, problem, license expired
- **Actions**: Resolve alarms

### Unsupported (Future Enhancements)

- ⏳ Veeam ONE servers that only serve REST API 2.1 or 2.2

## Support

- **Issues**: [GitHub Issues](https://github.com/Cenvora/ha-veeam-one/issues)
- **Documentation**: This README and inline code documentation

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

### Development Setup

To set up the development environment:

```bash
# Install development and test dependencies
pip install ruff ty -r requirements_test.txt
```

### Code Quality

This project uses automated testing and formatting:

- **Ruff**: Code formatting and linting (line length: 100)
- **ty**: Type checking
- **pytest**: Tests, using `pytest-homeassistant-custom-component`
- **HACS Action**: HACS integration validation
- **Hassfest**: Home Assistant manifest validation

Run formatting and checks locally:

```bash
# Format code
ruff format custom_components/

# Run linting
ruff check custom_components/

# Type checking
ty check custom_components/

# Run tests
pytest

# Validate JSON
python -m json.tool custom_components/veeam_one/manifest.json
```

### CI/CD

All pull requests are automatically validated with:
- Python code formatting and linting (Ruff)
- Type checking (ty)
- Tests (pytest)
- HACS validation
- Home Assistant manifest validation (hassfest)
- JSON validation

### Release Process

The version in `manifest.json` is automatically updated when a new release tag is created:

1. Create and push a tag with the format `v*` (e.g., `v1.0.0`, `v0.3.1b3`)
   ```bash
   git tag v1.0.0
   git push origin v1.0.0
   ```

   **Note:** Tags should be created from the default branch to ensure consistency.

2. The GitHub Actions workflow automatically:
   - Extracts the version from the tag (removes the `v` prefix)
   - Updates the `version` field in `custom_components/veeam_one/manifest.json`
   - Commits and pushes the change to the default branch

3. The updated manifest.json is now ready for the release

## License

This project is licensed under the terms included in the LICENSE file.

## Credits

This integration uses the [veeam-one](https://github.com/Cenvora/veeam-one) Python library for communication with Veeam ONE servers. The library is automatically installed by Home Assistant when you add this integration - no manual installation required.
