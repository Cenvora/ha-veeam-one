"""The Veeam ONE integration."""
from __future__ import annotations
import asyncio
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
from veeam_one import VeeamAuthenticationError
from .const import DOMAIN, UPDATE_TIMEOUT
from .coordinator import VeeamOneCoordinator
from .sdk import create_client

PLATFORMS=[Platform.SENSOR,Platform.BINARY_SENSOR,Platform.BUTTON]

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Veeam ONE."""
    client=create_client(entry.data)
    try:
        await asyncio.wait_for(client.connect(),timeout=UPDATE_TIMEOUT)
    except VeeamAuthenticationError as err:
        await client.close()
        raise ConfigEntryAuthFailed("Invalid Veeam ONE credentials") from err
    except Exception as err:
        await client.close()
        raise ConfigEntryNotReady(f"Unable to connect to Veeam ONE: {err}") from err
    coordinator=VeeamOneCoordinator(hass,entry,client)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data=coordinator
    await hass.config_entries.async_forward_entry_setups(entry,PLATFORMS)
    return True

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload Veeam ONE."""
    unloaded=await hass.config_entries.async_unload_platforms(entry,PLATFORMS)
    await entry.runtime_data.client.close()
    return unloaded
