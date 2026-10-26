"""My stocks, quoted by Home Assistant itself with the reader's OWN key.

Feedrion never relays a share price (the reader's free plan licenses personal
use, not redistribution), so the server only hands over the list of symbols.
The quote is fetched here, from this Home Assistant, straight from the
provider — the same thing the phone does. The key lives in this integration's
options and is sent to nobody but the provider.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from urllib.parse import quote as url_quote

import aiohttp

TIMEOUT = aiohttp.ClientTimeout(total=20)

# Requests a free key allows per day. The phone spends the same allowance and
# cannot see what Home Assistant spends, so only HALF of it is ever used here.
DAILY_LIMIT = {"twelvedata": 800, "alphavantage": 25, "eodhd": 20}


@dataclass
class Quote:
    price: float
    change_pct: float | None
    currency: str | None
    as_of: datetime | None


class QuoteError(Exception):
    """The provider refused (bad key, plan, unknown symbol, quota)."""


def _num(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(str(value).strip().rstrip("%"))
    except ValueError:
        return None


def _when(value: Any) -> datetime | None:
    if value in (None, ""):
        return None
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(value, timezone.utc)
    try:
        parsed = datetime.fromisoformat(str(value))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def parse_twelvedata(body: Any) -> Quote:
    if not isinstance(body, dict) or body.get("status") == "error":
        raise QuoteError((body or {}).get("message") if isinstance(body, dict) else "invalid answer")
    price = _num(body.get("close"))
    if price is None:
        raise QuoteError("no price")
    return Quote(price, _num(body.get("percent_change")), body.get("currency"),
                 _when(body.get("timestamp") or body.get("datetime")))


def parse_alphavantage(body: Any) -> Quote:
    quote = body.get("Global Quote") if isinstance(body, dict) else None
    if not quote:
        message = None
        if isinstance(body, dict):
            message = body.get("Note") or body.get("Information") or body.get("Error Message")
        raise QuoteError(message or "unknown symbol")
    price = _num(quote.get("05. price"))
    if price is None:
        raise QuoteError("no price")
    # A free key answers the last CLOSE: dated by its trading day, never "now".
    return Quote(price, _num(quote.get("10. change percent")), None, _when(quote.get("07. latest trading day")))


def parse_eodhd(body: Any) -> Quote:
    if not isinstance(body, dict):
        raise QuoteError("invalid answer")
    price = _num(body.get("close"))
    if price is None or price == 0:
        raise QuoteError("unknown symbol")
    return Quote(price, _num(body.get("change_p")), None, _when(body.get("timestamp")))


async def fetch_quote(session: aiohttp.ClientSession, provider: str, key: str, symbol: str) -> Quote:
    if provider == "twelvedata":
        url, params, parse = "https://api.twelvedata.com/quote", {"symbol": symbol, "apikey": key}, parse_twelvedata
    elif provider == "alphavantage":
        url = "https://www.alphavantage.co/query"
        params = {"function": "GLOBAL_QUOTE", "symbol": symbol, "apikey": key}
        parse = parse_alphavantage
    elif provider == "eodhd":
        url = f"https://eodhd.com/api/real-time/{url_quote(symbol, safe='.-_')}"
        params, parse = {"api_token": key, "fmt": "json"}, parse_eodhd
    else:
        raise QuoteError("unknown provider")
    try:
        async with session.get(url, params=params, timeout=TIMEOUT) as resp:
            if resp.status in (401, 403):
                raise QuoteError(f"refused ({resp.status})")
            try:
                body = await resp.json(content_type=None)
            except (aiohttp.ContentTypeError, ValueError) as err:
                raise QuoteError(f"HTTP {resp.status}") from err
    except (aiohttp.ClientError, asyncio.TimeoutError) as err:
        raise QuoteError(str(err) or type(err).__name__) from err
    return parse(body)
