"""Config flow for Kokozi."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
    OptionsFlowWithReload,
)
from homeassistant.const import UnitOfTime
from homeassistant.core import callback
from homeassistant.helpers import selector
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import KokoziApiClient, KokoziAuthError, KokoziCannotConnect, get_jwt_subject
from .const import (
    CONF_ACCESS_TOKEN,
    CONF_EXPIRES_AT,
    CONF_EXPIRES_IN,
    CONF_ISSUES_AT,
    CONF_LOGIN_PROVIDER,
    CONF_LOGIN_URL,
    CONF_OWNER_ID,
    CONF_POLLING_INTERVAL,
    CONF_REFRESH_EXPIRES_AT,
    CONF_REFRESH_TOKEN,
    CONF_TOKEN_TYPE,
    DEFAULT_POLLING_INTERVAL,
    DOMAIN,
    LOGGER,
    MAX_POLLING_INTERVAL,
    MIN_POLLING_INTERVAL,
    LOGIN_PROVIDER_EMAIL,
    LOGIN_PROVIDER_GOOGLE,
)

CONF_CALLBACK_URL = "callback_url"

CALLBACK_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_CALLBACK_URL): selector.TextSelector(
            selector.TextSelectorConfig(type=selector.TextSelectorType.TEXT)
        ),
    }
)


class KokoziConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Kokozi."""

    VERSION = 1

    _login_provider: str = ""
    _login_url: str = ""

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        """Create the options flow."""
        return KokoziOptionsFlow()

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial step."""
        LOGGER.debug("Showing Kokozi login provider menu")
        return self.async_show_menu(
            step_id="user",
            menu_options=[LOGIN_PROVIDER_EMAIL, LOGIN_PROVIDER_GOOGLE],
        )

    async def async_step_email(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Start email login."""
        return await self._async_start_login(LOGIN_PROVIDER_EMAIL)

    async def async_step_google(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Start Google login."""
        return await self._async_start_login(LOGIN_PROVIDER_GOOGLE)

    async def async_step_callback(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the Kokozi deep link callback URL."""
        errors: dict[str, str] = {}

        if user_input is not None:
            LOGGER.debug(
                "Received Kokozi callback URL input: length=%s",
                len(user_input[CONF_CALLBACK_URL]),
            )
            client = KokoziApiClient(async_get_clientsession(self.hass))
            try:
                token = await client.async_exchange_deep_link(
                    user_input[CONF_CALLBACK_URL]
                )
            except KokoziCannotConnect:
                LOGGER.warning("Kokozi login failed: cannot connect")
                errors["base"] = "cannot_connect"
            except KokoziAuthError as err:
                LOGGER.warning("Kokozi authentication failed: %s", err)
                errors["base"] = "invalid_auth"
            except Exception:
                LOGGER.exception("Unexpected exception during Kokozi login")
                errors["base"] = "unknown"
            else:
                await self.async_set_unique_id("kokozi")
                self._abort_if_unique_id_configured()
                LOGGER.info(
                    "Kokozi login succeeded: provider=%s token_type=%s expires_in=%s expires_at=%s refresh_expires_at=%s has_refresh_token=%s",
                    self._login_provider,
                    token.token_type,
                    token.expires_in,
                    token.expires_at,
                    token.refresh_expires_at,
                    token.refresh_token is not None,
                )
                return self.async_create_entry(
                    title="Kokozi",
                    data={
                        CONF_ACCESS_TOKEN: token.access_token,
                        CONF_REFRESH_TOKEN: token.refresh_token,
                        CONF_TOKEN_TYPE: token.token_type,
                        CONF_EXPIRES_IN: token.expires_in,
                        CONF_ISSUES_AT: token.issues_at,
                        CONF_EXPIRES_AT: token.expires_at,
                        CONF_REFRESH_EXPIRES_AT: token.refresh_expires_at,
                        CONF_OWNER_ID: get_jwt_subject(token.access_token),
                        CONF_LOGIN_PROVIDER: self._login_provider,
                        CONF_LOGIN_URL: self._login_url,
                    },
                )

        return self.async_show_form(
            step_id="callback",
            data_schema=CALLBACK_SCHEMA,
            errors=errors,
            description_placeholders={"login_url": self._login_url},
        )

    async def _async_start_login(self, provider: str) -> ConfigFlowResult:
        """Start provider login and ask the user for the callback URL."""
        errors: dict[str, str] = {}
        client = KokoziApiClient(async_get_clientsession(self.hass))

        try:
            LOGGER.debug("Starting Kokozi config flow login: provider=%s", provider)
            self._login_url = await client.async_get_login_url(provider)
        except KokoziCannotConnect:
            LOGGER.warning("Unable to start Kokozi login: cannot connect")
            errors["base"] = "cannot_connect"
        except KokoziAuthError as err:
            LOGGER.warning("Unable to start Kokozi login: %s", err)
            errors["base"] = "invalid_auth"
        except Exception:
            LOGGER.exception("Unexpected exception while starting Kokozi login")
            errors["base"] = "unknown"
        else:
            self._login_provider = provider
            LOGGER.debug(
                "Kokozi login URL ready: provider=%s url=%s",
                provider,
                self._login_url,
            )
            return await self.async_step_callback()

        return self.async_show_form(step_id=provider, errors=errors)


class KokoziOptionsFlow(OptionsFlowWithReload):
    """Handle Kokozi options."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Manage Kokozi options."""
        if user_input is not None:
            return self.async_create_entry(data=user_input)

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_POLLING_INTERVAL,
                        default=self.config_entry.options.get(
                            CONF_POLLING_INTERVAL, DEFAULT_POLLING_INTERVAL
                        ),
                    ): vol.All(
                        selector.NumberSelector(
                            selector.NumberSelectorConfig(
                                min=MIN_POLLING_INTERVAL,
                                max=MAX_POLLING_INTERVAL,
                                step=1,
                                mode=selector.NumberSelectorMode.BOX,
                                unit_of_measurement=UnitOfTime.SECONDS,
                            )
                        ),
                        vol.Coerce(int),
                    )
                }
            ),
        )
