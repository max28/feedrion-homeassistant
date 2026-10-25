"""One weather entity per city the reader follows in Feedrion (MET Norway data)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from homeassistant.components.weather import (
    Forecast,
    WeatherEntity,
    WeatherEntityFeature,
)
from homeassistant.const import UnitOfPrecipitationDepth, UnitOfPressure, UnitOfSpeed, UnitOfTemperature
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.util import dt as dt_util

from .coordinator import FeedrionCoordinator
from .entity import FeedrionEntity

if TYPE_CHECKING:
    from . import FeedrionConfigEntry

# MET Norway symbol codes (without _day/_night/_polartwilight) → HA conditions.
_CONDITIONS = {
    "clearsky": "sunny",
    "fair": "partlycloudy",
    "partlycloudy": "partlycloudy",
    "cloudy": "cloudy",
    "fog": "fog",
    "lightrain": "rainy",
    "rain": "rainy",
    "heavyrain": "pouring",
    "lightrainshowers": "rainy",
    "rainshowers": "rainy",
    "heavyrainshowers": "pouring",
    "lightsleet": "snowy-rainy",
    "sleet": "snowy-rainy",
    "heavysleet": "snowy-rainy",
    "lightsleetshowers": "snowy-rainy",
    "sleetshowers": "snowy-rainy",
    "heavysleetshowers": "snowy-rainy",
    "lightsnow": "snowy",
    "snow": "snowy",
    "heavysnow": "snowy",
    "lightsnowshowers": "snowy",
    "snowshowers": "snowy",
    "heavysnowshowers": "snowy",
}


def condition(symbol: str | None) -> str | None:
    """A MET symbol code as a Home Assistant condition."""
    if not symbol:
        return None
    base = symbol.split("_")[0]
    if "thunder" in base:
        return "lightning-rainy"
    if base == "clearsky" and symbol.endswith("_night"):
        return "clear-night"
    return _CONDITIONS.get(base)


class FeedrionWeather(FeedrionEntity, WeatherEntity):
    _attr_native_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_native_wind_speed_unit = UnitOfSpeed.METERS_PER_SECOND
    _attr_native_pressure_unit = UnitOfPressure.HPA
    _attr_native_precipitation_unit = UnitOfPrecipitationDepth.MILLIMETERS
    _attr_supported_features = WeatherEntityFeature.FORECAST_DAILY | WeatherEntityFeature.FORECAST_HOURLY

    def __init__(self, coordinator: FeedrionCoordinator, entry_id: str, place: dict) -> None:
        super().__init__(coordinator, entry_id, f"weather_{place['id']}")
        self._place_id = place["id"]
        self._attr_name = place["name"]

    @property
    def _place(self) -> dict | None:
        data = self.coordinator.data
        if data is None:
            return None
        return next((p for p in data.state.get("weather") or [] if p.get("id") == self._place_id), None)

    @property
    def _current(self) -> dict:
        place = self._place
        return (place or {}).get("current") or {}

    @property
    def available(self) -> bool:
        return super().available and self._place is not None

    @property
    def attribution(self) -> str | None:
        data = self.coordinator.data
        return data.state.get("weather_attribution") if data else None

    @property
    def condition(self) -> str | None:
        return condition(self._current.get("symbol"))

    @property
    def native_temperature(self) -> float | None:
        return self._current.get("temperature")

    @property
    def humidity(self) -> float | None:
        return self._current.get("humidity")

    @property
    def native_wind_speed(self) -> float | None:
        return self._current.get("wind_speed")

    @property
    def native_wind_gust_speed(self) -> float | None:
        return self._current.get("wind_gust")

    @property
    def wind_bearing(self) -> float | None:
        return self._current.get("wind_direction")

    @property
    def native_pressure(self) -> float | None:
        return self._current.get("pressure")

    @property
    def native_dew_point(self) -> float | None:
        return self._current.get("dew_point")

    @property
    def cloud_coverage(self) -> float | None:
        return self._current.get("cloud_cover")

    @property
    def uv_index(self) -> float | None:
        return self._current.get("uv_index")

    async def async_forecast_daily(self) -> list[Forecast] | None:
        out: list[Forecast] = []
        for day in (self._place or {}).get("daily") or []:
            parsed = dt_util.parse_date(day.get("date") or "")
            if parsed is None:
                continue
            out.append(Forecast(
                datetime=dt_util.start_of_local_day(parsed).isoformat(),
                condition=condition(day.get("symbol")),
                native_temperature=day.get("max"),
                native_templow=day.get("min"),
                native_precipitation=day.get("precipitation"),
                precipitation_probability=day.get("precipitation_probability"),
                native_wind_speed=day.get("wind_max"),
                native_wind_gust_speed=day.get("gust_max"),
                uv_index=day.get("uv_max"),
            ))
        return out

    async def async_forecast_hourly(self) -> list[Forecast] | None:
        out: list[Forecast] = []
        for hour in (self._place or {}).get("hourly") or []:
            if not hour.get("time"):
                continue
            out.append(Forecast(
                datetime=hour["time"],
                condition=condition(hour.get("symbol")),
                native_temperature=hour.get("temperature"),
                native_precipitation=hour.get("precipitation"),
                native_wind_speed=hour.get("wind_speed"),
                wind_bearing=hour.get("wind_direction"),
                humidity=hour.get("humidity"),
            ))
        return out

    @callback
    def _handle_coordinator_update(self) -> None:
        super()._handle_coordinator_update()
        self.hass.async_create_task(self.async_update_listeners(None))


async def async_setup_entry(
    hass: HomeAssistant, entry: FeedrionConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data.coordinator
    known: set[Any] = set()

    @callback
    def add_new() -> None:
        if coordinator.data is None:
            return
        new = []
        for place in coordinator.data.state.get("weather") or []:
            if place["id"] not in known:
                known.add(place["id"])
                new.append(FeedrionWeather(coordinator, entry.entry_id, place))
        if new:
            async_add_entities(new)

    add_new()
    entry.async_on_unload(coordinator.async_add_listener(add_new))
