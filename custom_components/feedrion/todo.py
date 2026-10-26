"""Two to-do lists: Saved (read later) and To watch (next episodes).

Checking an item off is the app's own action: a saved article is marked read
and leaves Saved; an episode is marked watched (and reaches Trakt, Simkl and
any paired media server like any other watch). Adding to Saved takes a link. Nothing else is editable from here.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from homeassistant.components.todo import TodoItem, TodoItemStatus, TodoListEntity, TodoListEntityFeature
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .api import FeedrionError
from .const import DOMAIN
from .coordinator import FeedrionCoordinator
from .entity import FeedrionEntity

if TYPE_CHECKING:
    from . import FeedrionConfigEntry


class SavedList(FeedrionEntity, TodoListEntity):
    _attr_translation_key = "saved_list"
    _attr_supported_features = TodoListEntityFeature.CREATE_TODO_ITEM | TodoListEntityFeature.UPDATE_TODO_ITEM

    def __init__(self, coordinator: FeedrionCoordinator, entry_id: str) -> None:
        super().__init__(coordinator, entry_id, "todo_saved")

    @property
    def todo_items(self) -> list[TodoItem]:
        data = self.coordinator.data
        return [
            TodoItem(
                uid=str(a["id"]),
                summary=a.get("title") or "",
                status=TodoItemStatus.NEEDS_ACTION,
                description=" · ".join(x for x in (a.get("feed_title"), a.get("url")) if x) or None,
            )
            for a in (data.saved if data else [])
        ]

    async def async_create_todo_item(self, item: TodoItem) -> None:
        url = (item.summary or "").strip()
        if not url.startswith(("https://", "http://")):
            raise ServiceValidationError(translation_domain=DOMAIN, translation_key="link_required")
        try:
            await self.coordinator.client.save_url(url, None)
        except FeedrionError as err:
            raise HomeAssistantError(str(err)) from err
        await self.coordinator.async_request_refresh()

    async def async_update_todo_item(self, item: TodoItem) -> None:
        if item.status != TodoItemStatus.COMPLETED or not item.uid:
            return
        try:
            await self.coordinator.client.done_saved(int(item.uid))
        except FeedrionError as err:
            raise HomeAssistantError(str(err)) from err
        await self.coordinator.async_request_refresh()


class ToWatchList(FeedrionEntity, TodoListEntity):
    _attr_translation_key = "to_watch_list"
    _attr_supported_features = TodoListEntityFeature.UPDATE_TODO_ITEM

    def __init__(self, coordinator: FeedrionCoordinator, entry_id: str) -> None:
        super().__init__(coordinator, entry_id, "todo_to_watch")

    @property
    def available(self) -> bool:
        data = self.coordinator.data
        return super().available and bool(data and (data.state.get("tv") or {}).get("enabled"))

    @property
    def todo_items(self) -> list[TodoItem]:
        data = self.coordinator.data
        items = []
        for e in data.to_watch if data else []:
            label = f"{e.get('show_name')} S{int(e.get('season') or 0):02d}E{int(e.get('number') or 0):02d}"
            if e.get("name"):
                label += f" · {e['name']}"
            items.append(TodoItem(uid=str(e["episode_id"]), summary=label, status=TodoItemStatus.NEEDS_ACTION))
        return items

    async def async_update_todo_item(self, item: TodoItem) -> None:
        if item.status != TodoItemStatus.COMPLETED or not item.uid:
            return
        try:
            await self.coordinator.client.episode_watched(int(item.uid))
        except FeedrionError as err:
            raise HomeAssistantError(str(err)) from err
        await self.coordinator.async_request_refresh()


async def async_setup_entry(
    hass: HomeAssistant, entry: FeedrionConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data.coordinator
    async_add_entities([SavedList(coordinator, entry.entry_id), ToWatchList(coordinator, entry.entry_id)])
