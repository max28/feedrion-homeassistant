"""The dashboard cards: served by the integration, loaded in every browser."""

from __future__ import annotations

import json
from pathlib import Path
import re
from unittest.mock import AsyncMock, MagicMock

from homeassistant.components.frontend import DATA_EXTRA_MODULE_URL, UrlManager
from homeassistant.core import HomeAssistant

from custom_components.feedrion import CARDS_FILE, CARDS_URL, _async_register_cards

ROOT = Path(__file__).resolve().parent.parent


async def test_the_cards_are_served_and_loaded(hass: HomeAssistant) -> None:
    hass.config.components.add("frontend")
    hass.http = MagicMock(async_register_static_paths=AsyncMock())
    hass.data[DATA_EXTRA_MODULE_URL] = UrlManager(lambda *_: None, [])

    await _async_register_cards(hass)

    (config,) = hass.http.async_register_static_paths.call_args.args[0]
    assert config.url_path == CARDS_URL and Path(config.path) == CARDS_FILE and CARDS_FILE.is_file()
    version = json.loads((CARDS_FILE.parent.parent / "manifest.json").read_text())["version"]
    assert hass.data[DATA_EXTRA_MODULE_URL].urls == {f"{CARDS_URL}?v={version}"}


async def test_without_a_frontend_nothing_is_registered(hass: HomeAssistant) -> None:
    hass.http = MagicMock(async_register_static_paths=AsyncMock())
    await _async_register_cards(hass)
    hass.http.async_register_static_paths.assert_not_called()


def test_the_readme_documents_every_card() -> None:
    source = CARDS_FILE.read_text(encoding="utf-8")
    tags = re.findall(r'\["(feedrion-[a-z-]+-card)"', source)
    assert len(tags) == 5
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    for tag in tags:
        assert f"custom:{tag}" in readme, tag


def test_the_package_ships_the_cards() -> None:
    # scripts/package.py zips the whole integration folder: the card must live in it.
    assert CARDS_FILE.is_relative_to(ROOT / "custom_components" / "feedrion")
