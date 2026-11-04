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
    if isinstance(body, list) and body:
        body = body[0]
    if not isinstance(body, dict):
        raise QuoteError("invalid answer")
    # An unknown ticker is not a 404 here: every field says "NA".
    price = _num(body.get("close"))
    if price is None or price == 0:
        raise QuoteError("unknown symbol")
    change = _num(body.get("change_p"))
    previous = _num(body.get("previousClose"))
    # A 0 % (or no figure) that the previous close contradicts is not believed.
    if previous and (change is None or (change == 0 and previous != price)):
        change = (price - previous) / previous * 100
    return Quote(price, change, None, _when(body.get("timestamp")))


def provider_id(stock: dict[str, Any]) -> str:
    """What the provider needs to quote a stock: its id (`GLE.PA` for EODHD,
    `AI:XPAR` for Twelve Data), never the bare ticker — `GLE` alone is quoted
    on a US exchange, i.e. another company. The ticker is the fallback for a
    stock stored without an id."""
    return str(stock.get("id") or stock.get("symbol") or "")


async def fetch_quote(session: aiohttp.ClientSession, provider: str, key: str, symbol: str) -> Quote:
    if provider == "twelvedata":
        # `SYMBOL:MIC` is Feedrion's spelling; Twelve Data takes the two apart.
        ticker, _, mic = symbol.partition(":")
        params = {"symbol": ticker, "apikey": key}
        if mic:
            params["mic_code"] = mic
        url, parse = "https://api.twelvedata.com/quote", parse_twelvedata
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
