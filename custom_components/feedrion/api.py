"""A small client for Feedrion's Home Assistant API (``/integrations/v1``)."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import Any
from urllib.parse import urlsplit

import aiohttp

from .const import DEFAULT_API_URL

TIMEOUT = aiohttp.ClientTimeout(total=30)


class FeedrionError(Exception):
    """Feedrion answered something other than a success."""

    def __init__(self, status: int, detail: str | None = None) -> None:
        super().__init__(f"Feedrion answered {status}" + (f": {detail}" if detail else ""))
        self.status = status
        self.detail = detail


class FeedrionAuthError(FeedrionError):
    """The session is gone (revoked from the app): the user has to pair again."""


class FeedrionPremiumRequired(FeedrionError):
    """The account is not Premium (any more)."""


class FeedrionConnectionError(FeedrionError):
    """Feedrion could not be reached; worth retrying unchanged."""


def normalize_api_url(value: str | None) -> str:
    """An https API root without its trailing slash. Plain http is refused:
    a token would travel in clear."""
    url = (value or "").strip().rstrip("/")
    if not url:
        return DEFAULT_API_URL
    parts = urlsplit(url)
    if parts.scheme != "https" or not parts.netloc:
        raise ValueError("https_required")
    return url


TokenSaver = Callable[[str, str], Awaitable[None] | None]


class FeedrionClient:
    """One linked Home Assistant, i.e. one Feedrion session."""

    def __init__(
        self,
        session: aiohttp.ClientSession,
        api_url: str,
        access_token: str | None = None,
        refresh_token: str | None = None,
        on_tokens: TokenSaver | None = None,
    ) -> None:
        self._session = session
        self._base = normalize_api_url(api_url)
        self.access_token = access_token
        self.refresh_token = refresh_token
        self._on_tokens = on_tokens
        self._refreshing = asyncio.Lock()

    # ── Pairing (no session yet) ────────────────────────────────────────────

    async def start_pairing(self, label: str | None) -> dict[str, Any]:
        return await self._request(
            "POST", "/integrations/v1/pair/start",
            json={"kind": "homeassistant", "label": (label or "")[:60] or None},
            auth=False,
        )

    async def poll_pairing(self, device_code: str) -> dict[str, Any]:
        try:
            return await self._request(
                "POST", "/integrations/v1/pair/poll", json={"device_code": device_code}, auth=False,
            )
        except FeedrionError as err:
            if err.status == 410:
                return {"status": "expired"}
            raise

    # ── The linked session ──────────────────────────────────────────────────

    async def me(self) -> dict[str, Any]:
        return await self._request("GET", "/integrations/v1/me")

    async def state(self, feeds: list[int]) -> dict[str, Any]:
        params = {"feeds": ",".join(str(f) for f in feeds)} if feeds else None
        return await self._request("GET", "/integrations/v1/homeassistant/state", params=params)

    async def catalog(self) -> dict[str, Any]:
        return await self._request("GET", "/integrations/v1/homeassistant/catalog")

    async def articles(self, scope: str = "all", unread_only: bool = True, limit: int = 10) -> list[dict[str, Any]]:
        return await self._request(
            "GET", "/integrations/v1/homeassistant/articles",
            params={"scope": scope, "unread_only": "true" if unread_only else "false", "limit": str(limit)},
        )

    async def to_watch(self) -> list[dict[str, Any]]:
        return await self._request("GET", "/integrations/v1/homeassistant/tv/to-watch")

    async def upcoming(self, days: int) -> list[dict[str, Any]]:
        return await self._request(
            "GET", "/integrations/v1/homeassistant/tv/upcoming", params={"days": str(days)},
        )

    async def events(self, cursor: str | None, feeds: list[int]) -> dict[str, Any]:
        params: dict[str, str] = {}
        if cursor:
            params["cursor"] = cursor
        if feeds:
            params["feeds"] = ",".join(str(f) for f in feeds)
        return await self._request("GET", "/integrations/v1/homeassistant/events", params=params or None)

    async def briefing(self, scope: str, limit: int) -> dict[str, Any]:
        return await self._request(
            "GET", "/integrations/v1/homeassistant/briefing", params={"scope": scope, "limit": str(limit)},
        )

    async def mark_read(self, article_ids: list[int]) -> None:
        await self._request("POST", "/integrations/v1/homeassistant/articles/read", json={"article_ids": article_ids})

    async def mark_all_read(self, feed_id: int | None = None, folder_id: int | None = None) -> None:
        await self._request(
            "POST", "/integrations/v1/homeassistant/articles/read-all",
            json={"feed_id": feed_id, "folder_id": folder_id},
        )

    async def save_url(self, url: str, title: str | None = None) -> dict[str, Any]:
        return await self._request("POST", "/integrations/v1/homeassistant/saved", json={"url": url, "title": title})

    async def done_saved(self, article_id: int) -> None:
        await self._request("DELETE", f"/integrations/v1/homeassistant/saved/{int(article_id)}")

    async def episode_watched(self, episode_id: int) -> None:
        await self._request("POST", f"/integrations/v1/homeassistant/tv/episodes/{int(episode_id)}/watched")

    async def disconnect(self) -> None:
        await self._request("POST", "/integrations/v1/disconnect")

    # ── Transport ───────────────────────────────────────────────────────────

    async def _request(
        self, method: str, path: str, *, json: Any = None, params: dict[str, str] | None = None,
        auth: bool = True,
    ) -> Any:
        status, body = await self._send(method, path, json, params, auth)
        if auth and status == 401:
            # An expired access token, most of the time: rotate once and retry.
            if not await self._refresh():
                raise FeedrionAuthError(401, "session_expired")
            status, body = await self._send(method, path, json, params, auth)
        if 200 <= status < 300:
            return body
        detail = body.get("detail") if isinstance(body, dict) and isinstance(body.get("detail"), str) else None
        if status == 401:
            raise FeedrionAuthError(status, detail)
        if status == 402:
            raise FeedrionPremiumRequired(status, detail)
        if status == 429 or status >= 500:
            raise FeedrionConnectionError(status, detail)
        raise FeedrionError(status, detail)

    async def _send(
        self, method: str, path: str, json: Any, params: dict[str, str] | None, auth: bool,
    ) -> tuple[int, Any]:
        headers = {"Accept": "application/json"}
        if auth:
            if not self.access_token:
                raise FeedrionAuthError(401, "not_linked")
            headers["Authorization"] = f"Bearer {self.access_token}"
        try:
            async with self._session.request(
                method, self._base + path, json=json, params=params, headers=headers, timeout=TIMEOUT,
            ) as resp:
                if resp.status == 204:
                    return resp.status, None
                try:
                    body = await resp.json(content_type=None)
                except (aiohttp.ContentTypeError, ValueError):
                    body = None
                return resp.status, body
        except (aiohttp.ClientError, asyncio.TimeoutError) as err:
            raise FeedrionConnectionError(0, str(err) or type(err).__name__) from err

    async def _refresh(self) -> bool:
        if not self.refresh_token:
            return False
        stale = self.access_token
        async with self._refreshing:
            if self.access_token != stale:
                return True  # another call rotated it meanwhile
            status, body = await self._send(
                "POST", "/auth/refresh", {"refresh_token": self.refresh_token}, None, auth=False,
            )
            if status == 401:
                return False
            if not 200 <= status < 300 or not isinstance(body, dict) or not body.get("access_token"):
                raise FeedrionConnectionError(status, "refresh_failed")
            self.access_token = body["access_token"]
            self.refresh_token = body.get("refresh_token") or self.refresh_token
            if self._on_tokens is not None:
                result = self._on_tokens(self.access_token, self.refresh_token)
                if asyncio.iscoroutine(result):
                    await result
            return True
