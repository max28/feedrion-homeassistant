"""Pairing by code: no password ever reaches Home Assistant.

Home Assistant asks Feedrion for a code; the reader types it in the Feedrion
app (Settings ▸ Integrations ▸ Connected devices), which shows what is asking
before approving; the next poll receives a session of its own.

The code is shown on a FORM, not on a bare progress screen, while polling runs
in the background from the moment it is shown. A progress screen can only be
left by the frontend reacting to "done", and the reader typically leaves this
tab for the Feedrion app: a phone that put Home Assistant in the background
misses that event and the dialog then waits for ever, although the session
already arrived. A submit button survives that; submitting before approving
falls back to a progress screen, watched by a frontend that is in front.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Mapping
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry, ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.core import callback
from homeassistant.helpers import selector
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import FeedrionClient, FeedrionConnectionError, FeedrionError, normalize_api_url
from .const import (
    CONF_ACCESS_TOKEN,
    CONF_API_URL,
    CONF_ARTICLES,
    CONF_FAMILY_ID,
    CONF_FEEDS,
    CONF_REFRESH_TOKEN,
    CONF_STOCK_INTERVAL,
    CONF_STOCK_KEY,
    CONF_STOCK_PROVIDER,
    DEFAULT_API_URL,
    DEFAULT_ARTICLES,
    DOMAIN,
    MAX_ARTICLES,
    MAX_FEEDS,
    STOCK_PROVIDERS,
)

_LOGGER = logging.getLogger(__name__)

PAIR_TIMEOUT = 600


async def _pause(seconds: float) -> None:
    """Between two polls (a seam for the tests)."""
    await asyncio.sleep(seconds)


class FeedrionConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1

    def __init__(self) -> None:
        self._api_url = DEFAULT_API_URL
        self._start: dict[str, Any] | None = None
        self._session: dict[str, Any] | None = None
        self._task: asyncio.Task | None = None
        self._failure = "expired"

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return FeedrionOptionsFlow()

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                self._api_url = normalize_api_url(user_input.get(CONF_API_URL))
            except ValueError:
                errors[CONF_API_URL] = "https_required"
            else:
                return await self.async_step_pair()
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({vol.Optional(CONF_API_URL, default=DEFAULT_API_URL): str}),
            errors=errors,
        )

    async def async_step_reauth(self, entry_data: Mapping[str, Any]) -> ConfigFlowResult:
        self._api_url = entry_data.get(CONF_API_URL, DEFAULT_API_URL)
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is None:
            return self.async_show_form(step_id="reauth_confirm")
        return await self.async_step_pair()

    async def async_step_pair(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        client = FeedrionClient(async_get_clientsession(self.hass), self._api_url)
        if self._start is None:
            try:
                self._start = await client.start_pairing(self.hass.config.location_name or "Home Assistant")
            except FeedrionError as err:
                _LOGGER.warning("Feedrion pairing could not start: %s", err)
                return self.async_abort(reason="cannot_connect")
        if self._task is None:
            self._task = self.hass.async_create_task(self._wait(client))
        return await self.async_step_code()

    async def async_step_code(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """The code, and a button the reader presses once they approved it."""
        assert self._start is not None and self._task is not None
        if user_input is None:
            return self.async_show_form(
                step_id="code",
                description_placeholders={
                    "code": self._start["user_code"],
                    "url": self._start["verification_url"],
                },
            )
        if self._task.done():
            return await (self.async_step_finish() if self._session else self.async_step_failed())
        return await self.async_step_wait()

    async def async_step_wait(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Submitted before the app approved: wait here, in front of the reader."""
        assert self._start is not None and self._task is not None
        if not self._task.done():
            return self.async_show_progress(
                step_id="wait",
                progress_action="wait_for_code",
                description_placeholders={
                    "code": self._start["user_code"],
                    "url": self._start["verification_url"],
                },
                progress_task=self._task,
            )
        return self.async_show_progress_done(next_step_id="finish" if self._session else "failed")

    async def _wait(self, client: FeedrionClient) -> None:
        try:
            await self._poll_until_answered(client)
        except Exception:  # a dying task would leave the reader waiting with no word
            _LOGGER.exception("Feedrion pairing failed")
            self._failure = "pairing_failed"

    async def _poll_until_answered(self, client: FeedrionClient) -> None:
        assert self._start is not None
        interval = max(int(self._start.get("interval") or 3), 2)
        deadline = asyncio.get_running_loop().time() + min(int(self._start.get("expires_in") or PAIR_TIMEOUT), PAIR_TIMEOUT)
        while asyncio.get_running_loop().time() < deadline:
            await _pause(interval)
            try:
                answer = await client.poll_pairing(self._start["device_code"])
            except FeedrionConnectionError as err:
                # Unreachable, 429 or 5xx: the code is still valid, try again.
                _LOGGER.debug("Feedrion pairing poll failed, retrying: %s", err)
                continue
            except FeedrionError as err:
                # Any other refusal will be the same on the next poll: waiting
                # ten minutes in silence would only hide it.
                _LOGGER.warning("Feedrion refused the pairing poll: %s", err)
                self._failure = "pairing_failed"
                return
            status = answer.get("status") if isinstance(answer, dict) else None
            if status == "approved" and answer.get("refresh_token"):
                _LOGGER.debug("Feedrion pairing approved")
                self._session = answer
                return
            if status in ("expired", "denied"):
                self._failure = "expired"
                return
        _LOGGER.info("Feedrion pairing code expired before it was approved")
        self._failure = "expired"

    async def async_step_failed(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        return self.async_abort(reason=self._failure)

    async def async_step_finish(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        assert self._session is not None
        data = {
            CONF_API_URL: self._api_url,
            CONF_ACCESS_TOKEN: self._session["access_token"],
            CONF_REFRESH_TOKEN: self._session["refresh_token"],
            CONF_FAMILY_ID: self._session.get("family_id"),
        }
        client = FeedrionClient(async_get_clientsession(self.hass), self._api_url,
                                data[CONF_ACCESS_TOKEN], data[CONF_REFRESH_TOKEN])
        try:
            me = await client.me()
        except FeedrionError:
            me = {}
        data[CONF_ACCESS_TOKEN], data[CONF_REFRESH_TOKEN] = client.access_token, client.refresh_token
        if self.source == "reauth":
            return self.async_update_reload_and_abort(self._get_reauth_entry(), data=data)
        name = me.get("display_name") or "Feedrion"
        return self.async_create_entry(title=f"Feedrion ({name})" if me.get("display_name") else name, data=data)


class FeedrionOptionsFlow(OptionsFlow):
    """Which feeds become entities, how many articles, and My stocks."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        options = self.config_entry.options
        if user_input is not None:
            feeds = user_input.get(CONF_FEEDS) or []
            if len(feeds) > MAX_FEEDS:
                errors[CONF_FEEDS] = "too_many_feeds"
            elif user_input.get(CONF_STOCK_PROVIDER) and not user_input.get(CONF_STOCK_KEY):
                errors[CONF_STOCK_KEY] = "key_required"
            else:
                cleaned = {k: v for k, v in user_input.items() if v not in (None, "")}
                return self.async_create_entry(data=cleaned)

        feed_options: list[selector.SelectOptionDict] = []
        try:
            catalog = await self.config_entry.runtime_data.client.catalog()
            folders = {f["id"]: f["name"] for f in catalog.get("folders") or []}
            for feed in catalog.get("feeds") or []:
                folder = folders.get(feed.get("folder_id"))
                label = f"{folder} ▸ {feed['title']}" if folder else feed["title"]
                feed_options.append({"value": str(feed["id"]), "label": label})
        except (FeedrionError, AttributeError):
            errors["base"] = "cannot_connect"

        schema = vol.Schema({
            vol.Optional(CONF_FEEDS, default=list(options.get(CONF_FEEDS, []))): selector.SelectSelector(
                selector.SelectSelectorConfig(options=feed_options, multiple=True,
                                              mode=selector.SelectSelectorMode.DROPDOWN)),
            vol.Optional(CONF_ARTICLES, default=options.get(CONF_ARTICLES, DEFAULT_ARTICLES)):
                selector.NumberSelector(selector.NumberSelectorConfig(
                    min=0, max=MAX_ARTICLES, step=1, mode=selector.NumberSelectorMode.BOX)),
            vol.Optional(CONF_STOCK_PROVIDER, description={"suggested_value": options.get(CONF_STOCK_PROVIDER)}):
                selector.SelectSelector(selector.SelectSelectorConfig(
                    options=list(STOCK_PROVIDERS), translation_key="stock_provider")),
            vol.Optional(CONF_STOCK_KEY, description={"suggested_value": options.get(CONF_STOCK_KEY)}):
                selector.TextSelector(selector.TextSelectorConfig(type=selector.TextSelectorType.PASSWORD)),
            vol.Optional(CONF_STOCK_INTERVAL, description={"suggested_value": options.get(CONF_STOCK_INTERVAL)}):
                selector.NumberSelector(selector.NumberSelectorConfig(
                    min=1, max=1440, step=1, unit_of_measurement="min", mode=selector.NumberSelectorMode.BOX)),
        })
        return self.async_show_form(step_id="init", data_schema=schema, errors=errors)
