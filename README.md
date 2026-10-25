# Feedrion for Home Assistant

A [Home Assistant](https://www.home-assistant.io) integration for
[Feedrion](https://feedrion.com): your feeds, your TV shows, your cities'
weather, your currencies and « Mes actions », as entities, events and actions.

**Requires Feedrion Premium.** A connected account that is not Premium shows a
repair notice and its sensors go unavailable until it is.

## What you get

| Entity | What it shows |
|--------|---------------|
| `sensor.feedrion_unread_articles`, `…_saved_articles`, `…_starred_articles`, `…_unseen_alerts` | Counters |
| `sensor.feedrion_<folder>_unread` | One per folder |
| `sensor.feedrion_<feed>_unread` | One per feed you pick in the options (50 at most) |
| `sensor.feedrion_latest_articles` | The newest unread articles (titles, links, images) in its attributes |
| `sensor.feedrion_episodes_to_watch`, `sensor.feedrion_next_episode` | Séries extension |
| `calendar.feedrion_upcoming_episodes` | Announced episodes (timed when the broadcast hour is known) |
| `todo.feedrion_saved`, `todo.feedrion_to_watch` | Check an article off = read and out of « Saved »; check an episode off = watched (reaches Trakt and Simkl too). Add a link to « Saved » by typing it. |
| `weather.feedrion_<city>` | Each city of the Météo extension, with daily and hourly forecasts (MET Norway, CC BY 4.0) |
| `sensor.feedrion_<pair>` | Each currency pair of the Bourse extension |
| `sensor.feedrion_<stock>` | « Mes actions », **quoted by Home Assistant itself with your own key** (see below) |
| `sensor.feedrion_ai_articles_this_month` | AI option usage |

### Events

- `feedrion_new_article` — a new article in one of the feeds you picked.
- `feedrion_alert` — a keyword alert matched (`keyword` in the data).

Both carry `article_id`, `feed_id`, `feed`, `title`, `masked`, `url`,
`image_url`, `published_at`. A title masked by anti-spoil stays masked.
Connecting or restarting never fires a backlog.

### Actions

`feedrion.mark_read`, `feedrion.mark_all_read`, `feedrion.save_url`,
`feedrion.mark_episode_watched`, and `feedrion.briefing`, which returns the
newest unread headlines as one text — ready for `tts.speak`:

```yaml
- action: feedrion.briefing
  data: { limit: 5 }
  response_variable: briefing
- action: tts.speak
  target: { entity_id: tts.home_assistant_cloud }
  data:
    media_player_entity_id: media_player.kitchen
    message: "{{ briefing.text }}"
```

## « Mes actions »

Feedrion never relays share prices: your free plan with the provider licenses
personal use, not redistribution. So the server only gives Home Assistant the
list of your symbols, and Home Assistant quotes them itself, straight from the
provider, with **your** key (Twelve Data, Alpha Vantage or EODHD — options of
the integration). The key stays in Home Assistant. At most half of the key's
daily allowance is spent here; your phone spends the rest.

## Install

1. HACS ▸ ⋮ ▸ Custom repositories ▸ `https://github.com/max28/feedrion-homeassistant`,
   category *Integration*. Install **Feedrion**, restart Home Assistant.
2. Settings ▸ Devices & services ▸ Add integration ▸ **Feedrion**.
3. A code appears. In the Feedrion app, open Settings ▸ Integrations ▸
   Connected devices and type it. The app shows what is asking before you
   approve. No password ever reaches Home Assistant.
4. Options: the feeds that get their own sensor and events, how many articles
   the « latest » sensor holds, and the « Mes actions » provider and key.

Removing the integration signs this Home Assistant out of Feedrion; the app can
also disconnect it (Home Assistant then asks to pair again).

## Privacy

Home Assistant calls Feedrion (https only) and, for « Mes actions » only, the
quote provider you chose. Feedrion never connects to your Home Assistant.

## Verify a download

```bash
cosign verify-blob feedrion.zip --bundle feedrion.zip.sigstore.json \
  --certificate-identity-regexp '^https://github.com/max28/feedrion-homeassistant/\.github/workflows/release\.yml@refs/heads/main$' \
  --certificate-oidc-issuer https://token.actions.githubusercontent.com
```

## Develop

```bash
python -m pip install -r requirements_test.txt ruff==0.14.0
ruff check custom_components tests scripts
python -m pytest -q
```

## License

[Apache-2.0](LICENSE). Feedrion is a trademark of its owner; this licence
covers the code in this repository, not the Feedrion service or its name.
