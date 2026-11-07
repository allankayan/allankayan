export const RADAR_ZOOM = 7;
const TILE = 256;

export interface RadarFrame {
  host: string;
  path: string;
}

export interface TilePoint {
  tileX: number;
  tileY: number;
  pixelX: number;
  pixelY: number;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

/** Picks the newest observed frame from RainViewer's weather-maps.json. */
export function latestFrame(body: unknown): RadarFrame {
  const radar = isRecord(body) ? body.radar : undefined;
  const past = isRecord(radar) ? radar.past : undefined;
  const frame = Array.isArray(past) ? past.at(-1) : undefined;
  if (!isRecord(body) || typeof body.host !== "string" || !isRecord(frame) || typeof frame.path !== "string") {
    throw new Error("unexpected rainviewer response");
  }
  return { host: body.host, path: frame.path };
}

/** Web Mercator tile and pixel that contain a coordinate. */
export function tileFor(lat: number, lon: number, zoom = RADAR_ZOOM): TilePoint {
  const n = 2 ** zoom;
  const x = ((lon + 180) / 360) * n;
  const y = ((1 - Math.asinh(Math.tan((lat * Math.PI) / 180)) / Math.PI) / 2) * n;
  return { tileX: Math.floor(x), tileY: Math.floor(y), pixelX: Math.floor((x % 1) * TILE), pixelY: Math.floor((y % 1) * TILE) };
}

function paeth(a: number, b: number, c: number): number {
  const p = a + b - c;
  const pa = Math.abs(p - a), pb = Math.abs(p - b), pc = Math.abs(p - c);
  return pa <= pb && pa <= pc ? a : pb <= pc ? b : c;
}

/** Decodes the rows of an 8-bit RGBA, non-interlaced PNG up to and including lastRow. */
export async function pngRows(png: Uint8Array, lastRow: number): Promise<{ width: number; rows: Uint8Array[] }> {
  const view = new DataView(png.buffer, png.byteOffset, png.byteLength);
  const width = view.getUint32(16);
  if (png[24] !== 8 || png[25] !== 6 || png[28] !== 0) throw new Error("unsupported png: expected 8-bit RGBA, not interlaced");
  const idat: Uint8Array<ArrayBuffer>[] = [];
  for (let offset = 8; offset < png.length; ) {
    const length = view.getUint32(offset);
    if (String.fromCharCode(...png.subarray(offset + 4, offset + 8)) === "IDAT") idat.push(png.slice(offset + 8, offset + 8 + length));
    offset += 12 + length;
  }
  const inflated = new Response(new Blob(idat).stream().pipeThrough(new DecompressionStream("deflate")));
  const raw = new Uint8Array(await inflated.arrayBuffer());

  const stride = width * 4;
  const rows: Uint8Array[] = [];
  let previous = new Uint8Array(stride);
  for (let y = 0; y <= lastRow; y++) {
    const start = y * (stride + 1);
    const filter = raw[start];
    const row = new Uint8Array(stride);
    for (let i = 0; i < stride; i++) {
      const left = i >= 4 ? row[i - 4] : 0;
      const up = previous[i];
      const upLeft = i >= 4 ? previous[i - 4] : 0;
      const predictor = [0, left, up, (left + up) >> 1, paeth(left, up, upLeft)][filter];
      if (predictor === undefined) throw new Error(`unsupported png filter ${filter}`);
      row[i] = (raw[start + 1 + i] + predictor) & 0xff;
    }
    rows.push(row);
    previous = row;
  }
  return { width, rows };
}

/**
 * True when any pixel around the point is fully opaque: in RainViewer's palette only echoes of
 * 15 dBZ and up (light rain or heavier) are opaque, fainter drizzle and clutter are translucent.
 */
export async function rainAt(png: Uint8Array, pixelX: number, pixelY: number, radius = 1): Promise<boolean> {
  const { width, rows } = await pngRows(png, Math.min(TILE - 1, pixelY + radius));
  for (let y = Math.max(0, pixelY - radius); y < rows.length; y++) {
    for (let x = Math.max(0, pixelX - radius); x <= Math.min(width - 1, pixelX + radius); x++) {
      if (rows[y][x * 4 + 3] === 255) return true;
    }
  }
  return false;
}

export function tileUrl(frame: RadarFrame, point: TilePoint): string {
  return `${frame.host}${frame.path}/${TILE}/${RADAR_ZOOM}/${point.tileX}/${point.tileY}/2/0_0.png`;
}
