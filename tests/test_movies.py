"""Feedrion's « Films » extension in Home Assistant: two sensors, a to-do
list, a calendar of releases and an action."""

from __future__ import annotations

from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker

from custom_components.feedrion.calendar import movie_event
from custom_components.feedrion.const import DOMAIN

from .conftest import HA, mock_api, state_payload


async def _setup(hass: HomeAssistant, entry: MockConfigEntry) -> None:
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()


async def test_movies_to_watch_and_upcoming(
    hass: HomeAssistant, entry: MockConfigEntry, aioclient_mock: AiohttpClientMocker,
) -> None:
    mock_api(aioclient_mock)
    await _setup(hass, entry)

    to_watch = hass.states.get("sensor.feedrion_movies_to_watch")
    assert to_watch.state == "1"
    assert to_watch.attributes["movies"][0]["name"] == "Northwind: The Film"
    assert to_watch.attributes["movies"][0]["backdrop_url"] == "https://artworks.example/film.jpg"
    nxt = hass.states.get("sensor.feedrion_next_movie_release")
    assert nxt.state.startswith("2027-03-1")  # local midnight of the release day
    assert nxt.attributes["name"] == "Orbit Nine" and nxt.attributes["upcoming_count"] == 1
    assert nxt.attributes["movies"][0]["movie_id"] == 22
    assert hass.states.get("todo.feedrion_movies_to_watch").state == "1"
    assert hass.states.get("calendar.feedrion_movie_releases") is not None


async def test_an_api_without_films_leaves_them_unavailable(
    hass: HomeAssistant, entry: MockConfigEntry, aioclient_mock: AiohttpClientMocker,
) -> None:
    state = state_payload()
    del state["movies"]
    mock_api(aioclient_mock, state=state)
    await _setup(hass, entry)
    assert hass.states.get("sensor.feedrion_movies_to_watch").state == "unavailable"
    assert hass.states.get("todo.feedrion_movies_to_watch").state == "unavailable"
    # Nothing was asked of routes such an API does not have.
    assert not any("/movies/" in str(c[1]) for c in aioclient_mock.mock_calls)


async def test_checking_a_film_off_marks_it_watched(
    hass: HomeAssistant, entry: MockConfigEntry, aioclient_mock: AiohttpClientMocker,
) -> None:
    mock_api(aioclient_mock)
    aioclient_mock.post(f"{HA}/movies/21/watched", status=204)
    aioclient_mock.post(f"{HA}/movies/22/watched", status=204)
    await _setup(hass, entry)
    await hass.services.async_call(
        "todo", "update_item", {"item": "21", "status": "completed"},
        target={"entity_id": "todo.feedrion_movies_to_watch"}, blocking=True,
    )
    assert any(str(c[1]).endswith("/movies/21/watched") for c in aioclient_mock.mock_calls)
    await hass.services.async_call(DOMAIN, "mark_movie_watched", {"movie_id": 22}, blocking=True)
    assert any(str(c[1]).endswith("/movies/22/watched") for c in aioclient_mock.mock_calls)


def test_a_release_is_an_all_day_event() -> None:
    ev = movie_event({"id": 9, "name": "Orbit Nine", "year": 2027, "release_date": "2027-03-12"})
    assert ev is not None and ev.summary == "Orbit Nine (2027)" and ev.uid == "feedrion-movie-9"
    assert str(ev.start) == "2027-03-12" and str(ev.end) == "2027-03-13"
    assert movie_event({"id": 1, "name": "No date"}) is None
