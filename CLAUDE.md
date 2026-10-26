# Feedrion for Home Assistant — notes for Claude

This repository WILL BE PUBLIC, history included. Write every file, commit
message and comment as if it already were.

## Never commit
- Secrets: tokens, keys, `.env` values, real tokens in fixtures (fixtures use
  obviously fake strings and `feedrion.example`).
- Infrastructure details of the Feedrion service: server names or paths,
  private hosts, VPN details, runner names, monitoring hosts. The only
  Feedrion addresses here are `https://api.feedrion.com/api` and
  `https://feedrion.com`.
- Personal data, including the owner's e-mail address.
- Self-hosted runner labels in a workflow: CI reads `CI_RUNS_ON` (repository
  variable), defaulting to GitHub-hosted. See `docs/PUBLISHING.md`.

## Layout
`custom_components/feedrion/`: `api.py` (client, token rotation persisted to
the config entry), `config_flow.py` (device-code pairing, options),
`coordinator.py` (state every 5 min, events every 60 s, My stocks),
`stocks.py` (provider quotes with the reader's key), one file per platform,
`services.py`, `frontend/feedrion-cards.js` (the dashboard cards, one
dependency-free module served by `async_setup` and added with
`add_extra_js_url`). `scripts/screenshots/render.mjs` draws `docs/images/cards-<lang>.webp`
(README and feedrion.com) from invented data with the real card module; the
showcase copies them, so re-render after a visual change to the cards.
Tests in `tests/` with
`pytest-homeassistant-custom-component`; the cards' helpers in `tests/js/`
(`node --test`).

## Rules that must not drift
- **Premium as a whole**: a 402 raises the `premium_required` repair issue and
  fails the update; nothing is cached as if it were fresh.
- **A rotated refresh token is saved at once** (`async_update_entry`), and an
  update listener reloads ONLY on an options change — a token save must never
  reload the entry.
- **A revoked session starts reauth**, never a silent retry loop.
- **Events never replay a backlog**: the first `/events` call has no cursor and
  only learns where to start.
- **Share prices never come from Feedrion.** Quotes are fetched here with the
  reader's own key, at most half of the free daily allowance, never below the
  free plan's floor. The key is sent to that provider only.
- **Masked stays masked**: anti-spoil titles reach sensors, events and the
  briefing already masked; never "unmask" anything locally.
- **Cards read entities, never Feedrion**: what they draw must already be in
  a state or an attribute (big lists are `_unrecorded_attributes`). Entity text
  goes through `textContent`, links through `safeUrl` (http(s) only). They
  show the TheTVDB and MET Norway attributions.
- **https only** for the API address.
- The API contract lives in the Feedrion API (`/integrations/v1/*`): additive
  changes only; tolerate unknown fields.

## Before pushing
`ruff check custom_components tests scripts`, `python -m pytest -q` and
`node --test tests/js/*.test.cjs`.
