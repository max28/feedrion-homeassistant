"""Setup, entities, Premium, token rotation, events and actions."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.helpers import issue_registry as ir
from pytest_homeassistant_custom_component.common import MockConfigEntry, async_capture_events
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker

from custom_components.feedrion.const import CONF_REFRESH_TOKEN, DOMAIN

from .conftest import API, ARTICLE, HA, mock_api


async def _setup(hass: HomeAssistant, entry: MockConfigEntry) -> None:
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()


async def test_entities(hass: HomeAssistant, entry: MockConfigEntry, aioclient_mock: AiohttpClientMocker) -> None:
    mock_api(aioclient_mock)
    await _setup(hass, entry)
    assert entry.state is ConfigEntryState.LOADED

    assert hass.states.get("sensor.feedrion_unread_articles").state == "42"
    assert hass.states.get("sensor.feedrion_tech_unread").state == "30"
    assert hass.states.get("sensor.feedrion_daily_horizon_unread").state == "12"
    assert hass.states.get("sensor.feedrion_episodes_to_watch").state == "4"
    latest = hass.states.get("sensor.feedrion_latest_articles")
    assert latest.state == "1"
    assert latest.attributes["articles"][0]["title"] == "Hello"
    assert hass.states.get("sensor.feedrion_next_episode").state == "2026-10-29T01:00:00+00:00"
    ai = hass.states.get("sensor.feedrion_ai_articles_this_month")
    assert ai.state == "120" and ai.attributes["quota"] == 1200
    assert hass.states.get("sensor.feedrion_euro_dollar").state == "1.08"

    weather = hass.states.get("weather.feedrion_orleans")
    assert weather.state == "partlycloudy"
    assert weather.attributes["attribution"].startswith("Données météo : MET Norway")

    assert hass.states.get("todo.feedrion_to_watch").state == "1"
    assert hass.states.get("todo.feedrion_saved").state == "1"
    assert hass.states.get("calendar.feedrion_upcoming_episodes") is not None

    # « Mes actions » is never quoted without the reader's own key.
    assert hass.states.get("sensor.feedrion_apple") is None
    assert not any("twelvedata" in str(call[1]) for call in aioclient_mock.mock_calls)


async def test_only_selected_feeds_are_asked_for(
    hass: HomeAssistant, entry: MockConfigEntry, aioclient_mock: AiohttpClientMocker,
) -> None:
    mock_api(aioclient_mock)
    await _setup(hass, entry)
    state_calls = [c for c in aioclient_mock.mock_calls if str(c[1]).startswith(f"{HA}/state")]
    assert state_calls and "feeds=11" in str(state_calls[0][1])


async def test_premium_required_raises_an_issue(
    hass: HomeAssistant, entry: MockConfigEntry, aioclient_mock: AiohttpClientMocker,
) -> None:
    mock_api(aioclient_mock, status=402)
    assert not await hass.config_entries.async_setup(entry.entry_id)
    assert entry.state is ConfigEntryState.SETUP_RETRY
    registry = ir.async_get(hass)
    assert registry.async_get_issue(DOMAIN, f"premium_required_{entry.entry_id}") is not None


async def test_a_rotated_refresh_token_is_stored(
    hass: HomeAssistant, entry: MockConfigEntry, aioclient_mock: AiohttpClientMocker,
) -> None:
    calls = {"n": 0}

    async def state(method, url, data):
        from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMockResponse
        from .conftest import state_payload
        calls["n"] += 1
        if calls["n"] == 1:
            return AiohttpClientMockResponse(method, url, status=401, json={"detail": "expired"})
        return AiohttpClientMockResponse(method, url, json=state_payload())

    aioclient_mock.get(f"{HA}/state", side_effect=state)
    aioclient_mock.post(f"{API}/auth/refresh", json={"access_token": "access-2", "refresh_token": "refresh-2"})
    aioclient_mock.get(f"{HA}/articles", json=[ARTICLE])
    aioclient_mock.get(f"{HA}/tv/to-watch", json=[])
    aioclient_mock.get(f"{HA}/tv/upcoming", json=[])
    aioclient_mock.get(f"{HA}/events", json={"cursor": "a1|m1", "events": []})
    await _setup(hass, entry)
    assert entry.state is ConfigEntryState.LOADED
    assert entry.data[CONF_REFRESH_TOKEN] == "refresh-2"


async def test_a_revoked_session_asks_to_pair_again(
    hass: HomeAssistant, entry: MockConfigEntry, aioclient_mock: AiohttpClientMocker,
) -> None:
    aioclient_mock.get(f"{HA}/state", status=401, json={"detail": "expired"})
    aioclient_mock.post(f"{API}/auth/refresh", status=401, json={"detail": "Invalid refresh token"})
    assert not await hass.config_entries.async_setup(entry.entry_id)
    assert entry.state is ConfigEntryState.SETUP_ERROR
    flows = hass.config_entries.flow.async_progress()
    assert any(f["context"]["source"] == "reauth" for f in flows)


async def test_events_fire_after_the_first_cursor(
    hass: HomeAssistant, entry: MockConfigEntry, aioclient_mock: AiohttpClientMocker,
) -> None:
    mock_api(aioclient_mock)
    await _setup(hass, entry)
    events = async_capture_events(hass, "feedrion_new_article")
    alerts = async_capture_events(hass, "feedrion_alert")
    runtime = entry.runtime_data
    assert runtime.events.cursor == "a1|m1"  # learnt, nothing fired

    aioclient_mock.clear_requests()
    aioclient_mock.get(f"{HA}/events", json={"cursor": "a2|m2", "events": [
        {"type": "new_article", "article": ARTICLE},
        {"type": "alert", "article": {**ARTICLE, "masked": True, "title": "Masked"}, "keyword": "finale"},
    ]})
    await runtime.events.poll()
    await hass.async_block_till_done()
    assert [e.data["title"] for e in events] == ["Hello"]
    assert alerts[0].data["keyword"] == "finale" and alerts[0].data["masked"] is True
    # The poll carried the cursor the first call learnt.
    assert aioclient_mock.mock_calls[0][1].query["cursor"] == "a1|m1"


async def test_actions(hass: HomeAssistant, entry: MockConfigEntry, aioclient_mock: AiohttpClientMocker) -> None:
    mock_api(aioclient_mock)
    aioclient_mock.post(f"{HA}/articles/read", status=204)
    aioclient_mock.post(f"{HA}/tv/episodes/800/watched", status=204)
    aioclient_mock.get(f"{HA}/briefing", json={"text": "Daily Horizon : Hello.", "items": [ARTICLE]})
    aioclient_mock.delete(f"{HA}/saved/101", status=204)
    await _setup(hass, entry)

    await hass.services.async_call(DOMAIN, "mark_read", {"article_ids": [101]}, blocking=True)
    read = [c for c in aioclient_mock.mock_calls if str(c[1]).endswith("/articles/read")]
    assert read and read[0][2] == {"article_ids": [101]}

    response = await hass.services.async_call(DOMAIN, "briefing", {"limit": 3}, blocking=True, return_response=True)
    assert response["text"] == "Daily Horizon : Hello."

    # Checking off « À voir » is the app's own « vu ».
    await hass.services.async_call(
        "todo", "update_item", {"item": "800", "status": "completed"},
        target={"entity_id": "todo.feedrion_to_watch"}, blocking=True,
    )
    assert any(str(c[1]).endswith("/tv/episodes/800/watched") for c in aioclient_mock.mock_calls)

    await hass.services.async_call(
        "todo", "update_item", {"item": "101", "status": "completed"},
        target={"entity_id": "todo.feedrion_saved"}, blocking=True,
    )
    assert any(c[0] == "DELETE" and str(c[1]).endswith("/saved/101") for c in aioclient_mock.mock_calls)


async def test_unload(hass: HomeAssistant, entry: MockConfigEntry, aioclient_mock: AiohttpClientMocker) -> None:
    mock_api(aioclient_mock)
    await _setup(hass, entry)
    assert await hass.config_entries.async_unload(entry.entry_id)
    assert entry.state is ConfigEntryState.NOT_LOADED
