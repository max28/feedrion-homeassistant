"""Data coordinators: Feedrion's state, the event poll, and « Mes actions »."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import (
    FeedrionAuthError,
    FeedrionClient,
    FeedrionError,
    FeedrionPremiumRequired,
)
from .const import (
    CONF_ARTICLES,
    CONF_FEEDS,
    CONF_STOCK_INTERVAL,
    CONF_STOCK_KEY,
    CONF_STOCK_PROVIDER,
    DEFAULT_ARTICLES,
    DOMAIN,
    EVENT_ALERT,
    EVENT_NEW_ARTICLE,
    ISSUE_PREMIUM,
    STATE_INTERVAL,
    STOCK_MIN_INTERVAL,
)
from .stocks import DAILY_LIMIT, Quote, QuoteError, fetch_quote

_LOGGER = logging.getLogger(__name__)

UPCOMING_DAYS = 31
SAVED_ITEMS = 50


def selected_feeds(entry: ConfigEntry) -> list[int]:
    return [int(f) for f in entry.options.get(CONF_FEEDS, []) if str(f).isdigit()]


def _premium_issue(hass: HomeAssistant, entry: ConfigEntry, missing: bool, pricing_url: str | None) -> None:
    issue_id = f"{ISSUE_PREMIUM}_{entry.entry_id}"
    if missing:
        ir.async_create_issue(
            hass, DOMAIN, issue_id, is_fixable=False, severity=ir.IssueSeverity.WARNING,
            translation_key=ISSUE_PREMIUM,
            translation_placeholders={"pricing_url": pricing_url or "https://feedrion.com/pricing"},
            learn_more_url=pricing_url or "https://feedrion.com/pricing",
        )
    else:
        ir.async_delete_issue(hass, DOMAIN, issue_id)


@dataclass
class FeedrionData:
    state: dict[str, Any]
    articles: list[dict[str, Any]] = field(default_factory=list)
    to_watch: list[dict[str, Any]] = field(default_factory=list)
    upcoming: list[dict[str, Any]] = field(default_factory=list)
    saved: list[dict[str, Any]] = field(default_factory=list)


class FeedrionCoordinator(DataUpdateCoordinator[FeedrionData]):
    """Everything the sensors show, in four calls every five minutes."""

    config_entry: ConfigEntry

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, client: FeedrionClient) -> None:
        super().__init__(hass, _LOGGER, config_entry=entry, name=DOMAIN, update_interval=STATE_INTERVAL)
        self.client = client
        self.premium_missing = False

    async def _async_update_data(self) -> FeedrionData:
        entry = self.config_entry
        try:
            state = await self.client.state(selected_feeds(entry))
            limit = int(entry.options.get(CONF_ARTICLES, DEFAULT_ARTICLES))
            articles = await self.client.articles("all", True, limit) if limit > 0 else []
            saved = await self.client.articles("saved", False, SAVED_ITEMS)
            tv = state.get("tv") or {}
            to_watch = await self.client.to_watch() if tv.get("enabled") else []
            upcoming = await self.client.upcoming(UPCOMING_DAYS) if tv.get("enabled") else []
        except FeedrionAuthError as err:
            raise ConfigEntryAuthFailed("The Feedrion session was revoked") from err
        except FeedrionPremiumRequired as err:
            if not self.premium_missing:
                self.premium_missing = True
                _premium_issue(self.hass, entry, True, None)
            raise UpdateFailed("Feedrion Premium is required") from err
        except FeedrionError as err:
            raise UpdateFailed(str(err)) from err
        if self.premium_missing:
            self.premium_missing = False
            _premium_issue(self.hass, entry, False, None)
        return FeedrionData(state=state, articles=articles, to_watch=to_watch, upcoming=upcoming,
                            saved=saved)


class FeedrionEvents:
    """Turns new articles of the selected feeds, and keyword alerts, into
    Home Assistant events. The first call only learns where to start, so
    connecting (or restarting) never fires a backlog of automations."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, client: FeedrionClient) -> None:
        self.hass = hass
        self.entry = entry
        self.client = client
        self.cursor: str | None = None

    async def poll(self, _now: datetime | None = None) -> None:
        try:
            page = await self.client.events(self.cursor, selected_feeds(self.entry))
        except FeedrionAuthError:
            self.entry.async_start_reauth(self.hass)
            return
        except FeedrionError as err:
            _LOGGER.debug("Feedrion events: %s", err)
            return
        self.cursor = page.get("cursor") or self.cursor
        for event in page.get("events") or []:
            article = event.get("article") or {}
            data = {
                "config_entry_id": self.entry.entry_id,
                "article_id": article.get("id"),
                "feed_id": article.get("feed_id"),
                "feed": article.get("feed_title"),
                "title": article.get("title"),
                "masked": article.get("masked", False),
                "url": article.get("url"),
                "image_url": article.get("image_url"),
                "published_at": article.get("published_at"),
            }
            if event.get("type") == "alert":
                self.hass.bus.async_fire(EVENT_ALERT, {**data, "keyword": event.get("keyword")})
            else:
                self.hass.bus.async_fire(EVENT_NEW_ARTICLE, data)


class StocksCoordinator(DataUpdateCoordinator[dict[str, Quote]]):
    """Quotes « Mes actions » with the reader's own key, within half its
    daily allowance (the phone spends the other half)."""

    config_entry: ConfigEntry

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, state: FeedrionCoordinator) -> None:
        provider = entry.options.get(CONF_STOCK_PROVIDER)
        minimum = STOCK_MIN_INTERVAL.get(provider or "", 60)
        minutes = max(int(entry.options.get(CONF_STOCK_INTERVAL) or minimum), minimum)
        super().__init__(hass, _LOGGER, config_entry=entry, name=f"{DOMAIN}_stocks",
                         update_interval=timedelta(minutes=minutes))
        self.provider: str | None = provider
        self.key: str | None = entry.options.get(CONF_STOCK_KEY)
        self.state = state
        self._day: date | None = None
        self._spent = 0
        self.errors: dict[str, str] = {}

    @property
    def enabled(self) -> bool:
        return bool(self.provider and self.key)

    def symbols(self) -> list[dict[str, Any]]:
        if self.state.data is None:
            return []
        stocks = self.state.data.state.get("personal_stocks") or []
        # A symbol is written for ONE provider; another provider's id would
        # quote nothing, or the wrong company.
        return [s for s in stocks if (s.get("provider") or self.provider) == self.provider]

    async def _async_update_data(self) -> dict[str, Quote]:
        quotes = dict(self.data or {})
        if not self.enabled:
            return quotes
        today = datetime.now(timezone.utc).date()
        if today != self._day:
            self._day, self._spent = today, 0
        budget = DAILY_LIMIT.get(self.provider or "", 0) // 2
        session = async_get_clientsession(self.hass)
        for stock in self.symbols():
            if self._spent >= budget:
                break
            symbol = stock["symbol"]
            self._spent += 1
            try:
                quotes[stock["id"]] = await fetch_quote(session, self.provider or "", self.key or "", symbol)
                self.errors.pop(stock["id"], None)
            except QuoteError as err:
                # The last quote stays; what went wrong is shown beside it.
                self.errors[stock["id"]] = str(err)[:200]
        return quotes
