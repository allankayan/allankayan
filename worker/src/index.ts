import clouds from "../../weather/clouds.svg";
import moon from "../../weather/moon.svg";
import rain from "../../weather/rain.svg";
import sun from "../../weather/sun.svg";
import { latestFrame, rainAt, tileFor, tileUrl } from "./radar.ts";
import { parseCurrent, scene, type Scene } from "./scene.ts";

const CARDS: Record<Scene, string> = { sun, moon, clouds, rain };
const FALLBACK: Scene = "clouds";
const WEATHER_CACHE_SECONDS = 600;
const RADAR_CACHE_SECONDS = 300;

function message(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}

async function forecastScene(lat: string, lon: string): Promise<Scene> {
  const query = new URLSearchParams({ latitude: lat, longitude: lon, current: "weather_code,is_day", timezone: "auto" });
  const response = await fetch(`https://api.open-meteo.com/v1/forecast?${query}`, {
    cf: { cacheTtl: WEATHER_CACHE_SECONDS, cacheEverything: true },
  });
  if (!response.ok) throw new Error(`open-meteo responded ${response.status}`);
  return scene(parseCurrent(await response.json()));
}

/** Radar sees showers that the forecast model misses, so it decides whether it is raining. */
async function radarRain(lat: number, lon: number): Promise<boolean> {
  const cf = { cacheTtl: RADAR_CACHE_SECONDS, cacheEverything: true };
  const maps = await fetch("https://api.rainviewer.com/public/weather-maps.json", { cf });
  if (!maps.ok) throw new Error(`rainviewer maps responded ${maps.status}`);
  const point = tileFor(lat, lon);
  const tile = await fetch(tileUrl(latestFrame(await maps.json()), point), { cf });
  if (!tile.ok) throw new Error(`rainviewer tile responded ${tile.status}`);
  return rainAt(new Uint8Array(await tile.arrayBuffer()), point.pixelX, point.pixelY);
}

async function currentScene(env: Env): Promise<Scene> {
  const lat = Number(env.WEATHER_LAT);
  const lon = Number(env.WEATHER_LON);
  if (!Number.isFinite(lat) || !Number.isFinite(lon)) throw new Error("WEATHER_LAT and WEATHER_LON must be numbers");

  const [forecast, radar] = await Promise.allSettled([forecastScene(env.WEATHER_LAT, env.WEATHER_LON), radarRain(lat, lon)]);
  if (radar.status === "rejected") {
    console.error(JSON.stringify({ message: "radar lookup failed", error: message(radar.reason) }));
  }
  if (radar.status === "fulfilled" && radar.value) return "rain";
  if (forecast.status === "rejected") throw forecast.reason;
  return forecast.value;
}

export default {
  async fetch(request, env): Promise<Response> {
    if (new URL(request.url).pathname !== "/card.svg") return new Response("Not found", { status: 404 });

    let name: Scene = FALLBACK;
    try {
      name = await currentScene(env);
    } catch (error) {
      console.error(JSON.stringify({ message: "weather lookup failed", error: message(error) }));
    }
    console.log(JSON.stringify({ message: "card served", scene: name }));
    // no-cache keeps GitHub's image proxy from serving a stale scene; the lookups above stay cached at the edge.
    return new Response(CARDS[name], {
      headers: { "content-type": "image/svg+xml; charset=utf-8", "cache-control": "no-cache" },
    });
  },
} satisfies ExportedHandler<Env>;
