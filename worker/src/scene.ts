export type Scene = "sun" | "moon" | "clouds" | "rain";

export interface CurrentWeather {
  weatherCode: number;
  isDay: boolean;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

/** Reads the `current` block of an Open-Meteo forecast response. */
export function parseCurrent(body: unknown): CurrentWeather {
  const current = isRecord(body) ? body.current : undefined;
  if (!isRecord(current) || typeof current.weather_code !== "number" || typeof current.is_day !== "number") {
    throw new Error("unexpected open-meteo response");
  }
  return { weatherCode: current.weather_code, isDay: current.is_day === 1 };
}

/** Maps a WMO weather code to the card scene. */
export function scene({ weatherCode, isDay }: CurrentWeather): Scene {
  if (weatherCode === 0 || weatherCode === 1) return isDay ? "sun" : "moon";
  const raining =
    (weatherCode >= 51 && weatherCode <= 67) || (weatherCode >= 80 && weatherCode <= 82) || weatherCode >= 95;
  return raining ? "rain" : "clouds";
}
