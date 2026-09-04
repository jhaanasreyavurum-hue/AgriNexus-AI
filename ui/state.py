"""Session state + caching glue between Streamlit and ``core``.

* the KnowledgeBase is loaded once per process (``st.cache_resource``)
* the selected FarmContext lives in ``st.session_state["ctx"]``
* the full assessment is cached per (farm context, weather mode) so page
  switches don't re-run the engines
"""
from __future__ import annotations

import hashlib
import json
from typing import Any, Dict, List, Optional

import streamlit as st

from core.kb import load_knowledge_base
from core.models import FarmContext, list_demo_farms, load_farm_context
from core.reasoning import run_full_assessment

WEATHER_MODES = {"live": "Live weather (Open-Meteo)", "offline": "No weather (offline)"}


@st.cache_resource(show_spinner="Loading knowledge base…")
def get_kb():
    return load_knowledge_base()


def _secrets() -> Optional[Dict[str, Any]]:
    try:
        return dict(st.secrets)
    except Exception:  # no secrets.toml — perfectly fine
        return None


def demo_farms() -> List[Dict[str, str]]:
    return list_demo_farms()


def _ctx_fingerprint(ctx: FarmContext) -> str:
    return hashlib.sha1(json.dumps(ctx.to_dict(), sort_keys=True, default=str).encode()).hexdigest()


@st.cache_data(show_spinner=False, ttl=1800, max_entries=16)
def _fetch_weather(lat: float, lon: float, _secrets_key: str) -> Dict[str, Any]:
    """Cached weather fetch (30 min). Returns a plain dict so it is picklable."""
    from core.integrations.weather import get_provider
    import dataclasses
    snap = get_provider(_secrets()).fetch(lat, lon)
    d = dataclasses.asdict(snap)
    d["provenance"] = {"source": snap.provenance.source.value, "observed_at": snap.provenance.observed_at, "detail": snap.provenance.detail}
    return d


def attach_weather(ctx: FarmContext, mode: str) -> FarmContext:
    """Return ctx with a live weather snapshot attached (keeps the twin's annual normal)."""
    if mode != "live" or ctx.location.latitude is None or ctx.location.longitude is None:
        return ctx
    from core.models import WeatherSnapshot, Provenance, DataSource
    try:
        d = _fetch_weather(float(ctx.location.latitude), float(ctx.location.longitude), "v1")
    except Exception as exc:  # network failure → keep offline snapshot, tell the user
        st.session_state["weather_error"] = str(exc)
        return ctx
    prov = d.pop("provenance")
    snap = WeatherSnapshot(**d)
    snap.provenance = Provenance(source=DataSource(prov["source"]), observed_at=prov.get("observed_at"), detail=prov.get("detail"))
    snap.annual_rainfall_normal_mm = ctx.weather.annual_rainfall_normal_mm
    ctx.weather = snap
    st.session_state.pop("weather_error", None)
    return ctx


def get_effective_kb():
    """KB with the session registry overlay (loan products added/updated by authorised users on this server)."""
    return get_registry().effective_kb()


@st.cache_data(show_spinner="Running farm assessment…", max_entries=8)
def _assess_cached(ctx_dict: Dict[str, Any], _fingerprint: str, target_season: Optional[str], _registry_version: int = 0):
    ctx = FarmContext.from_dict(ctx_dict)
    return run_full_assessment(ctx, get_effective_kb(), target_season=target_season)


def has_context() -> bool:
    return "ctx" in st.session_state


def clear_context() -> None:
    for k in ("ctx", "farm_choice", "copilot_history", "onboard"):
        st.session_state.pop(k, None)


@st.cache_resource(show_spinner="Loading modelled segment matrix…")
def get_matrix():
    from core.intelligence import load_segment_matrix
    return load_segment_matrix()


def get_registry():
    from core.store import get_registry as _get
    return _get(get_kb())


def ensure_context() -> FarmContext:
    """Selected farm context (defaults to the primary demo farm)."""
    if "ctx" not in st.session_state:
        farms = demo_farms()
        primary = next((f for f in farms if f["farm_id"].startswith("TS_")), farms[0])
        st.session_state["ctx"] = load_farm_context(primary["path"])
        st.session_state["farm_choice"] = primary["farm_id"]
        st.session_state.setdefault("weather_mode", "live")
    return st.session_state["ctx"]


def select_farm(farm_id: str) -> None:
    f = next(f for f in demo_farms() if f["farm_id"] == farm_id)
    st.session_state["ctx"] = load_farm_context(f["path"])
    st.session_state["farm_choice"] = farm_id
    st.session_state.pop("copilot_history", None)


def set_context(ctx: FarmContext) -> None:
    st.session_state["ctx"] = ctx
    st.session_state["farm_choice"] = ctx.farm_id
    st.session_state.pop("copilot_history", None)


def get_assessment(target_season: Optional[str] = None):
    """Full assessment for the selected farm, with the chosen weather mode."""
    ctx = ensure_context()
    mode = st.session_state.get("weather_mode", "live")
    ctx = attach_weather(ctx, mode)
    st.session_state["ctx"] = ctx
    d = ctx.to_dict()
    return _assess_cached(d, _ctx_fingerprint(ctx), target_season, get_registry().version)


def narrator_available() -> bool:
    from core.reasoning.narrator import narrator_enabled
    return narrator_enabled(_secrets())


def secrets() -> Optional[Dict[str, Any]]:
    return _secrets()
