"""« À venir »: the episodes announced for the shows the reader follows."""

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
        now = dt_util.now()
        for ev in self._events():
            if _sort_key(ev) >= now or (isinstance(ev.end, datetime) and ev.end > now) or (
                not isinstance(ev.end, datetime) and dt_util.start_of_local_day(ev.end) > now
            ):
                return ev
        return None

    async def async_get_events(self, hass: HomeAssistant, start_date: datetime, end_date: datetime) -> list[CalendarEvent]:
        return [ev for ev in self._events() if _sort_key(ev) < end_date and _end(ev) > start_date]


def _end(ev: CalendarEvent) -> datetime:
    return ev.end if isinstance(ev.end, datetime) else dt_util.start_of_local_day(ev.end)


async def async_setup_entry(
    hass: HomeAssistant, entry: FeedrionConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    async_add_entities([FeedrionUpcoming(entry.runtime_data.coordinator, entry.entry_id)])
