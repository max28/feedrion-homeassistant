// Renders the pictures of the Feedrion dashboard cards shown in the README
// (and on feedrion.com), one per language, from INVENTED data: the shows, the
// posters and the prices below exist nowhere. The real card module is loaded
// as Home Assistant loads it; only `ha-card`, `ha-icon` and the `hass` object
// are stand-ins.
//
//   npm install            # @mdi/js and Playwright (its Chromium too)
//   ./fetch-fonts.sh       # optional: the fonts every script renders with
//   node render.mjs        # all languages → ../../docs/images/cards-<lang>.webp
//   node render.mjs en fr  # a few
//
// The clock is frozen (FROZEN_NOW) so "Today", "Tomorrow" and the weekdays do
// not change from one run to the next.

import { readFileSync, writeFileSync, existsSync, mkdirSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { createRequire } from "node:module";
import * as mdi from "@mdi/js";

const require = createRequire(import.meta.url);
const { chromium } = require("playwright");

const HERE = dirname(fileURLToPath(import.meta.url));
const ROOT = join(HERE, "..", "..");
const CARDS = readFileSync(join(ROOT, "custom_components/feedrion/frontend/feedrion-cards.js"), "utf8");
const OUT = join(ROOT, "docs/images");
const FONTS = join(HERE, "fonts");
const FROZEN_NOW = "2026-10-27T18:30:00+01:00";
const TZ = "Europe/Paris";

// One city per language, and Home Assistant's own word for "partly cloudy".
const LANGS = {
  en: { city: "London", partly: "Partly cloudy" },
  fr: { city: "Paris", partly: "Partiellement nuageux" },
  es: { city: "Madrid", partly: "Parcialmente nublado" },
  de: { city: "Berlin", partly: "Teilweise bewölkt" },
  pt: { city: "Lisboa", partly: "Parcialmente nublado" },
  ru: { city: "Москва", partly: "Переменная облачность" },
  ja: { city: "東京", partly: "晴れ時々曇り" },
  zh: { city: "北京", partly: "多云" },
  hi: { city: "नई दिल्ली", partly: "आंशिक रूप से बादल" },
  bn: { city: "ঢাকা", partly: "আংশিক মেঘলা" },
  id: { city: "Jakarta", partly: "Berawan sebagian" },
  ar: { city: "القاهرة", partly: "غائم جزئياً" },
  ur: { city: "کراچی", partly: "جزوی ابر آلود" },
  nl: { city: "Amsterdam", partly: "Gedeeltelijk bewolkt" },
  it: { city: "Roma", partly: "Parzialmente nuvoloso" },
  ko: { city: "서울", partly: "구름 조금" },
  pl: { city: "Warszawa", partly: "Częściowe zachmurzenie" },
  vi: { city: "Hà Nội", partly: "Có mây một phần" },
  uk: { city: "Київ", partly: "Мінлива хмарність" },
  tr: { city: "İstanbul", partly: "Parçalı bulutlu" },
};
const RTL = new Set(["ar", "ur"]);

// ── Invented shows: four series nobody has started yet ─────────────────────

const SHOWS = [
  { id: 1, name: "Northwind", title: "NORTHWIND", colors: ["#1E3A5F", "#0B1320"] },
  { id: 2, name: "The Glass Harbor", title: "THE GLASS|HARBOR", colors: ["#0E7490", "#082F49"] },
  { id: 3, name: "Orbit Nine", title: "ORBIT|NINE", colors: ["#4C1D95", "#0F0A1E"] },
  { id: 4, name: "Midnight Bakery", title: "MIDNIGHT|BAKERY", colors: ["#B45309", "#3B1A08"] },
];
const IMG = "https://img.feedrion.example";

function posterSvg(show) {
  const [a, b] = show.colors;
  const lines = show.title.split("|");
  const text = lines.map((l, i) =>
    `<text x="20" y="${450 - 30 - (lines.length - 1 - i) * 38}" font-family="Lora, serif" font-weight="700" font-size="34" letter-spacing="1.5" fill="#FBF9F4">${l}</text>`).join("");
  return `<svg xmlns="http://www.w3.org/2000/svg" width="300" height="450" viewBox="0 0 300 450">
    <defs><linearGradient id="g" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="${a}"/><stop offset="1" stop-color="${b}"/></linearGradient>
    <linearGradient id="s" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#000" stop-opacity="0"/><stop offset="1" stop-color="#000" stop-opacity=".67"/></linearGradient></defs>
    <rect width="300" height="450" fill="url(#g)"/>
    <circle cx="${300 * (0.62 + (show.id % 3) * 0.1)}" cy="135" r="72" fill="#fff" fill-opacity=".13"/>
    <circle cx="54" cy="${450 * (0.82 - (show.id % 2) * 0.1)}" r="36" fill="#fff" fill-opacity=".09"/>
    <rect y="279" width="300" height="171" fill="url(#s)"/>${text}</svg>`;
}

function backdropSvg(show) {
  const [a, b] = show.colors;
  return `<svg xmlns="http://www.w3.org/2000/svg" width="800" height="450" viewBox="0 0 800 450">
    <defs><linearGradient id="g" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="${b}"/><stop offset="1" stop-color="${a}"/></linearGradient></defs>
    <rect width="800" height="450" fill="url(#g)"/>
    <circle cx="${800 * (0.62 + ((show.id + 3) % 3) * 0.1)}" cy="135" r="108" fill="#fff" fill-opacity=".13"/>
    <circle cx="144" cy="${450 * (0.82 - ((show.id + 3) % 2) * 0.1)}" r="54" fill="#fff" fill-opacity=".09"/></svg>`;
}

const art = (s) => ({ poster_url: `${IMG}/poster-${s.id}.svg`, backdrop_url: `${IMG}/backdrop-${s.id}.svg` });

// "To watch": each show's first episode — nothing watched yet, so the rows say
// how much is ahead, never that something was seen.
const TO_WATCH = [
  { s: SHOWS[0], remaining: 24 },
  { s: SHOWS[2], remaining: 11 },
  { s: SHOWS[1], remaining: 12 },
  { s: SHOWS[3], remaining: 10 },
].map(({ s, remaining }, i) => ({
  show: s.name, show_id: s.id, episode_id: s.id * 10000 + 101, season: 1, number: 1, name: null,
  remaining, set_aside: false, aired: "2026-03-0" + (i + 1), ...art(s),
}));

function upcoming(now) {
  const day = (d) => {
    const x = new Date(now.getTime() + d * 86400000);
    return `${x.getFullYear()}-${String(x.getMonth() + 1).padStart(2, "0")}-${String(x.getDate()).padStart(2, "0")}`;
  };
  // 21:00 on the frozen day, in the page's time zone.
  const tonight = new Date(`${day(0)}T21:00:00+01:00`);
  return [
    { s: SHOWS[0], season: 3, number: 1, aired: day(0), aired_at: tonight.toISOString() },
    { s: SHOWS[2], season: 2, number: 1, aired: day(1) },
    { s: SHOWS[3], season: 2, number: 1, aired: day(4) },
    { s: SHOWS[3], season: 2, number: 2, aired: day(4) },
  ].map(({ s, ...e }) => ({ show: s.name, show_id: s.id, name: null, ...e, ...art(s) }));
}

// ── The page ────────────────────────────────────────────────────────────────

function pageHtml(lang) {
  const fontCss = existsSync(join(FONTS, "fonts.css"))
    ? readFileSync(join(FONTS, "fonts.css"), "utf8").replace(/url\((f\d+\.woff2)\)/g, "url(https://fonts.local/$1)")
    : "";
  return `<!doctype html><html lang="${lang}" dir="${RTL.has(lang) ? "rtl" : "ltr"}"><head><meta charset="utf-8">
  <style>${fontCss}
  :root {
    --primary-color: #03a9f4; --primary-text-color: #212121; --secondary-text-color: #727272;
    --divider-color: rgba(0,0,0,.12); --error-color: #db4437; --secondary-background-color: #e5e5e5;
    font-family: Roboto, "Noto Sans JP", "Noto Sans SC", "Noto Sans KR", "Noto Sans Bengali",
      "Noto Sans Devanagari", "Noto Sans Arabic", sans-serif;
  }
  html:lang(ja) { font-family: Roboto, "Noto Sans JP", sans-serif; }
  html:lang(zh) { font-family: Roboto, "Noto Sans SC", sans-serif; }
  html:lang(ko) { font-family: Roboto, "Noto Sans KR", sans-serif; }
  body { margin: 0; background: #fafafa; -webkit-font-smoothing: antialiased; }
  #board { width: 1040px; padding: 24px; display: grid; grid-template-columns: 1.25fr 1fr; gap: 16px;
           align-items: start; box-sizing: border-box; }
  .col { display: flex; flex-direction: column; gap: 16px; min-width: 0; }
  </style></head><body><div id="board"><div class="col" id="c1"></div><div class="col" id="c2"></div></div></body></html>`;
}

function setup({ lang, copy, now, icons }) {
  // ── stand-ins for Home Assistant's own elements ──
  customElements.define("ha-card", class extends HTMLElement {
    constructor() {
      super();
      this.attachShadow({ mode: "open" }).innerHTML = `<style>:host { display: block; background: #fff;
        border-radius: 12px; border: 1px solid #e0e0e0; }</style><slot></slot>`;
    }
  });
  customElements.define("ha-icon", class extends HTMLElement {
    static get observedAttributes() { return ["icon"]; }
    constructor() { super(); this.attachShadow({ mode: "open" }); }
    connectedCallback() { this._draw(); }
    attributeChangedCallback() { this._draw(); }
    _draw() {
      const path = icons[this.getAttribute("icon")] || "";
      this.shadowRoot.innerHTML = `<style>:host { display: inline-flex; width: var(--mdc-icon-size, 24px);
        height: var(--mdc-icon-size, 24px); } svg { width: 100%; height: 100%; fill: currentColor; }</style>
        <svg viewBox="0 0 24 24"><path d="${path}"/></svg>`;
    }
  });

  const day = (n) => new Date(now.getTime() + n * 86400000).toISOString();
  const states = {
    "sensor.feedrion_episodes_to_watch": {
      state: String(copy.toWatch.reduce((n, e) => n + e.remaining, 0)),
      attributes: { friendly_name: "Feedrion Episodes to watch", next: copy.toWatch },
    },
    "sensor.feedrion_next_episode": {
      state: copy.upcoming[0].aired_at,
      attributes: { friendly_name: "Feedrion Next episode", ...copy.upcoming[0], upcoming: copy.upcoming },
    },
    [`weather.feedrion_city`]: {
      state: "partlycloudy",
      attributes: { friendly_name: copy.city, temperature: 14, attribution: "MET Norway" },
    },
    "sun.sun": { state: "above_horizon", attributes: {} },
    "sensor.feedrion_eur_usd": { state: "1.0842", attributes: { friendly_name: "EUR/USD", symbol: "EUR/USD", change_pct: 0.21, unit_of_measurement: "USD" } },
    "sensor.feedrion_usd_jpy": { state: "148.37", attributes: { friendly_name: "USD/JPY", symbol: "USD/JPY", change_pct: -0.28, unit_of_measurement: "JPY" } },
    "sensor.feedrion_gbp_usd": { state: "1.2718", attributes: { friendly_name: "GBP/USD", symbol: "GBP/USD", change_pct: 0.27, unit_of_measurement: "USD" } },
    "sensor.feedrion_unread_articles": { state: "42", attributes: {} },
  };
  const forecast = [
    ["partlycloudy", 16, 8], ["rainy", 13, 9], ["cloudy", 12, 7], ["sunny", 15, 6], ["sunny", 17, 9],
  ].map(([condition, temperature, templow], i) => ({ datetime: day(i), condition, temperature, templow }));
  const hass = {
    language: lang,
    locale: { language: lang },
    states,
    entities: {},
    localize: (key) => (key.endsWith(".partlycloudy") ? copy.partly : ""),
    callService: () => Promise.resolve(),
    connection: {
      subscribeMessage: (cb) => {
        setTimeout(() => cb({ forecast }), 0);
        return Promise.resolve(() => {});
      },
    },
  };

  const add = (col, tag, config) => {
    const el = document.createElement(tag);
    el.setConfig(config);
    el.hass = hass;
    document.getElementById(col).append(el);
  };
  add("c1", "feedrion-tv-card", { mode: "to_watch", max_items: 4 });
  add("c1", "feedrion-tv-card", { mode: "upcoming", max_items: 3 });
  add("c2", "feedrion-weather-card", { entity: "weather.feedrion_city", forecast: "daily", forecast_items: 5 });
  add("c2", "feedrion-markets-card", {});
  add("c2", "feedrion-unread-card", {});
}

const ICONS = Object.fromEntries(
  ["weather-partly-cloudy", "weather-rainy", "weather-cloudy", "weather-sunny", "weather-night"].map((n) => {
    const key = "mdi" + n.split("-").map((p) => p[0].toUpperCase() + p.slice(1)).join("");
    return [`mdi:${n}`, mdi[key]];
  }),
);

async function main() {
  const wanted = process.argv.slice(2);
  const langs = wanted.length ? wanted : Object.keys(LANGS);
  for (const l of langs) if (!LANGS[l]) throw new Error(`unknown language: ${l}`);
  mkdirSync(OUT, { recursive: true });
  const browser = await chromium.launch();
  try {
    for (const lang of langs) {
      const context = await browser.newContext({
        viewport: { width: 1040, height: 900 }, deviceScaleFactor: 2, timezoneId: TZ, locale: lang,
      });
      const page = await context.newPage();
      await page.clock.setFixedTime(new Date(FROZEN_NOW));
      await page.route(`${IMG}/**`, (route) => {
        const m = /\/(poster|backdrop)-(\d)\.svg$/.exec(route.request().url());
        const show = m && SHOWS.find((s) => s.id === Number(m[2]));
        if (!show) return route.fulfill({ status: 404 });
        return route.fulfill({ contentType: "image/svg+xml", body: m[1] === "poster" ? posterSvg(show) : backdropSvg(show) });
      });
      await page.route("https://fonts.local/*", (route) => {
        const file = join(FONTS, new URL(route.request().url()).pathname.slice(1));
        return existsSync(file) ? route.fulfill({ contentType: "font/woff2", body: readFileSync(file) }) : route.fulfill({ status: 404 });
      });
      await page.setContent(pageHtml(lang));
      await page.addScriptTag({ content: CARDS });
      const now = new Date(FROZEN_NOW);
      await page.evaluate(
        ({ fn, args }) => new Function(`return (${fn})`)()(args),
        {
          fn: setup.toString(),
          args: { lang, now, icons: ICONS, copy: { ...LANGS[lang], toWatch: TO_WATCH, upcoming: upcoming(now) } },
        },
      );
      await page.evaluate(() => document.fonts.ready);
      await page.waitForFunction(() => [...document.images].every((i) => i.complete)
        && [...document.querySelectorAll("feedrion-tv-card")].every((c) => [...c.shadowRoot.querySelectorAll("img")].every((i) => i.complete)));
      await page.waitForTimeout(150);
      // WebP, encoded by Chromium itself: a fifth of the PNG for the same
      // picture, and every browser (and GitHub) shows it.
      const png = await page.locator("#board").screenshot();
      const webp = await page.evaluate(async (b64) => {
        const bitmap = await createImageBitmap(await (await fetch(`data:image/png;base64,${b64}`)).blob());
        const canvas = new OffscreenCanvas(bitmap.width, bitmap.height);
        canvas.getContext("2d").drawImage(bitmap, 0, 0);
        const blob = await canvas.convertToBlob({ type: "image/webp", quality: 0.9 });
        const bytes = new Uint8Array(await blob.arrayBuffer());
        let bin = "";
        for (let i = 0; i < bytes.length; i += 0x8000) bin += String.fromCharCode(...bytes.subarray(i, i + 0x8000));
        return btoa(bin);
      }, png.toString("base64"));
      const file = join(OUT, `cards-${lang}.webp`);
      writeFileSync(file, Buffer.from(webp, "base64"));
      console.log(`render: ${file}`);
      await context.close();
    }
  } finally {
    await browser.close();
  }
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
