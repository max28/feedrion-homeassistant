"""Pure helpers: https only, MET symbols, provider quotes, calendar events."""

from __future__ import annotations

from datetime import date

import pytest

from custom_components.feedrion.api import normalize_api_url
from custom_components.feedrion.calendar import episode_event
from custom_components.feedrion.const import DEFAULT_API_URL
from custom_components.feedrion.stocks import (
    QuoteError,
    parse_alphavantage,
    parse_eodhd,
    parse_twelvedata,
)
from custom_components.feedrion.weather import condition


def test_api_url_is_https_only() -> None:
    assert normalize_api_url("") == DEFAULT_API_URL
    assert normalize_api_url("https://x.example/api/") == "https://x.example/api"
    with pytest.raises(ValueError):
        normalize_api_url("http://x.example/api")


@pytest.mark.parametrize(("symbol", "expected"), [
    ("clearsky_day", "sunny"), ("clearsky_night", "clear-night"), ("fair_night", "partlycloudy"),
    ("heavyrainandthunder", "lightning-rainy"), ("lightsnowshowers_day", "snowy"), ("fog", "fog"),
    (None, None), ("unknown", None),
])
def test_met_symbols(symbol: str | None, expected: str | None) -> None:
    assert condition(symbol) == expected


def test_quotes() -> None:
    q = parse_twelvedata({"close": "189.5", "percent_change": "-1.2", "currency": "USD", "timestamp": 1761400000})
    assert q.price == 189.5 and q.change_pct == -1.2 and q.as_of is not None
    with pytest.raises(QuoteError):
        parse_twelvedata({"status": "error", "message": "available starting with the Grow plan"})
    a = parse_alphavantage({"Global Quote": {"05. price": "10.0", "10. change percent": "0.5%",
                                             "07. latest trading day": "2026-10-24"}})
    assert a.price == 10.0 and a.change_pct == 0.5 and a.as_of.date() == date(2026, 10, 24)
    with pytest.raises(QuoteError):
        parse_alphavantage({"Note": "25 requests per day"})
    e = parse_eodhd({"close": 31.2, "change_p": 1.1, "timestamp": 1761400000})
    assert e.price == 31.2
    with pytest.raises(QuoteError):
        parse_eodhd({"close": 0})


def test_episode_events() -> None:
    timed = episode_event({"show_name": "Northwind", "season": 2, "number": 3, "episode_id": 9,
                           "aired_at": "2026-10-29T01:00:00Z", "runtime": 45})
    assert timed.summary == "Northwind S02E03" and (timed.end - timed.start).seconds == 45 * 60
    day = episode_event({"show_name": "Orbit Nine", "season": 1, "number": 1, "episode_id": 10,
                         "name": "Pilot", "aired": "2026-11-02"})
    assert day.start == date(2026, 11, 2) and day.summary.endswith("· Pilot")
    assert episode_event({"show_name": "X", "season": 1, "number": 1, "episode_id": 1}) is None
