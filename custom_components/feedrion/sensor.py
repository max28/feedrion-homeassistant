"""Sensors: counters, latest articles, TV shows, AI quota, currencies, « Mes actions »."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from typing import TYPE_CHECKING, Any

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorStateClass
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.util import dt as dt_util

from .coordinator import FeedrionCoordinator, StocksCoordinator
from .entity import FeedrionEntity

if TYPE_CHECKING:
    from . import FeedrionConfigEntry

MAX_ARTICLE_ATTRS = 50


def _article(a: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": a.get("id"),
        "title": a.get("title"),
        "feed": a.get("feed_title"),
        "masked": a.get("masked", False),
        "url": a.get("url"),
        "image_url": a.get("image_url"),
        "published_at": a.get("published_at"),
        "summary": a.get("summary"),
    }


def _episode(e: dict[str, Any] | None) -> dict[str, Any] | None:
    if not e:
        return None
    return {
        "show": e.get("show_name"),
        "show_id": e.get("show_id"),
        "episode_id": e.get("episode_id"),
        "season": e.get("season"),
        "number": e.get("number"),
        "name": e.get("name"),
        "aired": e.get("aired"),
        "poster_url": e.get("poster_url"),
    }


class _ValueSensor(FeedrionEntity, SensorEntity):
    """A sensor whose value is read from the state with a function."""

    def __init__(
        self, coordinator: FeedrionCoordinator, entry_id: str, key: str, value: Callable[[dict], Any],
        *, translation_key: str | None = None, name: str | None = None, icon: str | None = None,
        unit: str | None = None, attrs: Callable[[dict], dict] | None = None,
        state_class: SensorStateClass | None = SensorStateClass.MEASUREMENT,
        device_class: SensorDeviceClass | None = None,
    ) -> None:
        super().__init__(coordinator, entry_id, key)
        self._value = value
        self._attrs = attrs
        if translation_key:
            self._attr_translation_key = translation_key
        if name:
            self._attr_name = name
        self._attr_icon = icon
        self._attr_native_unit_of_measurement = unit
        self._attr_state_class = state_class
        self._attr_device_class = device_class

    @property
    def _data(self) -> dict:
        data = self.coordinator.data
        return {"state": data.state, "articles": data.articles, "to_watch": data.to_watch,
                "upcoming": data.upcoming} if data else {}

    def _eval(self, fn: Callable[[dict], Any]) -> Any:
        try:
            return fn(self._data)
        except (KeyError, TypeError, IndexError):
            return _MISSING

    @property
    def available(self) -> bool:
        return super().available and self._eval(self._value) is not _MISSING

    @property
    def native_value(self) -> Any:
        value = self._eval(self._value)
        return None if value is _MISSING else value

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        if not self._attrs:
            return None
        attrs = self._eval(self._attrs)
        return None if attrs is _MISSING else attrs


_MISSING = object()


def _find(items: list[dict] | None, item_id: Any) -> dict | None:
    return next((i for i in items or [] if i.get("id") == item_id), None)


def _parse_time(value: Any) -> datetime | None:
    return dt_util.parse_datetime(value) if isinstance(value, str) else None


def _fixed_sensors(c: FeedrionCoordinator, eid: str) -> list[SensorEntity]:
    rss = lambda d: d["state"]["rss"]  # noqa: E731
    tv = lambda d: d["state"]["tv"]  # noqa: E731
    sensors: list[SensorEntity] = [
        _ValueSensor(c, eid, "unread", lambda d: rss(d)["unread"], translation_key="unread",
                     icon="mdi:rss", unit="articles"),
        _ValueSensor(c, eid, "saved", lambda d: rss(d)["saved"], translation_key="saved",
                     icon="mdi:bookmark", unit="articles"),
        _ValueSensor(c, eid, "starred", lambda d: rss(d)["starred"], translation_key="starred",
                     icon="mdi:star", unit="articles"),
        _ValueSensor(c, eid, "alerts", lambda d: rss(d)["alerts_unseen"], translation_key="alerts",
                     icon="mdi:bell-ring", unit="articles"),
        _ValueSensor(
            c, eid, "latest_articles", lambda d: len(d["articles"]), translation_key="latest_articles",
            icon="mdi:newspaper-variant-multiple", unit="articles",
            attrs=lambda d: {"articles": [_article(a) for a in d["articles"][:MAX_ARTICLE_ATTRS]]},
        ),
        _ValueSensor(
            c, eid, "episodes_to_watch",
            lambda d: tv(d)["episodes_to_watch"] if tv(d).get("enabled") else _MISSING,
            translation_key="episodes_to_watch", icon="mdi:television-play", unit="episodes",
            attrs=lambda d: {
                "shows_to_watch": tv(d).get("shows_to_watch"),
                "next": [_episode(e) for e in d["to_watch"][:20]],
            },
        ),
        _ValueSensor(
            c, eid, "next_episode",
            lambda d: _next_air(tv(d).get("next_upcoming")) if tv(d).get("enabled") else _MISSING,
            translation_key="next_episode", icon="mdi:calendar-star",
            device_class=SensorDeviceClass.TIMESTAMP, state_class=None,
            attrs=lambda d: _episode(tv(d).get("next_upcoming")) or {},
        ),
        _ValueSensor(
            c, eid, "ai_quota",
            lambda d: d["state"]["ai"]["used"] if d["state"].get("ai") else _MISSING,
            translation_key="ai_quota", icon="mdi:creation", unit="articles",
            attrs=lambda d: {"quota": d["state"]["ai"]["quota"], "level": d["state"]["ai"]["level"]}
            if d["state"].get("ai") else {},
        ),
    ]
    return sensors


def _next_air(episode: dict | None) -> datetime | None:
    if not episode:
        return None
    if episode.get("aired_at"):
        return _parse_time(episode["aired_at"])
    if episode.get("aired"):
        day = dt_util.parse_date(episode["aired"])
        return dt_util.start_of_local_day(day) if day else None
    return None


def _folder_sensor(c: FeedrionCoordinator, eid: str, folder: dict) -> SensorEntity:
    fid = folder["id"]
    return _ValueSensor(
        c, eid, f"folder_{fid}",
        lambda d: (_find(d["state"]["rss"]["folders"], fid) or {}).get("unread", _MISSING),
        name=f"{folder['name']} unread", icon="mdi:folder", unit="articles",
    )


def _feed_sensor(c: FeedrionCoordinator, eid: str, feed: dict) -> SensorEntity:
    fid = feed["id"]
    return _ValueSensor(
        c, eid, f"feed_{fid}",
        lambda d: (_find(d["state"]["rss"]["feeds"], fid) or {}).get("unread", _MISSING),
        name=f"{feed['title']} unread", icon="mdi:rss-box", unit="articles",
    )


def _currency_sensor(c: FeedrionCoordinator, eid: str, item: dict) -> SensorEntity:
    iid = item["id"]
    def value(d: dict) -> Any:
        found = _find(d["state"]["currencies"], iid)
        return _MISSING if found is None else found.get("price")
    return _ValueSensor(
        c, eid, f"currency_{iid}", value, name=item.get("name") or item["symbol"],
        icon="mdi:currency-eur", unit=item.get("currency"),
        attrs=lambda d: {k: (_find(d["state"]["currencies"], iid) or {}).get(k)
                         for k in ("symbol", "change_pct")},
    )


class PersonalStockSensor(FeedrionEntity, SensorEntity):
    """One of « Mes actions », quoted here with the reader's own key."""

    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:chart-line"

    def __init__(self, coordinator: StocksCoordinator, entry_id: str, stock: dict) -> None:
        super().__init__(coordinator, entry_id, f"stock_{stock['id']}")
        self._stock = stock
        self._attr_name = stock.get("name") or stock["symbol"]
        self._attr_native_unit_of_measurement = stock.get("currency")

    @property
    def native_value(self) -> float | None:
        quote = (self.coordinator.data or {}).get(self._stock["id"])
        return quote.price if quote else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        quote = (self.coordinator.data or {}).get(self._stock["id"])
        coordinator: StocksCoordinator = self.coordinator  # type: ignore[assignment]
        return {
            "symbol": self._stock["symbol"],
            "exchange": self._stock.get("exchange"),
            "provider": coordinator.provider,
            "change_pct": quote.change_pct if quote else None,
            "as_of": quote.as_of.isoformat() if quote and quote.as_of else None,
            "error": coordinator.errors.get(self._stock["id"]),
        }


async def async_setup_entry(
    hass: HomeAssistant, entry: FeedrionConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    runtime = entry.runtime_data
    coordinator = runtime.coordinator
    eid = entry.entry_id
    async_add_entities(_fixed_sensors(coordinator, eid))
    known: set[str] = set()

    @callback
    def add_dynamic() -> None:
        data = coordinator.data
        if data is None:
            return
        new: list[SensorEntity] = []
        for folder in data.state["rss"].get("folders") or []:
            if (key := f"folder_{folder['id']}") not in known:
                known.add(key)
                new.append(_folder_sensor(coordinator, eid, folder))
        for feed in data.state["rss"].get("feeds") or []:
            if (key := f"feed_{feed['id']}") not in known:
                known.add(key)
                new.append(_feed_sensor(coordinator, eid, feed))
        for item in data.state.get("currencies") or []:
            if (key := f"currency_{item['id']}") not in known:
                known.add(key)
                new.append(_currency_sensor(coordinator, eid, item))
        if runtime.stocks.enabled:
            for stock in runtime.stocks.symbols():
                if (key := f"stock_{stock['id']}") not in known:
                    known.add(key)
                    new.append(PersonalStockSensor(runtime.stocks, eid, stock))
        if new:
            async_add_entities(new)

    add_dynamic()
    entry.async_on_unload(coordinator.async_add_listener(add_dynamic))
