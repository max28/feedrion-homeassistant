"""Pairing by code."""

from __future__ import annotations

import asyncio
from unittest.mock import patch

from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker

from custom_components.feedrion.const import CONF_API_URL, CONF_REFRESH_TOKEN, DOMAIN

from .conftest import API

START = {"device_code": "d" * 32, "user_code": "ABCD-EFGH",
         "verification_url": "https://feedrion.example/settings/integrations/connect?code=ABCD-EFGH",
         "expires_in": 600, "interval": 2}


async def _run_until_done(hass: HomeAssistant, flow_id: str) -> None:
    """Wait for the progress task, then continue the flow as the frontend does
    when it receives SHOW_PROGRESS_DONE."""
    for _ in range(20):
        await hass.async_block_till_done()
        flows = [f for f in hass.config_entries.flow.async_progress() if f["flow_id"] == flow_id]
        if not flows:
            return
        if flows[0]["step_id"] != "pair":
            await hass.config_entries.flow.async_configure(flow_id)
    raise AssertionError("pairing never finished")


async def test_pairing(hass: HomeAssistant, aioclient_mock: AiohttpClientMocker) -> None:
    aioclient_mock.post(f"{API}/integrations/v1/pair/start", json=START)
    aioclient_mock.post(f"{API}/integrations/v1/pair/poll", json={
        "status": "approved", "kind": "homeassistant", "access_token": "a", "refresh_token": "r",
        "family_id": "fam"})
    aioclient_mock.get(f"{API}/integrations/v1/me", json={
        "kind": "homeassistant", "display_name": "Max", "language": "fr", "premium": True,
        "pricing_url": "https://feedrion.example/pricing"})

    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    assert result["type"] is FlowResultType.FORM
    approved = asyncio.Event()

    async def wait_for_the_reader(_seconds: float) -> None:
        await approved.wait()

    with patch("custom_components.feedrion.config_flow._pause", side_effect=wait_for_the_reader), \
         patch("custom_components.feedrion.async_setup_entry", return_value=True):
        result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_API_URL: API})
        assert result["type"] is FlowResultType.SHOW_PROGRESS
        assert result["description_placeholders"]["code"] == "ABCD-EFGH"
        assert hass.config_entries.async_entries(DOMAIN) == []
        approved.set()
        await _run_until_done(hass, result["flow_id"])
    entries = hass.config_entries.async_entries(DOMAIN)
    assert len(entries) == 1
    assert entries[0].title == "Feedrion (Max)"
    assert entries[0].data[CONF_REFRESH_TOKEN] == "r"
    start = next(c for c in aioclient_mock.mock_calls if str(c[1]).endswith("/pair/start"))
    assert start[2]["kind"] == "homeassistant"


async def test_http_is_refused(hass: HomeAssistant) -> None:
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_API_URL: "http://x.example/api"})
    assert result["errors"] == {CONF_API_URL: "https_required"}


async def test_expired_code(hass: HomeAssistant, aioclient_mock: AiohttpClientMocker) -> None:
    aioclient_mock.post(f"{API}/integrations/v1/pair/start", json=START)
    aioclient_mock.post(f"{API}/integrations/v1/pair/poll", status=410, json={"detail": "expired"})
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    with patch("custom_components.feedrion.config_flow._pause", return_value=None):
        result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_API_URL: API})
        await _run_until_done(hass, result["flow_id"])
    assert hass.config_entries.async_entries(DOMAIN) == []
