"""Weather provider interface.

* :class:`OpenMeteoProvider` — default, keyless, works on Streamlit Cloud.
* :class:`OpenWeatherMapProvider` — optional, needs ``OPENWEATHER_API_KEY``.
* :func:`get_provider` — picks a provider from a secrets/env mapping without
  importing Streamlit (the UI passes ``st.secrets`` in as a plain dict).

All providers return a :class:`core.models.WeatherSnapshot`. On any failure
they return a snapshot with ``provenance.detail`` describing the error and all
numeric fields ``None`` — never fabricated values.
"""
from core.integrations.weather.base import WeatherProvider, get_provider
from core.integrations.weather.open_meteo import OpenMeteoProvider
from core.integrations.weather.openweathermap import OpenWeatherMapProvider

__all__ = ["WeatherProvider", "get_provider", "OpenMeteoProvider", "OpenWeatherMapProvider"]
