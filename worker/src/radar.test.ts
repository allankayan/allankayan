import assert from "node:assert/strict";
import { test } from "node:test";
import { deflateSync } from "node:zlib";
import { latestFrame, pngRows, rainAt, tileFor } from "./radar.ts";

type Pixel = [number, number, number, number];

function paeth(a: number, b: number, c: number): number {
  const p = a + b - c;
  const pa = Math.abs(p - a), pb = Math.abs(p - b), pc = Math.abs(p - c);
  return pa <= pb && pa <= pc ? a : pb <= pc ? b : c;
}

/** Encodes RGBA rows as a PNG, using the given filter type on each row. */
function png(rows: Pixel[][], filters: number[]): Uint8Array {
  const width = rows[0].length;
  const stride = width * 4;
  let previous = new Uint8Array(stride);
  const raw: number[] = [];
  rows.forEach((pixels, y) => {
    const row = Uint8Array.from(pixels.flat());
    raw.push(filters[y]);
    for (let i = 0; i < stride; i++) {
      const left = i >= 4 ? row[i - 4] : 0, up = previous[i], upLeft = i >= 4 ? previous[i - 4] : 0;
      const predictor = [0, left, up, (left + up) >> 1, paeth(left, up, upLeft)][filters[y]];
      raw.push((row[i] - predictor) & 0xff);
    }
    previous = row;
  });
  const chunk = (type: string, data: Uint8Array) => {
    const out = new Uint8Array(12 + data.length);
    new DataView(out.buffer).setUint32(0, data.length);
    out.set([...type].map((c) => c.charCodeAt(0)), 4);
    out.set(data, 8);
    return out;
  };
  const header = new Uint8Array(13);
  new DataView(header.buffer).setUint32(0, width);
  new DataView(header.buffer).setUint32(4, rows.length);
  header.set([8, 6, 0, 0, 0], 8);
  const parts = [Uint8Array.from([137, 80, 78, 71, 13, 10, 26, 10]), chunk("IHDR", header), chunk("IDAT", deflateSync(Uint8Array.from(raw))), chunk("IEND", new Uint8Array())];
  return Uint8Array.from(parts.flatMap((p) => [...p]));
}

const clear: Pixel = [0, 0, 0, 0];
const drizzle: Pixel = [206, 192, 135, 150];
const rain: Pixel = [0, 119, 170, 255];

test("decodes every png filter type", async () => {
  const rows: Pixel[][] = [
    [[10, 20, 30, 40], [50, 60, 70, 80], [90, 100, 110, 120]],
    [[200, 10, 0, 255], [1, 2, 3, 4], [250, 250, 250, 250]],
    [[7, 77, 177, 255], [130, 3, 99, 12], [0, 0, 0, 0]],
    [[33, 66, 99, 132], [255, 255, 255, 255], [12, 34, 56, 78]],
    [[5, 15, 25, 35], [45, 55, 65, 75], [85, 95, 105, 115]],
  ];
  const { rows: decoded } = await pngRows(png(rows, [0, 1, 2, 3, 4]), 4);
  assert.deepEqual(decoded.map((row) => [...row]), rows.map((row) => row.flat()));
});

test("only opaque echoes near the point count as rain", async () => {
  const grid = (cell: Pixel, at: [number, number]) =>
    Array.from({ length: 5 }, (_, y) => Array.from({ length: 5 }, (_, x) => (x === at[0] && y === at[1] ? cell : clear)));
  const filters = [0, 1, 2, 3, 4];
  assert.equal(await rainAt(png(grid(rain, [3, 2]), filters), 2, 2), true);
  assert.equal(await rainAt(png(grid(drizzle, [2, 2]), filters), 2, 2), false);
  assert.equal(await rainAt(png(grid(rain, [4, 4]), filters), 1, 1), false);
});

test("finds the tile and pixel of a coordinate", () => {
  assert.deepEqual(tileFor(0, 0, 1), { tileX: 1, tileY: 1, pixelX: 0, pixelY: 0 });
  const point = tileFor(-23.55, -46.63);
  assert.equal(point.tileX, 47);
  assert.ok(point.pixelX >= 0 && point.pixelX < 256 && point.pixelY >= 0 && point.pixelY < 256);
});

test("reads the newest radar frame and rejects anything else", () => {
  const maps = { host: "https://tilecache.rainviewer.com", radar: { past: [{ path: "/v2/radar/1" }, { path: "/v2/radar/2" }] } };
  assert.deepEqual(latestFrame(maps), { host: "https://tilecache.rainviewer.com", path: "/v2/radar/2" });
  assert.throws(() => latestFrame({ host: "x", radar: { past: [] } }));
  assert.throws(() => latestFrame(null));
});
