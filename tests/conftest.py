"""Fixtures: a Feedrion API answering like the real one (aioclient_mock)."""

from __future__ import annotations

from typing import Any

import pytest

from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker

from custom_components.feedrion.const import (
    CONF_ACCESS_TOKEN,
    CONF_API_URL,
    CONF_FEEDS,
    CONF_REFRESH_TOKEN,
    DOMAIN,
)

API = "https://feedrion.example/api"
HA = API + "/integrations/v1/homeassistant"


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations: Any) -> None:
    return None


def state_payload(**overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "generated_at": "2026-10-25T10:00:00Z",
        "rss": {
            "unread": 42, "saved": 3, "starred": 5, "alerts_unseen": 1,
            "folders": [{"id": 7, "name": "Tech", "unread": 30}],
            "feeds": [{"id": 11, "title": "Daily Horizon", "folder_id": 7, "unread": 12}],
        },
        "tv": {
            "enabled": True, "hide_spoilers": True, "episodes_to_watch": 4, "shows_to_watch": 2,
            "next_upcoming": {"show_id": 1, "show_name": "Northwind", "episode_id": 900, "season": 2,
                              "number": 3, "name": None, "aired": "2026-10-28",
                              "aired_at": "2026-10-29T01:00:00Z", "runtime": 45},
        },
        "weather": [{
            "id": 5, "name": "Orléans", "country_code": "FR",
            "current": {"temperature": 12.5, "humidity": 80, "wind_speed": 3.1, "symbol": "partlycloudy_day",
                        "pressure": 1013.2, "time": "2026-10-25T10:00:00+00:00"},
            "hourly": [{"time": "2026-10-25T11:00:00+00:00", "temperature": 13.0, "symbol": "rain"}],
            "daily": [{"date": "2026-10-26", "min": 8.0, "max": 15.0, "symbol": "clearsky_day",
                       "precipitation": 0.0}],
        }],
        "weather_attribution": "Données météo : MET Norway (CC BY 4.0)",
        "currencies": [{"id": 3, "symbol": "EUR/USD", "name": "Euro → Dollar", "price": 1.08,
                        "change_pct": 0.2, "currency": "USD"}],
        "personal_stocks": [{"id": "p1", "symbol": "AAPL", "name": "Apple", "exchange": "NASDAQ",
                             "currency": "USD", "provider": "twelvedata"}],
        "personal_stocks_provider": "twelvedata",
        "ai": {"level": "ai", "used": 120, "quota": 1200},
    }
    payload.update(overrides)
    return payload


ARTICLE = {"id": 101, "feed_id": 11, "feed_title": "Daily Horizon", "title": "Hello", "masked": False,
           "url": "https://example.com/a", "image_url": None, "published_at": "2026-10-25T09:00:00Z",
           "summary": None, "read": False, "saved": False}
EPISODE = {"show_id": 1, "show_name": "Northwind", "episode_id": 800, "season": 1, "number": 5,
           "name": "Pilot", "aired": "2026-10-01", "aired_at": None, "runtime": 45, "poster_url": None,
           "backdrop_url": "https://artworks.example/fanart.jpg", "remaining": 3, "set_aside": False}


def mock_api(aioclient_mock: AiohttpClientMocker, *, state: dict | None = None, status: int = 200) -> None:
    if status != 200:
        aioclient_mock.get(f"{HA}/state", status=status, json={"detail": "premium_required"})
    else:
        aioclient_mock.get(f"{HA}/state", json=state or state_payload())
    aioclient_mock.get(f"{HA}/articles", json=[ARTICLE])
    aioclient_mock.get(f"{HA}/tv/to-watch", json=[EPISODE])
    aioclient_mock.get(f"{HA}/tv/upcoming", json=[state_payload()["tv"]["next_upcoming"]])
    aioclient_mock.get(f"{HA}/alerts", json=[{"article": {**ARTICLE, "id": 102, "title": "Rust 2.0"},
                                              "keyword": "Rust", "seen": False,
                                              "matched_at": "2026-10-25T09:30:00Z"}])
    aioclient_mock.get(f"{HA}/events", json={"cursor": "a1|m1", "events": []})
    aioclient_mock.get(f"{HA}/catalog", json={"folders": state_payload()["rss"]["folders"],
                                              "feeds": state_payload()["rss"]["feeds"]})


@pytest.fixture
def entry(hass: HomeAssistant) -> MockConfigEntry:
    config_entry = MockConfigEntry(
        domain=DOMAIN,
        title="Feedrion (Max)",
        data={CONF_API_URL: API, CONF_ACCESS_TOKEN: "access-1", CONF_REFRESH_TOKEN: "refresh-1"},
        options={CONF_FEEDS: ["11"]},
    )
    config_entry.add_to_hass(hass)
    return config_entry
