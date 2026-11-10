"""Upcoming: the episodes announced for the shows the reader follows, and the
releases of the films they wait for."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import TYPE_CHECKING, Any

from homeassistant.components.calendar import CalendarEntity, CalendarEvent
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.util import dt as dt_util

from .coordinator import FeedrionCoordinator
from .entity import FeedrionEntity

if TYPE_CHECKING:
    from . import FeedrionConfigEntry


def episode_event(e: dict[str, Any]) -> CalendarEvent | None:
    """An episode as a calendar event: a timed hour when its broadcast time is
    known, otherwise an all-day event on the channel's day."""
    label = f"{e.get('show_name')} S{int(e.get('season') or 0):02d}E{int(e.get('number') or 0):02d}"
    if e.get("name"):
        label += f" · {e['name']}"
    uid = f"feedrion-episode-{e.get('episode_id')}"
    start: date | datetime | None = None
    end: date | datetime | None = None
    if e.get("aired_at"):
        start = dt_util.parse_datetime(e["aired_at"])
        if start is not None:
            end = start + timedelta(minutes=int(e.get("runtime") or 30))
    if start is None and e.get("aired"):
        start = dt_util.parse_date(e["aired"])
        end = start + timedelta(days=1) if start else None
    if start is None or end is None:
        return None
    return CalendarEvent(start=start, end=end, summary=label, uid=uid)


def movie_event(m: dict[str, Any]) -> CalendarEvent | None:
    """A film's release: an all-day event on the reader's country's day."""
    day = dt_util.parse_date(m.get("release_date") or "") if m.get("release_date") else None
    if day is None:
        return None
    label = m.get("name") or ""
    if m.get("year"):
        label += f" ({m['year']})"
    return CalendarEvent(start=day, end=day + timedelta(days=1), summary=label,
                         uid=f"feedrion-movie-{m.get('id')}")


def _sort_key(ev: CalendarEvent) -> datetime:
    start = ev.start
    if isinstance(start, datetime):
        return start
    return dt_util.start_of_local_day(start)


class FeedrionUpcoming(FeedrionEntity, CalendarEntity):
    _attr_translation_key = "upcoming"

    def __init__(self, coordinator: FeedrionCoordinator, entry_id: str) -> None:
        super().__init__(coordinator, entry_id, "tv_upcoming")

    def _events(self) -> list[CalendarEvent]:
        data = self.coordinator.data
        events = [ev for e in (data.upcoming if data else []) if (ev := episode_event(e))]
        return sorted(events, key=_sort_key)

    @property
    def event(self) -> CalendarEvent | None:
        return _next(self._events())

    async def async_get_events(self, hass: HomeAssistant, start_date: datetime, end_date: datetime) -> list[CalendarEvent]:
        return [ev for ev in self._events() if _sort_key(ev) < end_date and _end(ev) > start_date]


class FeedrionMovieReleases(FeedrionEntity, CalendarEntity):
    """The releases of the followed films not out yet (« Films à venir »)."""

    _attr_translation_key = "movie_releases"

    def __init__(self, coordinator: FeedrionCoordinator, entry_id: str) -> None:
        super().__init__(coordinator, entry_id, "movie_releases")

    @property
    def available(self) -> bool:
        data = self.coordinator.data
        return super().available and bool(data and (data.state.get("movies") or {}).get("enabled"))

    def _events(self) -> list[CalendarEvent]:
        data = self.coordinator.data
        events = [ev for m in (data.movies_upcoming if data else []) if (ev := movie_event(m))]
        return sorted(events, key=_sort_key)

    @property
    def event(self) -> CalendarEvent | None:
        return _next(self._events())

    async def async_get_events(self, hass: HomeAssistant, start_date: datetime, end_date: datetime) -> list[CalendarEvent]:
        return [ev for ev in self._events() if _sort_key(ev) < end_date and _end(ev) > start_date]


def _next(events: list[CalendarEvent]) -> CalendarEvent | None:
    now = dt_util.now()
    for ev in events:
        if _sort_key(ev) >= now or (isinstance(ev.end, datetime) and ev.end > now) or (
            not isinstance(ev.end, datetime) and dt_util.start_of_local_day(ev.end) > now
        ):
            return ev
    return None


def _end(ev: CalendarEvent) -> datetime:
    return ev.end if isinstance(ev.end, datetime) else dt_util.start_of_local_day(ev.end)


async def async_setup_entry(
    hass: HomeAssistant, entry: FeedrionConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data.coordinator
    async_add_entities([
        FeedrionUpcoming(coordinator, entry.entry_id),
        FeedrionMovieReleases(coordinator, entry.entry_id),
    ])
