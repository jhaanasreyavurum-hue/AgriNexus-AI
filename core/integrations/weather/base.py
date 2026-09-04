from __future__ import annotations

import os
from abc import ABC, abstractmethod
from typing import Any, Mapping, Optional

from core.models.farm_context import WeatherSnapshot


class WeatherProvider(ABC):
    name: str = "abstract"
    requires_key: bool = False

    @abstractmethod
    def fetch(self, latitude: float, longitude: float, past_days: int = 7,
              forecast_days: int = 7, timeout: int = 10) -> WeatherSnapshot:
        ...


def _lookup(secrets: Optional[Mapping[str, Any]], key: str) -> Optional[str]:
    if secrets is not None:
        try:
            if key in secrets and secrets[key]:
                return str(secrets[key])
        except Exception:  # st.secrets raises if no secrets file exists
            pass
    return os.environ.get(key) or None


def get_provider(secrets: Optional[Mapping[str, Any]] = None) -> WeatherProvider:
    """Choose provider from ``WEATHER_PROVIDER`` secret/env; default Open-Meteo.

    Pass ``st.secrets`` from the UI layer; this module never imports Streamlit.
    """
    from core.integrations.weather.open_meteo import OpenMeteoProvider
    from core.integrations.weather.openweathermap import OpenWeatherMapProvider

    choice = (_lookup(secrets, "WEATHER_PROVIDER") or "open_meteo").lower()
    if choice in ("openweathermap", "owm"):
        key = _lookup(secrets, "OPENWEATHER_API_KEY")
        if key:
            return OpenWeatherMapProvider(api_key=key)
    return OpenMeteoProvider()
