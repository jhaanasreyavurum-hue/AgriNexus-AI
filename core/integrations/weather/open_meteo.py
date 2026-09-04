"""Open-Meteo provider — free, no API key, CC-BY 4.0 (https://open-meteo.com)."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List

import requests

from core.integrations.weather.base import WeatherProvider
from core.models.farm_context import DataSource, Provenance, WeatherSnapshot

FORECAST_URL = "https://api.open-meteo.com/v1/forecast"


class OpenMeteoProvider(WeatherProvider):
    name = "Open-Meteo"
    requires_key = False

    def fetch(self, latitude: float, longitude: float, past_days: int = 7,
              forecast_days: int = 7, timeout: int = 10) -> WeatherSnapshot:
        params = {
            "latitude": latitude, "longitude": longitude,
            "daily": ",".join([
                "temperature_2m_max", "temperature_2m_min", "precipitation_sum",
                "et0_fao_evapotranspiration", "precipitation_probability_max",
                "wind_speed_10m_max", "relative_humidity_2m_mean",
            ]),
            "hourly": "precipitation",
            "past_days": past_days, "forecast_days": forecast_days,
            "timezone": "Asia/Kolkata",
        }
        try:
            r = requests.get(FORECAST_URL, params=params, timeout=timeout)
            r.raise_for_status()
            data = r.json()
        except Exception as exc:  # network / API failure -> honest empty snapshot
            return WeatherSnapshot(provenance=Provenance(
                source=DataSource.WEATHER_API, detail=f"Open-Meteo unavailable: {exc.__class__.__name__}"))
        return self._parse(data, past_days)

    # ------------------------------------------------------------------
    def _parse(self, data: Dict[str, Any], past_days: int) -> WeatherSnapshot:
        d = data.get("daily", {})
        dates: List[str] = d.get("time", [])
        n = len(dates)
        if n == 0:
            return WeatherSnapshot(provenance=Provenance(source=DataSource.WEATHER_API,
                                                         detail="Open-Meteo returned no daily data"))

        def col(name: str) -> List[Any]:
            v = d.get(name) or [None] * n
            return v

        tmax, tmin = col("temperature_2m_max"), col("temperature_2m_min")
        rain, et0 = col("precipitation_sum"), col("et0_fao_evapotranspiration")
        pprob, wind, rh = col("precipitation_probability_max"), col("wind_speed_10m_max"), col("relative_humidity_2m_mean")

        today_str = datetime.now(timezone.utc).astimezone().date().isoformat()
        try:
            today_idx = dates.index(today_str)
        except ValueError:
            today_idx = min(past_days, n - 1)

        daily = [{
            "date": dates[i], "tmax_c": tmax[i], "tmin_c": tmin[i], "rain_mm": rain[i],
            "et0_mm": et0[i], "rain_prob_pct": pprob[i], "wind_kmh": wind[i], "humidity_pct": rh[i],
            "is_forecast": i >= today_idx,
        } for i in range(n)]

        def ssum(vals: List[Any]) -> float | None:
            vals = [v for v in vals if v is not None]
            return round(float(sum(vals)), 1) if vals else None

        past = daily[:today_idx]
        future = daily[today_idx:]
        # next-24h rain from hourly series if present
        rain_24 = None
        h = data.get("hourly", {})
        if h.get("time") and h.get("precipitation"):
            now = datetime.now().replace(minute=0, second=0, microsecond=0)
            vals = []
            for t, p in zip(h["time"], h["precipitation"]):
                try:
                    ts = datetime.fromisoformat(t)
                except ValueError:
                    continue
                if 0 <= (ts - now).total_seconds() < 24 * 3600 and p is not None:
                    vals.append(p)
            rain_24 = round(float(sum(vals)), 1) if vals else None
        if rain_24 is None and future:
            rain_24 = future[0]["rain_mm"]

        cur = future[0] if future else daily[-1]
        return WeatherSnapshot(
            observed_at=datetime.now().isoformat(timespec="minutes"),
            temp_max_c=cur["tmax_c"], temp_min_c=cur["tmin_c"],
            humidity_pct=cur["humidity_pct"], wind_kmh=cur["wind_kmh"],
            rain_last_7d_mm=ssum([x["rain_mm"] for x in past[-7:]]),
            rain_next_24h_mm=rain_24,
            rain_next_7d_mm=ssum([x["rain_mm"] for x in future[:7]]),
            et0_next_7d_mm=ssum([x["et0_mm"] for x in future[:7]]),
            forecast_daily=daily,
            provenance=Provenance(source=DataSource.WEATHER_API, observed_at=today_str,
                                  detail="Open-Meteo (open-meteo.com, CC-BY 4.0)"),
        )
