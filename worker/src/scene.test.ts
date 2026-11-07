import assert from "node:assert/strict";
import { test } from "node:test";
import { parseCurrent, scene } from "./scene.ts";

test("clear sky shows the sun by day and the moon by night", () => {
  assert.equal(scene({ weatherCode: 0, isDay: true }), "sun");
  assert.equal(scene({ weatherCode: 1, isDay: false }), "moon");
});

test("drizzle, rain, showers and storms show rain", () => {
  for (const weatherCode of [51, 61, 67, 80, 82, 95, 99]) {
    assert.equal(scene({ weatherCode, isDay: true }), "rain", `code ${weatherCode}`);
  }
});

test("partly cloudy, overcast, fog and snow show clouds", () => {
  for (const weatherCode of [2, 3, 45, 48, 71, 86]) {
    assert.equal(scene({ weatherCode, isDay: false }), "clouds", `code ${weatherCode}`);
  }
});

test("parses the current block and rejects anything else", () => {
  assert.deepEqual(parseCurrent({ current: { weather_code: 3, is_day: 0 } }), { weatherCode: 3, isDay: false });
  assert.throws(() => parseCurrent({ current: { weather_code: "3", is_day: 0 } }));
  assert.throws(() => parseCurrent(null));
});
