"""Pairing by code."""

from __future__ import annotations

import asyncio
from unittest.mock import patch

from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.test_util.aiohttp import (
    AiohttpClientMocker,
    AiohttpClientMockResponse,
)

from custom_components.feedrion.const import CONF_API_URL, CONF_REFRESH_TOKEN, DOMAIN

from .conftest import API

START = {"device_code": "d" * 32, "user_code": "ABCD-EFGH",
         "verification_url": "https://feedrion.example/settings/integrations/connect?code=ABCD-EFGH",
         "expires_in": 600, "interval": 2}


APPROVED = {"status": "approved", "kind": "homeassistant", "access_token": "a", "refresh_token": "r",
            "family_id": "fam"}
ME = {"kind": "homeassistant", "display_name": "Max", "language": "fr", "premium": True,
      "pricing_url": "https://feedrion.example/pricing"}


async def _run_until_done(hass: HomeAssistant, flow_id: str) -> None:
    """Wait for the progress task, then continue the flow as the frontend does
    when it receives SHOW_PROGRESS_DONE."""
    for _ in range(20):
        await hass.async_block_till_done()
        flows = [f for f in hass.config_entries.flow.async_progress() if f["flow_id"] == flow_id]
        if not flows:
            return
        if flows[0]["step_id"] != "wait":
            await hass.config_entries.flow.async_configure(flow_id)
    raise AssertionError("pairing never finished")


async def _show_code(hass: HomeAssistant) -> dict:
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    assert result["type"] is FlowResultType.FORM
    return await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_API_URL: API})


async def test_approved_while_away_finishes_on_submit(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker,
) -> None:
    """The reader leaves for the app, approves, comes back to a dialog that
    missed every event: the code form is still there and one submit ends it,
    without another poll."""
    aioclient_mock.post(f"{API}/integrations/v1/pair/start", json=START)
    aioclient_mock.post(f"{API}/integrations/v1/pair/poll", json=APPROVED)
    aioclient_mock.get(f"{API}/integrations/v1/me", json=ME)
    with patch("custom_components.feedrion.config_flow._pause", return_value=None), \
         patch("custom_components.feedrion.async_setup_entry", return_value=True):
        result = await _show_code(hass)
        assert result["type"] is FlowResultType.FORM
        assert result["step_id"] == "code"
        assert result["description_placeholders"]["code"] == "ABCD-EFGH"
        await hass.async_block_till_done()  # polling ran in the background
        polls = sum(1 for c in aioclient_mock.mock_calls if str(c[1]).endswith("/pair/poll"))
        result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert sum(1 for c in aioclient_mock.mock_calls if str(c[1]).endswith("/pair/poll")) == polls
    entries = hass.config_entries.async_entries(DOMAIN)
    assert len(entries) == 1
    assert entries[0].title == "Feedrion (Max)"
    assert entries[0].data[CONF_REFRESH_TOKEN] == "r"
    start = next(c for c in aioclient_mock.mock_calls if str(c[1]).endswith("/pair/start"))
    assert start[2]["kind"] == "homeassistant"


async def test_submitted_before_approval_waits_then_finishes(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker,
) -> None:
    aioclient_mock.post(f"{API}/integrations/v1/pair/start", json=START)
    aioclient_mock.post(f"{API}/integrations/v1/pair/poll", json=APPROVED)
    aioclient_mock.get(f"{API}/integrations/v1/me", json=ME)
    approved = asyncio.Event()

    async def wait_for_the_reader(_seconds: float) -> None:
        await approved.wait()

    with patch("custom_components.feedrion.config_flow._pause", side_effect=wait_for_the_reader), \
         patch("custom_components.feedrion.async_setup_entry", return_value=True):
        result = await _show_code(hass)
        result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
        assert result["type"] is FlowResultType.SHOW_PROGRESS
        assert result["step_id"] == "wait"
        assert hass.config_entries.async_entries(DOMAIN) == []
        approved.set()
        await _run_until_done(hass, result["flow_id"])
    assert len(hass.config_entries.async_entries(DOMAIN)) == 1


async def test_http_is_refused(hass: HomeAssistant) -> None:
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_API_URL: "http://x.example/api"})
    assert result["errors"] == {CONF_API_URL: "https_required"}


async def test_expired_code(hass: HomeAssistant, aioclient_mock: AiohttpClientMocker) -> None:
    aioclient_mock.post(f"{API}/integrations/v1/pair/start", json=START)
    aioclient_mock.post(f"{API}/integrations/v1/pair/poll", status=410, json={"detail": "expired"})
    with patch("custom_components.feedrion.config_flow._pause", return_value=None):
        result = await _show_code(hass)
        await hass.async_block_till_done()
        result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "expired"
    assert hass.config_entries.async_entries(DOMAIN) == []


async def test_a_lasting_refusal_stops_instead_of_waiting_in_silence(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, caplog,
) -> None:
    aioclient_mock.post(f"{API}/integrations/v1/pair/start", json=START)
    aioclient_mock.post(f"{API}/integrations/v1/pair/poll", status=403, json={"detail": "forbidden"})
    with patch("custom_components.feedrion.config_flow._pause", return_value=None):
        result = await _show_code(hass)
        await hass.async_block_till_done()
        result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "pairing_failed"
    assert sum(1 for c in aioclient_mock.mock_calls if str(c[1]).endswith("/pair/poll")) == 1
    assert "403" in caplog.text


async def test_an_unreachable_api_is_retried(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker,
) -> None:
    aioclient_mock.post(f"{API}/integrations/v1/pair/start", json=START)
    answers = iter([(503, {"detail": "down"}), (429, {"detail": "slow"}), (200, APPROVED)])

    async def poll(method, url, data):
        status, body = next(answers)
        return AiohttpClientMockResponse(method, url, status=status, json=body)

    aioclient_mock.post(f"{API}/integrations/v1/pair/poll", side_effect=poll)
    aioclient_mock.get(f"{API}/integrations/v1/me", json=ME)
    with patch("custom_components.feedrion.config_flow._pause", return_value=None), \
         patch("custom_components.feedrion.async_setup_entry", return_value=True):
        result = await _show_code(hass)
        await hass.async_block_till_done()
        result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    assert result["type"] is FlowResultType.CREATE_ENTRY
