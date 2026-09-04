"""OpenWeatherMap provider — optional, requires ``OPENWEATHER_API_KEY`` in
``st.secrets`` or the environment. Never hard-code the key."""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from typing import Any, Dict

import requests

from core.integrations.weather.base import WeatherProvider
from core.models.farm_context import DataSource, Provenance, WeatherSnapshot

URL = "https://api.openweathermap.org/data/2.5/forecast"  # 5 day / 3 hour, free tier


class OpenWeatherMapProvider(WeatherProvider):
    name = "OpenWeatherMap"
    requires_key = True

    def __init__(self, api_key: str):
        self.api_key = api_key

    def fetch(self, latitude: float, longitude: float, past_days: int = 7,
              forecast_days: int = 5, timeout: int = 10) -> WeatherSnapshot:
        try:
            r = requests.get(URL, params={"lat": latitude, "lon": longitude, "appid": self.api_key,
                                          "units": "metric"}, timeout=timeout)
            r.raise_for_status()
            data = r.json()
        except Exception as exc:
            return WeatherSnapshot(provenance=Provenance(
                source=DataSource.WEATHER_API, detail=f"OpenWeatherMap unavailable: {exc.__class__.__name__}"))
        return self._parse(data)

    def _parse(self, data: Dict[str, Any]) -> WeatherSnapshot:
        by_day: Dict[str, Dict[str, Any]] = defaultdict(lambda: {"tmax": [], "tmin": [], "rain": 0.0, "rh": [], "wind": []})
        for item in data.get("list", []):
            day = item["dt_txt"][:10]
            m = item.get("main", {})
            by_day[day]["tmax"].append(m.get("temp_max"))
            by_day[day]["tmin"].append(m.get("temp_min"))
            by_day[day]["rh"].append(m.get("humidity"))
            by_day[day]["wind"].append((item.get("wind") or {}).get("speed", 0) * 3.6)
            by_day[day]["rain"] += (item.get("rain") or {}).get("3h", 0.0)
        daily = []
        for day in sorted(by_day):
            v = by_day[day]
            daily.append({"date": day, "tmax_c": max(v["tmax"]), "tmin_c": min(v["tmin"]),
                          "rain_mm": round(v["rain"], 1), "et0_mm": None, "rain_prob_pct": None,
                          "wind_kmh": round(max(v["wind"]), 1), "humidity_pct": round(sum(v["rh"]) / len(v["rh"]), 0),
                          "is_forecast": True})
        if not daily:
            return WeatherSnapshot(provenance=Provenance(source=DataSource.WEATHER_API, detail="OpenWeatherMap: no data"))
        cur = daily[0]
        return WeatherSnapshot(
            observed_at=datetime.now().isoformat(timespec="minutes"),
            temp_max_c=cur["tmax_c"], temp_min_c=cur["tmin_c"], humidity_pct=cur["humidity_pct"], wind_kmh=cur["wind_kmh"],
            rain_last_7d_mm=None,  # not provided by this endpoint — left None, not guessed
            rain_next_24h_mm=cur["rain_mm"], rain_next_7d_mm=round(sum(x["rain_mm"] for x in daily[:7]), 1),
            et0_next_7d_mm=None, forecast_daily=daily,
            provenance=Provenance(source=DataSource.WEATHER_API, detail="OpenWeatherMap 5-day forecast"),
        )
