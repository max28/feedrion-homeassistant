"""Base entity: every entity belongs to one « Feedrion » service device."""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity, DataUpdateCoordinator

from .const import DOMAIN


class FeedrionEntity(CoordinatorEntity[DataUpdateCoordinator]):
    _attr_has_entity_name = True

    def __init__(self, coordinator: DataUpdateCoordinator, entry_id: str, key: str) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry_id}_{key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry_id)},
            name="Feedrion",
            manufacturer="Feedrion",
            entry_type=DeviceEntryType.SERVICE,
            configuration_url="https://feedrion.com",
        )
