"""Actions: mark read, save a page, check off an episode, read a briefing."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import voluptuous as vol

from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant, ServiceCall, ServiceResponse, SupportsResponse
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import config_validation as cv

from .api import FeedrionError, FeedrionPremiumRequired
from .const import DOMAIN

if TYPE_CHECKING:
    from . import FeedrionConfigEntry

ATTR_ENTRY = "config_entry_id"

_ENTRY = vol.Optional(ATTR_ENTRY)

SCHEMAS = {
    "mark_read": vol.Schema({_ENTRY: cv.string, vol.Required("article_ids"): vol.All(
        cv.ensure_list, [vol.Coerce(int)], vol.Length(min=1, max=500))}),
    "mark_all_read": vol.Schema({_ENTRY: cv.string, vol.Optional("feed_id"): vol.Coerce(int),
                                 vol.Optional("folder_id"): vol.Coerce(int)}),
    "save_url": vol.Schema({_ENTRY: cv.string, vol.Required("url"): cv.url,
                            vol.Optional("title"): vol.All(cv.string, vol.Length(max=2000))}),
    "mark_episode_watched": vol.Schema({_ENTRY: cv.string, vol.Required("episode_id"): vol.Coerce(int)}),
    "briefing": vol.Schema({_ENTRY: cv.string,
                            vol.Optional("scope", default="all"): vol.Match(r"^(all|saved|starred|feed:\d+|folder:\d+)$"),
                            vol.Optional("limit", default=5): vol.All(vol.Coerce(int), vol.Range(min=1, max=20))}),
}


def _entry(hass: HomeAssistant, call: ServiceCall) -> FeedrionConfigEntry:
    wanted = call.data.get(ATTR_ENTRY)
    entries = [e for e in hass.config_entries.async_entries(DOMAIN) if e.state is ConfigEntryState.LOADED]
    if wanted:
        entries = [e for e in entries if e.entry_id == wanted]
    if not entries:
        raise ServiceValidationError(translation_domain=DOMAIN, translation_key="no_entry")
    if len(entries) > 1 and not wanted:
        raise ServiceValidationError(translation_domain=DOMAIN, translation_key="several_entries")
    return entries[0]


async def _run(hass: HomeAssistant, call: ServiceCall) -> ServiceResponse:
    entry = _entry(hass, call)
    client = entry.runtime_data.client
    data = call.data
    try:
        if call.service == "mark_read":
            await client.mark_read(data["article_ids"])
        elif call.service == "mark_all_read":
            await client.mark_all_read(data.get("feed_id"), data.get("folder_id"))
        elif call.service == "save_url":
            saved: dict[str, Any] = await client.save_url(data["url"], data.get("title"))
            await entry.runtime_data.coordinator.async_request_refresh()
            return {"article_id": saved.get("id"), "title": saved.get("title")} if call.return_response else None
        elif call.service == "mark_episode_watched":
            await client.episode_watched(data["episode_id"])
        elif call.service == "briefing":
            return await client.briefing(data["scope"], data["limit"])
    except FeedrionPremiumRequired as err:
        raise HomeAssistantError(translation_domain=DOMAIN, translation_key="premium_required") from err
    except FeedrionError as err:
        raise HomeAssistantError(str(err)) from err
    await entry.runtime_data.coordinator.async_request_refresh()
    return None


def async_setup_services(hass: HomeAssistant) -> None:
    async def handler(call: ServiceCall) -> ServiceResponse:
        return await _run(hass, call)

    for name, schema in SCHEMAS.items():
        supports = {
            "briefing": SupportsResponse.ONLY,
            "save_url": SupportsResponse.OPTIONAL,
        }.get(name, SupportsResponse.NONE)
        hass.services.async_register(DOMAIN, name, handler, schema=schema, supports_response=supports)
