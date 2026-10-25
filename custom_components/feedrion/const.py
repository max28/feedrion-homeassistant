"""Constants for the Feedrion integration."""

from __future__ import annotations

from datetime import timedelta
from typing import Final

DOMAIN: Final = "feedrion"

DEFAULT_API_URL: Final = "https://api.feedrion.com/api"

# Config entry data.
CONF_API_URL: Final = "api_url"
CONF_ACCESS_TOKEN: Final = "access_token"
CONF_REFRESH_TOKEN: Final = "refresh_token"
CONF_FAMILY_ID: Final = "family_id"

# Options.
CONF_FEEDS: Final = "feeds"
CONF_ARTICLES: Final = "articles"
CONF_STOCK_PROVIDER: Final = "stock_provider"
CONF_STOCK_KEY: Final = "stock_api_key"
CONF_STOCK_INTERVAL: Final = "stock_interval_minutes"

DEFAULT_ARTICLES: Final = 10
MAX_ARTICLES: Final = 50
MAX_FEEDS: Final = 50

STOCK_PROVIDERS: Final = ("twelvedata", "alphavantage", "eodhd")
# The free plans' floors: the reader's own key, the reader's own daily budget.
STOCK_MIN_INTERVAL: Final = {"twelvedata": 15, "alphavantage": 180, "eodhd": 60}

STATE_INTERVAL: Final = timedelta(minutes=5)
EVENTS_INTERVAL: Final = timedelta(seconds=60)

EVENT_NEW_ARTICLE: Final = "feedrion_new_article"
EVENT_ALERT: Final = "feedrion_alert"

ISSUE_PREMIUM: Final = "premium_required"
