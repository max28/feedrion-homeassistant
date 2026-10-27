// Unit tests of the cards' pure helpers: node --test tests/js
const test = require("node:test");
const assert = require("node:assert/strict");
const cards = require("../../custom_components/feedrion/frontend/feedrion-cards.js");

const fr = { locale: { language: "fr" } };
const en = { locale: { language: "en" } };

test("only http(s) links leave a card", () => {
  assert.equal(cards.safeUrl("https://example.com/a"), "https://example.com/a");
  assert.equal(cards.safeUrl("javascript:alert(1)"), null);
  assert.equal(cards.safeUrl("data:text/html,x"), null);
  assert.equal(cards.safeUrl(null), null);
});

test("the same show the same day is one row", () => {
  const rows = cards.groupUpcoming([
    { show_id: 1, show: "Northwind", season: 2, number: 3, aired: "2026-10-28" },
    { show_id: 1, show: "Northwind", season: 2, number: 4, aired: "2026-10-28" },
    { show_id: 1, show: "Northwind", season: 2, number: 5, aired: "2026-10-28" },
    { show_id: 2, show: "Orbit Nine", season: 1, number: 1, aired: "2026-10-28" },
    { show_id: 1, show: "Northwind", season: 2, number: 6, aired: "2026-11-04" },
  ]);
  assert.equal(rows.length, 3);
  assert.equal(cards.episodeLine(fr, rows[0]), "S02 · Épisodes 3 à 5");
  assert.equal(cards.episodeLine(en, rows[1]), "S01E01");
  assert.equal(cards.episodeLine(en, { season: 1, number: 5, name: "Pilot" }), "S01E05 · Pilot");
});

test("a broadcast day is read at LOCAL midnight", () => {
  const { date, timed } = cards.airDate({ aired: "2026-10-28" });
  assert.equal(timed, false);
  assert.deepEqual([date.getFullYear(), date.getMonth(), date.getDate(), date.getHours()], [2026, 9, 28, 0]);
  assert.equal(cards.airDate({ aired_at: "2026-10-29T01:00:00Z" }).timed, true);
});

test("today and tomorrow are named", () => {
  const now = new Date(2026, 9, 25, 12, 0);
  assert.equal(cards.airLabel(fr, { aired: "2026-10-25" }, now), "Aujourd'hui");
  assert.equal(cards.airLabel(en, { aired: "2026-10-26" }, now), "Tomorrow");
  assert.match(cards.airLabel(fr, { aired: "2026-10-30" }, now), /30/);
});

test("the sky follows the phone widget's families", () => {
  assert.equal(cards.weatherSky("sunny", false), "clear_day");
  assert.equal(cards.weatherSky("sunny", true), "clear_night");
  assert.equal(cards.weatherSky("partlycloudy", true), "partly_night");
  assert.equal(cards.weatherSky("pouring", false), "rain");
  assert.equal(cards.weatherSky("lightning-rainy", false), "thunder");
  assert.equal(cards.weatherSky("windy", false), "cloudy");
});

test("an unknown language falls back to English", () => {
  assert.equal(cards.t({ locale: { language: "he" } }, "watched"), "Watched");
  assert.equal(cards.t({ locale: { language: "zh-Hans" } }, "tomorrow"), "明天");
  assert.equal(cards.t(fr, "remaining_other", { n: 3 }), "3 restants");
});

test("the cards speak the app's 20 languages, every key in each", () => {
  const langs = ["en", "fr", "es", "de", "pt", "ru", "ja", "zh", "hi", "bn", "id", "ar", "ur", "nl", "it",
    "ko", "pl", "vi", "uk", "tr"];
  assert.deepEqual(Object.keys(cards.STRINGS).sort(), [...langs].sort());
  const keys = Object.keys(cards.STRINGS.en).sort();
  for (const l of langs) {
    assert.deepEqual(Object.keys(cards.STRINGS[l]).sort(), keys, l);
    for (const k of ["remaining_other", "episodes_range", "last_close", "not_found"]) {
      for (const v of (cards.STRINGS.en[k].match(/\{\w+\}/g) || [])) assert.ok(cards.STRINGS[l][k].includes(v), `${l}.${k}`);
    }
  }
});

test("a change is signed, a missing one is nothing", () => {
  assert.equal(cards.changeLabel(en, 1.234), "+1.23 %");
  assert.equal(cards.changeLabel(en, -0.5), "−0.50 %");
  assert.equal(cards.changeLabel(en, null), null);
  assert.equal(cards.deg(12.6), "13°");
  assert.equal(cards.deg(undefined), "–");
});

test("an entity's name loses the Feedrion device prefix", () => {
  const hass = {
    states: {
      "sensor.feedrion_euro_dollar": { attributes: { friendly_name: "Feedrion Euro → Dollar" } },
      "sensor.feedrion_apple": { attributes: { friendly_name: "Maison Apple" } },
      "weather.feedrion_orleans": { attributes: { friendly_name: "Feedrion Orléans" } },
      "sensor.feedrion_renamed": { attributes: { friendly_name: "Feedrion X" } },
    },
    entities: {
      "sensor.feedrion_apple": { platform: "feedrion", device_id: "d1" },
      "sensor.feedrion_renamed": { platform: "feedrion", device_id: "d1", name: "Mon dollar" },
    },
    devices: { d1: { name: "Feedrion", name_by_user: "Maison" } },
  };
  assert.equal(cards.entityLabel(hass, "sensor.feedrion_euro_dollar"), "Euro → Dollar");
  assert.equal(cards.entityLabel(hass, "sensor.feedrion_apple"), "Apple");
  assert.equal(cards.entityLabel(hass, "weather.feedrion_orleans"), "Orléans");
  assert.equal(cards.entityLabel(hass, "sensor.feedrion_renamed"), "Mon dollar");
});

test("upcoming, saved and alerts have their own cards", () => {
  for (const tag of ["feedrion-upcoming-card", "feedrion-saved-card", "feedrion-alerts-card"]) {
    assert.ok(cards.CARDS.includes(tag), tag);
  }
});
