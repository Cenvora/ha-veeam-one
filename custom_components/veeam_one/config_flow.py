"""Config flow for Veeam ONE."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Mapping
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlowWithReload,
)
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_PORT, CONF_USERNAME
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import selector

from veeam_one import VeeamAuthenticationError

from .api_version import async_find_other_port, async_resolve_api_version, configured_api_version
from .const import (
    AUTO_API_VERSION,
    CONF_API_VERSION,
    CONF_VERIFY_SSL,
    CONNECT_TIMEOUT,
    DEFAULT_PORT,
    DEFAULT_VERIFY_SSL,
    DOMAIN,
)
from .sdk import API_VERSIONS, create_client, prepare_sdk, revoke

_LOGGER = logging.getLogger(__name__)


class CannotConnect(HomeAssistantError):
    """The server could not be reached, or did not answer usefully."""


class InvalidAuth(HomeAssistantError):
    """The server refused the credentials."""


class WrongPort(CannotConnect):
    """The configured port did not answer, but another Veeam ONE API port did."""

    def __init__(self, port: int) -> None:
        super().__init__(f"The Veeam ONE API answered on port {port}")
        self.port = port


async def validate_input(hass: HomeAssistant, data: Mapping[str, Any]) -> None:
    """Log in with the given details, raising InvalidAuth, WrongPort or CannotConnect.

    A stored "auto" is resolved here only to test the connection and is not written back,
    so every setup re-resolves it.
    """
    api_version = await async_resolve_api_version(hass, data)
    await hass.async_add_executor_job(prepare_sdk, api_version)
    client = create_client(data, api_version)
    try:
        async with asyncio.timeout(CONNECT_TIMEOUT):
            await client.connect()
        await revoke(client)
    except VeeamAuthenticationError as err:
        # Refused credentials prove the port is right, so there is nothing to probe
        raise InvalidAuth from err
    except Exception as err:
        _LOGGER.debug("Could not connect to %s:%s: %r", data[CONF_HOST], data[CONF_PORT], err)
        if (port := await async_find_other_port(hass, data)) is not None:
            raise WrongPort(port) from err
        raise CannotConnect(str(err)) from err
    finally:
        await client.close()


async def _validate(
    hass: HomeAssistant, data: Mapping[str, Any], errors: dict[str, str]
) -> dict[str, str]:
    """Run validate_input, recording any form error. Returns description placeholders."""
    try:
        await validate_input(hass, data)
    except InvalidAuth:
        errors["base"] = "invalid_auth"
    except WrongPort as err:
        errors["base"] = "wrong_port"
        return {"wrong_port": str(err.port)}
    except CannotConnect:
        errors["base"] = "cannot_connect"
    except Exception:
        _LOGGER.exception("Unexpected error validating the Veeam ONE connection")
        errors["base"] = "unknown"
    return {"wrong_port": ""}


def _api_version_selector() -> selector.SelectSelector:
    return selector.SelectSelector(
        selector.SelectSelectorConfig(
            options=[AUTO_API_VERSION, *API_VERSIONS],
            mode=selector.SelectSelectorMode.DROPDOWN,
            translation_key=CONF_API_VERSION,
        )
    )


def _connection_schema(defaults: Mapping[str, Any]) -> dict[vol.Marker, Any]:
    return {
        vol.Required(CONF_HOST, default=defaults.get(CONF_HOST, vol.UNDEFINED)): cv.string,
        vol.Required(CONF_PORT, default=defaults.get(CONF_PORT, DEFAULT_PORT)): cv.port,
        vol.Required(CONF_USERNAME, default=defaults.get(CONF_USERNAME, vol.UNDEFINED)): cv.string,
        vol.Required(CONF_PASSWORD): cv.string,
        vol.Optional(
            CONF_VERIFY_SSL, default=defaults.get(CONF_VERIFY_SSL, DEFAULT_VERIFY_SSL)
        ): cv.boolean,
    }


class VeeamOneConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle Veeam ONE config flow."""

    VERSION = 1
    MINOR_VERSION = 2

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> VeeamOneOptionsFlow:
        return VeeamOneOptionsFlow()

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        placeholders = {"wrong_port": ""}
        if user_input is not None:
            await self.async_set_unique_id(f"{user_input[CONF_HOST]}:{user_input[CONF_PORT]}")
            self._abort_if_unique_id_configured()
            placeholders = await _validate(self.hass, user_input, errors)
            if not errors:
                return self.async_create_entry(
                    title=f"Veeam ONE ({user_input[CONF_HOST]})", data=user_input
                )
        defaults = user_input or {}
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    **_connection_schema(defaults),
                    vol.Optional(
                        CONF_API_VERSION,
                        default=defaults.get(CONF_API_VERSION, AUTO_API_VERSION),
                    ): _api_version_selector(),
                }
            ),
            errors=errors,
            description_placeholders=placeholders,
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Change the server, port or credentials of an existing entry."""
        errors: dict[str, str] = {}
        placeholders = {"wrong_port": ""}
        entry = self._get_reconfigure_entry()
        if user_input is not None:
            data = {**entry.data, **user_input}
            unique_id = f"{data[CONF_HOST]}:{data[CONF_PORT]}"
            await self.async_set_unique_id(unique_id)
            # Moving to another server changes the unique ID, but never onto one that
            # another entry already covers
            if unique_id != entry.unique_id:
                self._abort_if_unique_id_configured()
            placeholders = await _validate(
                self.hass, {**data, CONF_API_VERSION: configured_api_version(entry)}, errors
            )
            if not errors:
                return self.async_update_reload_and_abort(
                    entry,
                    unique_id=unique_id,
                    title=f"Veeam ONE ({data[CONF_HOST]})",
                    data=data,
                )
        return self.async_show_form(
            step_id="reconfigure",
            data_schema=vol.Schema(_connection_schema(user_input or entry.data)),
            errors=errors,
            description_placeholders=placeholders,
        )

    async def async_step_reauth(self, entry_data: Mapping[str, Any]) -> ConfigFlowResult:
        """Start reauthentication after Veeam ONE rejected the stored credentials."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        placeholders = {"wrong_port": ""}
        entry = self._get_reauth_entry()
        if user_input is not None:
            placeholders = await _validate(
                self.hass,
                {**entry.data, **user_input, CONF_API_VERSION: configured_api_version(entry)},
                errors,
            )
            if not errors:
                return self.async_update_reload_and_abort(entry, data_updates=user_input)
        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_USERNAME, default=entry.data[CONF_USERNAME]): cv.string,
                    vol.Required(CONF_PASSWORD): cv.string,
                }
            ),
            errors=errors,
            description_placeholders={**placeholders, "host": entry.data[CONF_HOST]},
        )


class VeeamOneOptionsFlow(OptionsFlowWithReload):
    """Choose the API version. Reloads the entry when it changes."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        placeholders = {"wrong_port": ""}
        if user_input is not None:
            placeholders = await _validate(
                self.hass, {**self.config_entry.data, **user_input}, errors
            )
            if not errors:
                # Stored verbatim, including "auto", so it is re-resolved on every setup
                return self.async_create_entry(data=user_input)
        current = configured_api_version(self.config_entry)
        if current not in (AUTO_API_VERSION, *API_VERSIONS):
            current = AUTO_API_VERSION
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {vol.Required(CONF_API_VERSION, default=current): _api_version_selector()}
            ),
            errors=errors,
            description_placeholders=placeholders,
        )
