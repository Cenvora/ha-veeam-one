# Veeam ONE for Home Assistant

Home Assistant integration for Veeam ONE using the Cenvora `veeam-one` Python client and Veeam ONE REST API 2.3.

## Features

- Veeam ONE connectivity and health
- Triggered alarm count and per-alarm details
- Resolve triggered alarms from Home Assistant
- Veeam Backup & Replication VM backup, replication and backup copy jobs
- Backup repository capacity, free space, task count and state
- Monitored Veeam Backup & Replication server connection state and version
- Veeam ONE license information

## Installation

Install through HACS as a custom repository, or copy `custom_components/veeam_one` into Home Assistant.

The integration installs `veeam-one>=0.1.0,<1.0.0` automatically.

## Configuration

Add **Veeam ONE** from Settings → Devices & services.

The Veeam ONE REST API defaults to HTTPS port **1239**. Use the port configured for Veeam ONE Web Services if it has been changed.

## License

MIT
