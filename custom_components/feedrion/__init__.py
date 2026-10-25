"""Feedrion for Home Assistant: feeds, TV shows, weather, currencies and stocks."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.helpers.typing import ConfigType

from .api import FeedrionClient
from .const import (
    CONF_ACCESS_TOKEN,
    CONF_API_URL,
    CONF_REFRESH_TOKEN,
    DEFAULT_API_URL,
    DOMAIN,
    EVENTS_INTERVAL,
)
from .coordinator import FeedrionCoordinator, FeedrionEvents, StocksCoordinator
from .services import async_setup_services

PLATFORMS: list[Platform] = [
    Platform.SENSOR,
    Platform.CALENDAR,
    Platform.TODO,
    Platform.WEATHER,
]

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)


@dataclass
class FeedrionRuntime:
    client: FeedrionClient
    coordinator: FeedrionCoordinator
    events: FeedrionEvents
    stocks: StocksCoordinator
    options: dict


type FeedrionConfigEntry = ConfigEntry[FeedrionRuntime]


CARDS_URL = "/feedrion_static/feedrion-cards.js"
CARDS_FILE = Path(__file__).parent / "frontend" / "feedrion-cards.js"


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    async_setup_services(hass)
    await _async_register_cards(hass)
    return True


async def _async_register_cards(hass: HomeAssistant) -> None:
    """Serve the dashboard cards and load them in every browser: nothing to
    add by hand in Settings ▸ Dashboards ▸ Resources."""
    if hass.http is None or "frontend" not in hass.config.components:
        return
    from homeassistant.components.frontend import add_extra_js_url  # noqa: PLC0415
    from homeassistant.components.http import StaticPathConfig  # noqa: PLC0415

    def _version() -> str:
        manifest = json.loads((Path(__file__).parent / "manifest.json").read_text(encoding="utf-8"))
        return str(manifest.get("version", "0"))

    version = await hass.async_add_executor_job(_version)
    # cache_headers=False: the ?v= query is what makes a release reach the
    # browser, and an update must not wait for a month-long cache to expire.
    await hass.http.async_register_static_paths([StaticPathConfig(CARDS_URL, str(CARDS_FILE), False)])
    add_extra_js_url(hass, f"{CARDS_URL}?v={version}")


async def async_setup_entry(hass: HomeAssistant, entry: FeedrionConfigEntry) -> bool:
    @callback
    def save_tokens(access: str, refresh: str) -> None:
        # Feedrion rotates the refresh token on every use: the new one MUST be
        # stored, or the next restart signs this Home Assistant out.
        hass.config_entries.async_update_entry(
            entry, data={**entry.data, CONF_ACCESS_TOKEN: access, CONF_REFRESH_TOKEN: refresh},
        )

    client = FeedrionClient(
        async_get_clientsession(hass),
        entry.data.get(CONF_API_URL, DEFAULT_API_URL),
        entry.data.get(CONF_ACCESS_TOKEN),
        entry.data.get(CONF_REFRESH_TOKEN),
        on_tokens=save_tokens,
    )
    coordinator = FeedrionCoordinator(hass, entry, client)
    await coordinator.async_config_entry_first_refresh()

    stocks = StocksCoordinator(hass, entry, coordinator)
    if stocks.enabled:
        await stocks.async_refresh()

    events = FeedrionEvents(hass, entry, client)
    await events.poll()
    entry.async_on_unload(async_track_time_interval(hass, events.poll, EVENTS_INTERVAL))

    entry.runtime_data = FeedrionRuntime(client, coordinator, events, stocks, dict(entry.options))
    entry.async_on_unload(entry.add_update_listener(_reload_on_options))
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def _reload_on_options(hass: HomeAssistant, entry: FeedrionConfigEntry) -> None:
    # Saving rotated tokens updates the entry too: only an OPTIONS change
    # is worth a reload.
    if dict(entry.options) != entry.runtime_data.options:
        await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: FeedrionConfigEntry) -> bool:
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def async_remove_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Removing the integration signs this Home Assistant out of Feedrion."""
    client = FeedrionClient(
        async_get_clientsession(hass),
        entry.data.get(CONF_API_URL, DEFAULT_API_URL),
        entry.data.get(CONF_ACCESS_TOKEN),
        entry.data.get(CONF_REFRESH_TOKEN),
    )
    try:
        await client.disconnect()
    except Exception:  # noqa: BLE001 — best effort; the app can revoke it too
        pass
