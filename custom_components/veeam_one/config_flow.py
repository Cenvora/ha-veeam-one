"""Config flow for Veeam ONE."""

from __future__ import annotations

import asyncio
from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.config_entries import ConfigFlowResult
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_PORT, CONF_USERNAME
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import config_validation as cv

from veeam_one import VeeamAuthenticationError

from .const import CONF_VERIFY_SSL, DEFAULT_PORT, DEFAULT_VERIFY_SSL, DOMAIN
from .sdk import create_client


class CannotConnect(HomeAssistantError):
    """Unable to connect."""


class InvalidAuth(HomeAssistantError):
    """Invalid credentials."""


async def validate_input(data: dict[str, Any]) -> dict[str, str]:
    """Validate connection details."""
    client = create_client(data)
    try:
        await asyncio.wait_for(client.connect(), timeout=60)
    except VeeamAuthenticationError as err:
        raise InvalidAuth from err
    except Exception as err:
        raise CannotConnect from err
    finally:
        await client.close()
    return {"title": f"Veeam ONE ({data[CONF_HOST]})"}


class VeeamOneConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle Veeam ONE config flow."""

    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors = {}
        if user_input is not None:
            await self.async_set_unique_id(f"{user_input[CONF_HOST]}:{user_input[CONF_PORT]}")
            self._abort_if_unique_id_configured()
            try:
                info = await validate_input(user_input)
            except InvalidAuth:
                errors["base"] = "invalid_auth"
            except CannotConnect:
                errors["base"] = "cannot_connect"
            else:
                return self.async_create_entry(title=info["title"], data=user_input)
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_HOST): cv.string,
                    vol.Required(CONF_PORT, default=DEFAULT_PORT): cv.port,
                    vol.Required(CONF_USERNAME): cv.string,
                    vol.Required(CONF_PASSWORD): cv.string,
                    vol.Optional(CONF_VERIFY_SSL, default=DEFAULT_VERIFY_SSL): cv.boolean,
                }
            ),
            errors=errors,
        )
