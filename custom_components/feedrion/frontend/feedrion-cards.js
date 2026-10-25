/*
 * Feedrion cards for Home Assistant dashboards.
 *
 * Five cards drawn like the Feedrion phone widgets, reading only what the
 * integration's entities already hold — a card never calls Feedrion itself:
 *
 *   custom:feedrion-tv-card       « À voir » / « À venir » (Séries extension)
 *   custom:feedrion-weather-card  a city of the Météo extension, sky included
 *   custom:feedrion-markets-card  currency pairs and « Mes actions »
 *   custom:feedrion-articles-card the newest unread articles
 *   custom:feedrion-unread-card   one counter
 *
 * Served by the integration itself (no resource to add by hand). Every piece
 * of text coming from an entity is written with textContent, every link is
 * checked to be http(s): an article title is a publisher's text.
 */

// One closure: nothing leaks into the page's globals, however it is loaded.
(() => {
"use strict";

// ── Pure helpers (exported for tests at the bottom) ──────────────────────────

const STRINGS = {
  en: {
    to_watch: "Episodes to watch",
    upcoming: "Upcoming episodes",
    to_watch_empty: "Nothing left to watch",
    upcoming_empty: "Nothing announced",
    tv_disabled: "The Séries extension is off",
    remaining_one: "1 left",
    remaining_other: "{n} left",
    episodes_range: "Episodes {a} to {b}",
    today: "Today",
    tomorrow: "Tomorrow",
    watched: "Watched",
    watched_confirm: "Watched?",
    tvdb: "Data: TheTVDB",
    articles: "Unread",
    articles_empty: "All caught up",
    masked: "Anti-spoil",
    markets: "Markets",
    markets_empty: "No currency or share followed",
    no_quote: "No quote yet",
    last_close: "Last price {d}",
    unread: "Unread articles",
    unavailable: "Unavailable",
    not_found: "Entity not found: {e}",
    max: "max",
    min: "min",
  },
  fr: {
    to_watch: "Épisodes à voir",
    upcoming: "Épisodes à venir",
    to_watch_empty: "Plus rien à voir",
    upcoming_empty: "Aucun épisode annoncé",
    tv_disabled: "L'extension Séries est désactivée",
    remaining_one: "1 restant",
    remaining_other: "{n} restants",
    episodes_range: "Épisodes {a} à {b}",
    today: "Aujourd'hui",
    tomorrow: "Demain",
    watched: "Vu",
    watched_confirm: "Vu ?",
    tvdb: "Données : TheTVDB",
    articles: "Non lus",
    articles_empty: "Tout est lu",
    masked: "Anti-spoil",
    markets: "Bourse & devises",
    markets_empty: "Aucune devise ni action suivie",
    no_quote: "Pas encore de cours",
    last_close: "Dernier cours du {d}",
    unread: "Articles non lus",
    unavailable: "Indisponible",
    not_found: "Entité introuvable : {e}",
    max: "max",
    min: "min",
  },
};

function lang(hass) {
  const l = (hass && ((hass.locale && hass.locale.language) || hass.language)) || "en";
  return String(l).toLowerCase().split("-")[0];
}

function t(hass, key, vars) {
  const table = STRINGS[lang(hass)] || STRINGS.en;
  let s = table[key] !== undefined ? table[key] : STRINGS.en[key] !== undefined ? STRINGS.en[key] : key;
  for (const [k, v] of Object.entries(vars || {})) s = s.replace(`{${k}}`, String(v));
  return s;
}

/** Only http(s) leaves a card: a publisher's link is not trusted. */
function safeUrl(value) {
  if (typeof value !== "string") return null;
  try {
    const u = new URL(value);
    return u.protocol === "https:" || u.protocol === "http:" ? u.href : null;
  } catch (_e) {
    return null;
  }
}

function pad2(n) {
  return String(n).padStart(2, "0");
}

/** « S01E05 », « S02 · Épisodes 3 à 5 » for a grouped row. */
function episodeCode(e) {
  const s = `S${pad2(Number(e.season) || 0)}`;
  if (e.number_to && e.number_to !== e.number) return s;
  return `${s}E${pad2(Number(e.number) || 0)}`;
}

/**
 * When an episode airs, as a Date: its instant when the broadcast hour is
 * known, otherwise its DAY read at local midnight — a broadcast date is the
 * channel's day, and reading it in UTC would show the day before west of
 * Greenwich.
 */
function airDate(e) {
  if (e && e.aired_at) {
    const d = new Date(e.aired_at);
    if (!Number.isNaN(d.getTime())) return { date: d, timed: true };
  }
  if (e && typeof e.aired === "string") {
    const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(e.aired);
    if (m) return { date: new Date(Number(m[1]), Number(m[2]) - 1, Number(m[3])), timed: false };
  }
  return null;
}

function dayKey(d) {
  return `${d.getFullYear()}-${pad2(d.getMonth() + 1)}-${pad2(d.getDate())}`;
}

/**
 * « À venir » groups the episodes of one show airing the same day into one
 * row (« Épisodes 3 à 5 »), like the app's tab and the phone widget.
 */
function groupUpcoming(episodes) {
  const out = [];
  for (const e of episodes || []) {
    const air = airDate(e);
    const key = air ? dayKey(air.date) : "";
    const last = out[out.length - 1];
    if (last && last.show_id === e.show_id && last._day === key && last.season === e.season && key) {
      last.number_to = e.number;
      last.count += 1;
      last.name = null;
      continue;
    }
    out.push({ ...e, _day: key, number_to: e.number, count: 1 });
  }
  return out;
}

/** « Aujourd'hui 21:00 », « Demain », « mar. 28 oct. ». */
function airLabel(hass, e, now) {
  const air = airDate(e);
  if (!air) return "";
  const locale = lang(hass);
  const ref = now || new Date();
  const today = new Date(ref.getFullYear(), ref.getMonth(), ref.getDate());
  const day = new Date(air.date.getFullYear(), air.date.getMonth(), air.date.getDate());
  const diff = Math.round((day - today) / 86400000);
  let label;
  if (diff === 0) label = t(hass, "today");
  else if (diff === 1) label = t(hass, "tomorrow");
  else {
    const opts = { weekday: "short", day: "numeric", month: "short" };
    if (day.getFullYear() !== today.getFullYear()) opts.year = "numeric";
    label = new Intl.DateTimeFormat(locale, opts).format(air.date);
  }
  if (air.timed) {
    label += ` ${new Intl.DateTimeFormat(locale, { hour: "2-digit", minute: "2-digit" }).format(air.date)}`;
  }
  return label;
}

/** The second line of a TV row: « S01E05 · Pilot » or « S02 · Épisodes 3 à 5 ». */
function episodeLine(hass, e) {
  if (e.number_to && e.number_to !== e.number) {
    return `${episodeCode(e)} · ${t(hass, "episodes_range", { a: e.number, b: e.number_to })}`;
  }
  const code = episodeCode(e);
  return e.name ? `${code} · ${e.name}` : code;
}

/**
 * The sky behind the weather card, the same families as the phone widget
 * (weatherWidgetSky). Night comes from the sun when Home Assistant knows it.
 */
const SKIES = {
  clear_day: ["#1259C3", "#2A7BE0", "#4D9BEA"],
  clear_night: ["#0B1533", "#1B2E5E", "#3A4F86"],
  partly_day: ["#2F5F9E", "#4C7DB8", "#7398C7"],
  partly_night: ["#141C33", "#2A3552", "#4A5675"],
  cloudy: ["#47515E", "#626C78", "#7E8792"],
  cloudy_night: ["#272C35", "#3C434F", "#565E6B"],
  fog: ["#59616B", "#737B85", "#8E959D"],
  rain: ["#24364F", "#3B5675", "#5B7898"],
  snow: ["#3F5D7D", "#5F7F9F", "#84A1BD"],
  thunder: ["#1E1430", "#3A2A5C", "#5B4682"],
};

function weatherSky(condition, night) {
  switch (condition) {
    case "sunny":
      return night ? "clear_night" : "clear_day";
    case "clear-night":
      return "clear_night";
    case "partlycloudy":
      return night ? "partly_night" : "partly_day";
    case "fog":
      return "fog";
    case "rainy":
    case "pouring":
    case "snowy-rainy":
    case "hail":
      return "rain";
    case "snowy":
      return "snow";
    case "lightning":
    case "lightning-rainy":
      return "thunder";
    default:
      return night ? "cloudy_night" : "cloudy";
  }
}

const WEATHER_ICONS = {
  "clear-night": "mdi:weather-night",
  cloudy: "mdi:weather-cloudy",
  exceptional: "mdi:alert-circle-outline",
  fog: "mdi:weather-fog",
  hail: "mdi:weather-hail",
  lightning: "mdi:weather-lightning",
  "lightning-rainy": "mdi:weather-lightning-rainy",
  partlycloudy: "mdi:weather-partly-cloudy",
  pouring: "mdi:weather-pouring",
  rainy: "mdi:weather-rainy",
  snowy: "mdi:weather-snowy",
  "snowy-rainy": "mdi:weather-snowy-rainy",
  sunny: "mdi:weather-sunny",
  windy: "mdi:weather-windy",
  "windy-variant": "mdi:weather-windy-variant",
};

function weatherIcon(condition, night) {
  if (night && condition === "partlycloudy") return "mdi:weather-night-partly-cloudy";
  if (night && condition === "sunny") return "mdi:weather-night";
  return WEATHER_ICONS[condition] || "mdi:weather-cloudy";
}

function deg(value) {
  return typeof value === "number" && Number.isFinite(value) ? `${Math.round(value)}°` : "–";
}

function formatNumber(hass, value, digits) {
  if (typeof value !== "number" || !Number.isFinite(value)) return "–";
  const opts = digits === undefined
    ? { maximumFractionDigits: Math.abs(value) < 10 ? 4 : 2 }
    : { minimumFractionDigits: digits, maximumFractionDigits: digits };
  return new Intl.NumberFormat(lang(hass), opts).format(value);
}

function changeLabel(hass, pct) {
  if (typeof pct !== "number" || !Number.isFinite(pct)) return null;
  const sign = pct > 0 ? "+" : pct < 0 ? "−" : "";
  return `${sign}${formatNumber(hass, Math.abs(pct), 2)} %`;
}

function timeAgo(hass, iso, now) {
  if (!iso) return "";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  const seconds = Math.round(((now || new Date()) - d) / 1000);
  const rtf = new Intl.RelativeTimeFormat(lang(hass), { numeric: "auto", style: "short" });
  if (seconds < 3600) return rtf.format(-Math.max(1, Math.round(seconds / 60)), "minute");
  if (seconds < 86400) return rtf.format(-Math.round(seconds / 3600), "hour");
  return rtf.format(-Math.round(seconds / 86400), "day");
}

/**
 * The integration's entity for a role, found by its translation key in the
 * entity registry (so a renamed entity still works), else by its default id.
 */
function findEntity(hass, translationKey, fallbackId) {
  const entities = (hass && hass.entities) || {};
  for (const entry of Object.values(entities)) {
    if (entry.platform === "feedrion" && entry.translation_key === translationKey) return entry.entity_id;
  }
  return fallbackId;
}

function feedrionEntities(hass, predicate) {
  const out = [];
  const registry = (hass && hass.entities) || {};
  for (const [id, state] of Object.entries((hass && hass.states) || {})) {
    const entry = registry[id];
    if (entry && entry.platform !== "feedrion") continue;
    if (!entry && !id.includes("feedrion")) continue;
    if (predicate(id, state)) out.push(id);
  }
  return out.sort();
}

// ── DOM helpers ──────────────────────────────────────────────────────────────

function h(tag, attrs, ...children) {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v === undefined || v === null || v === false) continue;
    if (k === "class") el.className = v;
    else if (k === "style") el.setAttribute("style", v);
    else if (k.startsWith("on") && typeof v === "function") el.addEventListener(k.slice(2), v);
    else if (k in el && typeof v !== "string") el[k] = v;
    else el.setAttribute(k, v === true ? "" : String(v));
  }
  for (const c of children.flat()) {
    if (c === null || c === undefined || c === false) continue;
    el.append(c instanceof Node ? c : document.createTextNode(String(c)));
  }
  return el;
}

function img(src, cls) {
  const url = safeUrl(src);
  if (!url) return null;
  const el = h("img", { class: cls, src: url, alt: "", loading: "lazy", referrerpolicy: "no-referrer" });
  el.addEventListener("error", () => el.remove());
  return el;
}

function openUrl(url) {
  const safe = safeUrl(url);
  if (safe) window.open(safe, "_blank", "noopener,noreferrer");
}

function moreInfo(node, entityId) {
  node.dispatchEvent(new CustomEvent("hass-more-info", { bubbles: true, composed: true, detail: { entityId } }));
}

const LOGO = `<svg viewBox="0 0 1000 1000" aria-hidden="true"><circle cx="500" cy="500" r="480" fill="#0c365b"/><g fill="#fff"><path d="M215 265h160v70h-90v70h90v70h-90v110h-70z"/><circle cx="405" cy="645" r="90"/><path d="M405 475v-70a240 240 0 0 1 240 240h-70a170 170 0 0 0-170-170z"/><path d="M405 335v-70a380 380 0 0 1 380 380h-70a310 310 0 0 0-310-310z"/></g></svg>`;

const BASE_CSS = `
  :host { display: block; }
  ha-card { overflow: hidden; padding: 12px; box-sizing: border-box; height: 100%; color: var(--primary-text-color); }
  .head { display: flex; align-items: center; gap: 6px; padding-bottom: 8px; }
  .logo { width: 22px; height: 22px; flex: none; }
  .logo svg { width: 100%; height: 100%; display: block; }
  .title { flex: 1; min-width: 0; font-size: 15px; font-weight: 700; color: var(--primary-color);
           white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .empty { padding: 18px 4px; text-align: center; color: var(--secondary-text-color); font-size: 13px; }
  .foot { padding-top: 4px; text-align: right; font-size: 10.5px; color: var(--secondary-text-color); }
  .clickable { cursor: pointer; }
  .warn { padding: 12px; color: var(--error-color, #D63A2F); font-size: 13px; }
`;

// Outside a browser (the helpers' unit tests) there is no HTMLElement.
const Element_ = typeof HTMLElement !== "undefined" ? HTMLElement : class {};

class FeedrionBaseCard extends Element_ {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._config = {};
    this._hass = null;
    this._signature = null;
  }

  setConfig(config) {
    this._config = { ...(config || {}) };
    this._signature = null;
    this._render();
  }

  set hass(hass) {
    this._hass = hass;
    const sig = this._watched().map((id) => hass && hass.states[id]).concat([lang(hass)]);
    if (this._signature && sig.length === this._signature.length && sig.every((s, i) => s === this._signature[i])) {
      return;
    }
    this._signature = sig;
    this._render();
  }

  get hass() {
    return this._hass;
  }

  /** The entity ids whose change re-renders the card. */
  _watched() {
    return [];
  }

  _render() {
    if (!this._hass) return;
    const card = h("ha-card", {});
    const style = h("style", {}, BASE_CSS + this._css());
    try {
      this._build(card);
    } catch (err) {
      card.replaceChildren(h("div", { class: "warn" }, String(err && err.message ? err.message : err)));
    }
    this.shadowRoot.replaceChildren(style, card);
  }

  _css() {
    return "";
  }

  _head(title, icon) {
    const logo = h("span", { class: "logo" });
    if (icon) logo.append(h("ha-icon", { icon }));
    else logo.innerHTML = LOGO; // constant markup, no entity data
    return h("div", { class: "head" }, logo, h("span", { class: "title" }, title));
  }

  _state(id) {
    return id && this._hass ? this._hass.states[id] : undefined;
  }

  getCardSize() {
    return 3;
  }
}

// ── « À voir » / « À venir » ─────────────────────────────────────────────────

const TV_CSS = `
  .rows { display: flex; flex-direction: column; gap: 6px; }
  .row { position: relative; height: 72px; border-radius: 16px; overflow: hidden; background: #23252B;
         flex: none; }
  .row .bg { position: absolute; inset: 0; width: 100%; height: 100%; object-fit: cover; }
  .row .bg.blur { filter: blur(14px) saturate(1.2); transform: scale(1.3); }
  .row .scrim { position: absolute; inset: 0;
         background: linear-gradient(90deg, rgba(16,17,20,.9) 0%, rgba(16,17,20,.6) 50%, rgba(16,17,20,.2) 100%); }
  .row .fg { position: relative; height: 100%; display: flex; align-items: center; gap: 10px;
         padding: 0 10px 0 6px; box-sizing: border-box; }
  .row .poster { width: 40px; height: 60px; object-fit: cover; border-radius: 6px; flex: none; }
  .row .text { flex: 1; min-width: 0; margin-left: 4px; color: #fff; text-shadow: 0 0 3px rgba(0,0,0,.5); }
  .row .show { font-size: 14px; font-weight: 700; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .row .line { margin-top: 2px; font-size: 12px; color: rgba(255,255,255,.88); white-space: nowrap;
         overflow: hidden; text-overflow: ellipsis; }
  .pill { flex: none; max-width: 40%; padding: 3px 8px; border-radius: 10px; background: rgba(255,255,255,.2);
         color: #fff; font-size: 11.5px; font-weight: 700; text-align: center; }
  .seen { flex: none; border: 0; border-radius: 12px; padding: 4px 9px; cursor: pointer; font: inherit;
         font-size: 11.5px; font-weight: 700; color: #fff; background: rgba(31,138,91,.85); }
  .seen.armed { background: #1F8A5B; outline: 2px solid #fff; }
  .seen[disabled] { opacity: .6; cursor: default; }
`;

class FeedrionTvCard extends FeedrionBaseCard {
  static getStubConfig() {
    return { mode: "to_watch" };
  }

  static getConfigForm() {
    return {
      schema: [
        { name: "mode", required: true, selector: { select: { mode: "dropdown", options: [
          { value: "to_watch", label: "To watch / À voir" },
          { value: "upcoming", label: "Upcoming / À venir" },
        ] } } },
        { name: "title", selector: { text: {} } },
        { name: "max_items", selector: { number: { min: 1, max: 30, mode: "box" } } },
        { name: "show_set_aside", selector: { boolean: {} } },
        { name: "show_watched_button", selector: { boolean: {} } },
      ],
    };
  }

  setConfig(config) {
    if (config && config.mode && !["to_watch", "upcoming"].includes(config.mode)) {
      throw new Error("mode must be to_watch or upcoming");
    }
    super.setConfig({ mode: "to_watch", ...config });
  }

  get _mode() {
    return this._config.mode === "upcoming" ? "upcoming" : "to_watch";
  }

  get _entity() {
    if (this._config.entity) return this._config.entity;
    return this._mode === "upcoming"
      ? findEntity(this._hass, "next_episode", "sensor.feedrion_next_episode")
      : findEntity(this._hass, "episodes_to_watch", "sensor.feedrion_episodes_to_watch");
  }

  _watched() {
    return [this._entity];
  }

  _css() {
    return TV_CSS;
  }

  _items(st) {
    const attrs = (st && st.attributes) || {};
    if (this._mode === "upcoming") {
      const list = Array.isArray(attrs.upcoming) ? attrs.upcoming : attrs.show ? [attrs] : [];
      return { all: list.length, rows: groupUpcoming(list) };
    }
    let list = Array.isArray(attrs.next) ? attrs.next : [];
    if (!this._config.show_set_aside) list = list.filter((e) => !e.set_aside);
    const count = Number(st && st.state);
    return { all: Number.isFinite(count) ? count : list.length, rows: list };
  }

  _build(card) {
    const id = this._entity;
    const st = this._state(id);
    const key = this._mode;
    const { all, rows } = this._items(st);
    const title = this._config.title || `${t(this._hass, key)}${st && st.state !== "unavailable" ? ` (${all})` : ""}`;
    card.append(this._head(title));
    if (!st) {
      card.append(h("div", { class: "empty" }, t(this._hass, "not_found", { e: id })));
      return;
    }
    if (st.state === "unavailable") {
      card.append(h("div", { class: "empty" }, t(this._hass, "tv_disabled")));
      return;
    }
    const max = Math.max(1, Number(this._config.max_items) || 6);
    const shown = rows.slice(0, max);
    if (!shown.length) {
      card.append(h("div", { class: "empty" }, t(this._hass, key === "upcoming" ? "upcoming_empty" : "to_watch_empty")));
    } else {
      card.append(h("div", { class: "rows" }, shown.map((e) => this._row(e))));
    }
    card.append(h("div", { class: "foot" }, t(this._hass, "tvdb")));
  }

  _row(e) {
    // The SHOW's artwork, never the episode's: it reveals nothing the name
    // does not. No background: the poster, blurred, like the phone widget.
    const bg = img(e.backdrop_url, "bg") || img(e.poster_url, "bg blur");
    const pill = this._mode === "upcoming"
      ? airLabel(this._hass, e)
      : Number(e.remaining) > 1
        ? t(this._hass, "remaining_other", { n: e.remaining })
        : t(this._hass, "remaining_one");
    const right = [];
    if (pill) right.push(h("span", { class: "pill" }, pill));
    if (this._mode === "to_watch" && this._config.show_watched_button && e.episode_id) {
      right.push(this._seenButton(e));
    }
    const link = e.show_id ? `https://feedrion.com/extensions/tv_shows/show/${encodeURIComponent(e.show_id)}` : null;
    return h(
      "div",
      { class: `row${link ? " clickable" : ""}`, onclick: link ? () => openUrl(link) : null },
      bg,
      h("div", { class: "scrim" }),
      h("div", { class: "fg" },
        img(e.poster_url, "poster"),
        h("div", { class: "text" },
          h("div", { class: "show" }, e.show || e.show_name || ""),
          h("div", { class: "line" }, episodeLine(this._hass, e))),
        right),
    );
  }

  /** Two taps: the first arms it, the second marks the episode watched —
   * a « vu » reaches Trakt and Simkl, one stray tap must not send it. */
  _seenButton(e) {
    const btn = h("button", { class: "seen", type: "button" }, t(this._hass, "watched"));
    let timer = null;
    btn.addEventListener("click", (ev) => {
      ev.stopPropagation();
      if (!btn.classList.contains("armed")) {
        btn.classList.add("armed");
        btn.textContent = t(this._hass, "watched_confirm");
        timer = setTimeout(() => {
          btn.classList.remove("armed");
          btn.textContent = t(this._hass, "watched");
        }, 3000);
        return;
      }
      clearTimeout(timer);
      btn.disabled = true;
      this._hass.callService("feedrion", "mark_episode_watched", { episode_id: Number(e.episode_id) })
        .catch(() => {
          btn.disabled = false;
          btn.classList.remove("armed");
          btn.textContent = t(this._hass, "watched");
        });
    });
    return btn;
  }

  getCardSize() {
    return 1 + Math.min(Number(this._config.max_items) || 6, 6);
  }

  getGridOptions() {
    return { columns: 12, min_columns: 6, rows: "auto" };
  }
}

// ── Météo ────────────────────────────────────────────────────────────────────

const WEATHER_CSS = `
  ha-card { padding: 0; color: #fff; border: 0; }
  .sky { padding: 14px 16px 12px; min-height: 100%; box-sizing: border-box; }
  .top { display: flex; align-items: flex-start; gap: 8px; }
  .city { flex: 1; min-width: 0; font-size: 15px; font-weight: 700; white-space: nowrap; overflow: hidden;
          text-overflow: ellipsis; text-shadow: 0 1px 2px rgba(0,0,0,.25); }
  .now { display: flex; align-items: center; gap: 10px; margin-top: 6px; }
  .now ha-icon { --mdc-icon-size: 44px; }
  .temp { font-size: 42px; font-weight: 300; line-height: 1; }
  .cond { font-size: 13px; opacity: .92; }
  .range { font-size: 13px; opacity: .92; margin-top: 2px; }
  .days { display: grid; grid-auto-flow: column; grid-auto-columns: 1fr; gap: 4px; margin-top: 12px;
          padding: 8px 4px; border-radius: 14px; background: rgba(255,255,255,.14); }
  .day { display: flex; flex-direction: column; align-items: center; gap: 2px; font-size: 12px; min-width: 0; }
  .day .name { opacity: .9; text-transform: capitalize; white-space: nowrap; }
  .day ha-icon { --mdc-icon-size: 24px; }
  .day .lo { opacity: .75; }
  .attr { margin-top: 8px; font-size: 10.5px; opacity: .75; text-align: right; }
`;

class FeedrionWeatherCard extends FeedrionBaseCard {
  static getStubConfig(hass) {
    const ids = feedrionEntities(hass, (id) => id.startsWith("weather."));
    return { entity: ids[0] || "weather.feedrion" };
  }

  static getConfigForm() {
    return {
      schema: [
        { name: "entity", required: true, selector: { entity: { filter: { integration: "feedrion", domain: "weather" } } } },
        { name: "forecast", selector: { select: { mode: "dropdown", options: [
          { value: "daily", label: "Days / Jours" },
          { value: "hourly", label: "Hours / Heures" },
          { value: "none", label: "None / Aucune" },
        ] } } },
        { name: "forecast_items", selector: { number: { min: 1, max: 8, mode: "box" } } },
      ],
    };
  }

  constructor() {
    super();
    this._forecast = null;
    this._unsub = null;
    this._subscribedTo = null;
  }

  setConfig(config) {
    if (!config || !config.entity) throw new Error("entity is required (a weather.feedrion_… entity)");
    super.setConfig({ forecast: "daily", ...config });
    this._resubscribe();
  }

  set hass(hass) {
    super.hass = hass;
    this._resubscribe();
  }

  get hass() {
    return this._hass;
  }

  connectedCallback() {
    this._resubscribe();
  }

  disconnectedCallback() {
    this._unsubscribe();
  }

  _watched() {
    return [this._config.entity, "sun.sun"];
  }

  _css() {
    return WEATHER_CSS;
  }

  _unsubscribe() {
    if (this._unsub) {
      const unsub = this._unsub;
      this._unsub = null;
      Promise.resolve(unsub).then((fn) => typeof fn === "function" && fn()).catch(() => {});
    }
    this._subscribedTo = null;
  }

  _resubscribe() {
    const type = this._config.forecast === "hourly" ? "hourly" : "daily";
    const wanted = this._config.forecast === "none" ? null : `${this._config.entity}|${type}`;
    if (!this.isConnected || !this._hass || !this._hass.connection || wanted === this._subscribedTo) return;
    this._unsubscribe();
    this._forecast = null;
    if (!wanted) return;
    this._subscribedTo = wanted;
    this._unsub = this._hass.connection.subscribeMessage(
      (msg) => {
        this._forecast = { type, items: (msg && msg.forecast) || [] };
        this._render();
      },
      { type: "weather/subscribe_forecast", forecast_type: type, entity_id: this._config.entity },
    ).catch(() => {
      this._subscribedTo = null;
      return null;
    });
  }

  _night(st) {
    if (st.state === "clear-night") return true;
    const sun = this._state("sun.sun");
    return sun ? sun.state === "below_horizon" : false;
  }

  _build(card) {
    const st = this._state(this._config.entity);
    if (!st) {
      card.style.color = "var(--primary-text-color)";
      card.style.padding = "12px";
      card.append(h("div", { class: "empty" }, t(this._hass, "not_found", { e: this._config.entity })));
      return;
    }
    const attrs = st.attributes || {};
    const night = this._night(st);
    const sky = SKIES[weatherSky(st.state, night)];
    const box = h("div", {
      class: "sky clickable",
      style: `background: linear-gradient(180deg, ${sky[0]} 0%, ${sky[1]} 50%, ${sky[2]} 100%)`,
      onclick: () => moreInfo(this, this._config.entity),
    });
    const daily = this._forecast && this._forecast.type === "daily" ? this._forecast.items : [];
    const today = daily[0];
    const condText = this._hass.localize
      ? this._hass.localize(`component.weather.entity_component._.state.${st.state}`) || st.state
      : st.state;
    box.append(
      h("div", { class: "top" }, h("div", { class: "city" }, attrs.friendly_name || this._config.entity)),
      h("div", { class: "now" },
        h("ha-icon", { icon: weatherIcon(st.state, night) }),
        h("div", {},
          h("div", { class: "temp" }, deg(attrs.temperature)),
          h("div", { class: "cond" }, st.state === "unavailable" ? t(this._hass, "unavailable") : condText),
          today ? h("div", { class: "range" }, `↑ ${deg(today.temperature)}  ↓ ${deg(today.templow)}`) : null)),
    );
    const items = this._forecast ? this._forecast.items : [];
    const n = Math.max(1, Math.min(8, Number(this._config.forecast_items) || 5));
    if (this._config.forecast !== "none" && items.length) {
      const locale = lang(this._hass);
      const hourly = this._forecast.type === "hourly";
      const fmt = new Intl.DateTimeFormat(locale, hourly ? { hour: "2-digit", minute: "2-digit" } : { weekday: "short" });
      const list = hourly ? items.slice(0, n) : items.slice(0, n);
      box.append(h("div", { class: "days" }, list.map((f, i) => h("div", { class: "day" },
        h("span", { class: "name" }, !hourly && i === 0 ? t(this._hass, "today") : fmt.format(new Date(f.datetime))),
        h("ha-icon", { icon: weatherIcon(f.condition, false) }),
        h("span", {}, deg(f.temperature)),
        !hourly ? h("span", { class: "lo" }, deg(f.templow)) : null))));
    }
    // MET Norway's licence (CC BY 4.0) asks for the attribution.
    if (attrs.attribution) box.append(h("div", { class: "attr" }, attrs.attribution));
    card.append(box);
  }

  getCardSize() {
    return this._config.forecast === "none" ? 2 : 4;
  }

  getGridOptions() {
    return { columns: 6, min_columns: 4, rows: "auto" };
  }
}

// ── Bourse & devises ─────────────────────────────────────────────────────────

const MARKETS_CSS = `
  .list { display: flex; flex-direction: column; }
  .item { display: flex; align-items: center; gap: 10px; padding: 8px 2px; }
  .item + .item { border-top: 1px solid var(--divider-color); }
  .names { flex: 1; min-width: 0; }
  .name { font-size: 14px; font-weight: 600; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .sub { font-size: 11.5px; color: var(--secondary-text-color); white-space: nowrap; overflow: hidden;
         text-overflow: ellipsis; }
  .price { text-align: right; font-size: 15px; font-weight: 600; white-space: nowrap; }
  .chg { display: inline-block; margin-top: 2px; padding: 1px 7px; border-radius: 9px; font-size: 11.5px;
         font-weight: 700; color: #fff; background: var(--secondary-text-color); }
  .chg.up { background: #1F8A5B; }
  .chg.down { background: #D63A2F; }
  .rotate .item { min-height: 52px; }
`;

class FeedrionMarketsCard extends FeedrionBaseCard {
  static getStubConfig() {
    return {};
  }

  static getConfigForm() {
    return {
      schema: [
        { name: "title", selector: { text: {} } },
        { name: "entities", selector: { entity: { multiple: true, filter: { integration: "feedrion", domain: "sensor" } } } },
        { name: "rotate", selector: { boolean: {} } },
      ],
    };
  }

  constructor() {
    super();
    this._index = 0;
    this._timer = null;
  }

  connectedCallback() {
    this._startRotation();
  }

  disconnectedCallback() {
    clearInterval(this._timer);
    this._timer = null;
  }

  setConfig(config) {
    super.setConfig(config);
    this._startRotation();
  }

  _startRotation() {
    clearInterval(this._timer);
    this._timer = null;
    if (!this._config.rotate || !this.isConnected) return;
    // The phone's « Bourse » row turns every 5 s.
    this._timer = setInterval(() => {
      this._index += 1;
      this._render();
    }, 5000);
  }

  get _ids() {
    const configured = this._config.entities;
    if (Array.isArray(configured) && configured.length) {
      return configured.map((e) => (typeof e === "string" ? e : e && e.entity)).filter(Boolean);
    }
    // Every Feedrion instrument: currency pairs carry `change_pct`, « Mes
    // actions » `provider` too.
    return feedrionEntities(this._hass, (id, st) => id.startsWith("sensor.") && st.attributes
      && "symbol" in st.attributes && "change_pct" in st.attributes);
  }

  _watched() {
    return this._ids;
  }

  _css() {
    return MARKETS_CSS;
  }

  _item(id) {
    const st = this._state(id);
    if (!st) return h("div", { class: "item" }, h("div", { class: "names" }, h("div", { class: "sub" }, t(this._hass, "not_found", { e: id }))));
    const a = st.attributes || {};
    const value = Number(st.state);
    const hasPrice = st.state !== "unknown" && st.state !== "unavailable" && Number.isFinite(value);
    const chg = changeLabel(this._hass, a.change_pct);
    let sub = [a.symbol, a.exchange].filter(Boolean).join(" · ");
    if (a.error) sub = String(a.error);
    else if (hasPrice && a.as_of) {
      const d = new Date(a.as_of);
      if (!Number.isNaN(d.getTime())) {
        sub = [sub, t(this._hass, "last_close", { d: new Intl.DateTimeFormat(lang(this._hass), { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" }).format(d) })].filter(Boolean).join(" · ");
      }
    }
    const unit = a.unit_of_measurement ? ` ${a.unit_of_measurement}` : "";
    return h("div", { class: "item clickable", onclick: () => moreInfo(this, id) },
      h("div", { class: "names" },
        h("div", { class: "name" }, a.friendly_name || id),
        sub ? h("div", { class: "sub" }, sub) : null),
      h("div", { class: "price" },
        hasPrice ? `${formatNumber(this._hass, value)}${unit}` : h("span", { class: "sub" }, t(this._hass, "no_quote")),
        chg ? h("div", {}, h("span", { class: `chg ${a.change_pct > 0 ? "up" : a.change_pct < 0 ? "down" : ""}` }, chg)) : null));
  }

  _build(card) {
    card.append(this._head(this._config.title || t(this._hass, "markets")));
    const ids = this._ids;
    if (!ids.length) {
      card.append(h("div", { class: "empty" }, t(this._hass, "markets_empty")));
      return;
    }
    if (this._config.rotate) {
      // Like the phone: only what has a price turns, unless nothing does.
      const priced = ids.filter((id) => {
        const st = this._state(id);
        return st && Number.isFinite(Number(st.state));
      });
      const pool = priced.length ? priced : ids;
      card.append(h("div", { class: "list rotate" }, this._item(pool[this._index % pool.length])));
      return;
    }
    card.append(h("div", { class: "list" }, ids.map((id) => this._item(id))));
  }

  getCardSize() {
    return this._config.rotate ? 2 : 1 + Math.min(this._ids.length || 1, 8);
  }
}

// ── Articles ─────────────────────────────────────────────────────────────────

const ARTICLES_CSS = `
  .list { display: flex; flex-direction: column; }
  .art { display: flex; gap: 10px; padding: 8px 2px; align-items: center; }
  .art + .art { border-top: 1px solid var(--divider-color); }
  .thumb { width: 56px; height: 56px; border-radius: 10px; object-fit: cover; flex: none;
           background: var(--secondary-background-color); }
  .body { flex: 1; min-width: 0; }
  .atitle { font-size: 14px; font-weight: 600; line-height: 1.3; display: -webkit-box; -webkit-line-clamp: 2;
            -webkit-box-orient: vertical; overflow: hidden; }
  .meta { margin-top: 3px; font-size: 11.5px; color: var(--secondary-text-color); white-space: nowrap;
          overflow: hidden; text-overflow: ellipsis; }
  .badge { display: inline-block; margin-right: 6px; padding: 0 6px; border-radius: 6px; font-size: 10.5px;
           font-weight: 700; background: #FFE898; color: #5C4612; vertical-align: 1px; }
`;

class FeedrionArticlesCard extends FeedrionBaseCard {
  static getStubConfig() {
    return {};
  }

  static getConfigForm() {
    return {
      schema: [
        { name: "title", selector: { text: {} } },
        { name: "max_items", selector: { number: { min: 1, max: 50, mode: "box" } } },
        { name: "show_images", selector: { boolean: {} } },
      ],
    };
  }

  setConfig(config) {
    super.setConfig({ max_items: 5, show_images: true, ...config });
  }

  get _entity() {
    return this._config.entity || findEntity(this._hass, "latest_articles", "sensor.feedrion_latest_articles");
  }

  get _unread() {
    return findEntity(this._hass, "unread", "sensor.feedrion_unread_articles");
  }

  _watched() {
    return [this._entity, this._unread];
  }

  _css() {
    return ARTICLES_CSS;
  }

  _build(card) {
    const st = this._state(this._entity);
    const unread = this._state(this._unread);
    const count = unread && Number.isFinite(Number(unread.state)) ? ` (${unread.state})` : "";
    card.append(this._head(this._config.title || `${t(this._hass, "articles")}${count}`));
    if (!st) {
      card.append(h("div", { class: "empty" }, t(this._hass, "not_found", { e: this._entity })));
      return;
    }
    const list = (Array.isArray(st.attributes.articles) ? st.attributes.articles : [])
      .slice(0, Math.max(1, Number(this._config.max_items) || 5));
    if (!list.length) {
      card.append(h("div", { class: "empty" }, t(this._hass, "articles_empty")));
      return;
    }
    card.append(h("div", { class: "list" }, list.map((a) => {
      const url = safeUrl(a.url);
      return h("div", { class: `art${url ? " clickable" : ""}`, onclick: url ? () => openUrl(url) : null },
        this._config.show_images ? img(a.image_url, "thumb") : null,
        h("div", { class: "body" },
          // A title masked by anti-spoil arrives masked; it stays masked here.
          h("div", { class: "atitle" }, a.masked ? h("span", { class: "badge" }, t(this._hass, "masked")) : null, a.title || ""),
          h("div", { class: "meta" }, [a.feed, timeAgo(this._hass, a.published_at)].filter(Boolean).join(" · "))));
    })));
  }

  getCardSize() {
    return 1 + Math.min(Number(this._config.max_items) || 5, 8);
  }
}

// ── Compteur ─────────────────────────────────────────────────────────────────

const UNREAD_CSS = `
  .tile { display: flex; align-items: center; gap: 12px; }
  .tile .logo { width: 40px; height: 40px; }
  .count { font-size: 34px; font-weight: 700; line-height: 1; color: var(--primary-color); }
  .label { font-size: 13px; color: var(--secondary-text-color); margin-top: 2px; }
`;

class FeedrionUnreadCard extends FeedrionBaseCard {
  static getStubConfig() {
    return {};
  }

  static getConfigForm() {
    return {
      schema: [
        { name: "entity", selector: { entity: { filter: { integration: "feedrion", domain: "sensor" } } } },
        { name: "name", selector: { text: {} } },
      ],
    };
  }

  get _entity() {
    return this._config.entity || findEntity(this._hass, "unread", "sensor.feedrion_unread_articles");
  }

  _watched() {
    return [this._entity];
  }

  _css() {
    return UNREAD_CSS;
  }

  _build(card) {
    const id = this._entity;
    const st = this._state(id);
    const logo = h("span", { class: "logo" });
    logo.innerHTML = LOGO; // constant markup
    const available = st && st.state !== "unavailable" && st.state !== "unknown";
    card.append(h("div", { class: "tile clickable", onclick: () => moreInfo(this, id) },
      logo,
      h("div", {},
        h("div", { class: "count" }, available ? st.state : "–"),
        h("div", { class: "label" }, this._config.name || (st && st.attributes.friendly_name) || t(this._hass, "unread")))));
  }

  getCardSize() {
    return 1;
  }

  getGridOptions() {
    return { columns: 6, min_columns: 3, rows: 1 };
  }
}

// ── Registration ─────────────────────────────────────────────────────────────

const CARDS = [
  ["feedrion-tv-card", FeedrionTvCard, "Feedrion · Séries", "« À voir » or « À venir », like the phone widget."],
  ["feedrion-weather-card", FeedrionWeatherCard, "Feedrion · Météo", "A city with its sky, like the phone widget."],
  ["feedrion-markets-card", FeedrionMarketsCard, "Feedrion · Bourse & devises", "Currency pairs and « Mes actions »."],
  ["feedrion-articles-card", FeedrionArticlesCard, "Feedrion · Articles", "The newest unread articles."],
  ["feedrion-unread-card", FeedrionUnreadCard, "Feedrion · Compteur", "One Feedrion counter."],
];

if (typeof customElements !== "undefined") {
  window.customCards = window.customCards || [];
  for (const [tag, cls, name, description] of CARDS) {
    if (!customElements.get(tag)) customElements.define(tag, cls);
    if (!window.customCards.some((c) => c.type === tag)) {
      window.customCards.push({ type: tag, name, description, preview: true,
        documentationURL: "https://github.com/max28/feedrion-homeassistant#cards" });
    }
  }
}

if (typeof module !== "undefined" && module.exports) {
  module.exports = {
    STRINGS, t, safeUrl, episodeCode, airDate, groupUpcoming, airLabel, episodeLine, weatherSky,
    weatherIcon, changeLabel, deg, CARDS: CARDS.map((c) => c[0]),
  };
}
})();
