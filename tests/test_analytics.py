"""Phase-2 tests: analytics engines, farm health, risks, Next Best Action, advisor.

All scenarios use synthetic weather snapshots injected into the demo farm so
tests are deterministic and offline (no Open-Meteo call).
"""
import copy
from datetime import date, timedelta

import pytest

from core.kb import load_knowledge_base
from core.models import list_demo_farms, load_farm_context, WeatherSnapshot, Provenance, DataSource, NDVIObservation
from core.reasoning import assess_farm, generate_farm_advice
from core.reasoning.advisor import detect_intent


@pytest.fixture(scope="module")
def kb():
    return load_knowledge_base()


def _farm(farm_id="TS_WARANGAL_COTTON_DEMO"):
    p = next(f["path"] for f in list_demo_farms() if f["farm_id"] == farm_id)
    return load_farm_context(p)


def _weather(ctx, past_rain, past_et0, fut_rain, fut_et0, tmax=32.0):
    """Build a synthetic 7-day past + 7-day future snapshot."""
    today = ctx.today()
    daily = []
    for i in range(7, 0, -1):
        daily.append({"date": (today - timedelta(days=i)).isoformat(), "tmax_c": tmax, "tmin_c": 22, "rain_mm": past_rain,
                      "et0_mm": past_et0, "rain_prob_pct": None, "wind_kmh": 10, "humidity_pct": 60, "is_forecast": False})
    for i in range(0, 7):
        daily.append({"date": (today + timedelta(days=i)).isoformat(), "tmax_c": tmax, "tmin_c": 22, "rain_mm": fut_rain,
                      "et0_mm": fut_et0, "rain_prob_pct": None, "wind_kmh": 10, "humidity_pct": 60, "is_forecast": True})
    return WeatherSnapshot(observed_at=today.isoformat(), temp_max_c=tmax, temp_min_c=22, humidity_pct=60, wind_kmh=10,
                           rain_last_7d_mm=past_rain * 7, rain_next_24h_mm=fut_rain, rain_next_7d_mm=fut_rain * 7,
                           et0_next_7d_mm=fut_et0 * 7, forecast_daily=daily,
                           provenance=Provenance(source=DataSource.WEATHER_API, detail="synthetic test"))


# --------------------------------------------------------------------- NBA scenarios
def test_dry_week_hot_no_rain_gives_irrigate(kb):
    ctx = _farm()
    ctx.weather = _weather(ctx, past_rain=0, past_et0=6.5, fut_rain=0, fut_et0=6.5, tmax=36)
    a = assess_farm(ctx, kb)
    assert a.water.mode == "quantitative"
    assert a.water.irrigation_advice in ("irrigate_now", "irrigate_24h")
    assert "rrigat" in a.next_best_action.action
    assert a.next_best_action.category == "irrigation"
    assert any(r.risk_type == "water_stress" for r in a.risks)
    # explanation must cite the numbers
    assert a.next_best_action.explanation.summary
    assert a.next_best_action.method.value == "Rule-based"


def test_rain_expected_and_moisture_ok_gives_hold(kb):
    ctx = _farm()
    ctx.irrigation.last_irrigation_date = (ctx.today() - timedelta(days=2)).isoformat()
    ctx.weather = _weather(ctx, past_rain=8, past_et0=4.0, fut_rain=28, fut_et0=3.0)
    a = assess_farm(ctx, kb)
    assert a.water.irrigation_advice in ("hold_rain", "hold_adequate")
    assert a.next_best_action.action.startswith(("Do not irrigate", "No irrigation needed"))
    assert any(r.risk_type == "excess_rainfall" for r in a.risks)  # 28 mm/day triggers heavy-rain watch


def test_wet_profile_no_rain_gives_adequate(kb):
    ctx = _farm()
    ctx.irrigation.last_irrigation_date = (ctx.today() - timedelta(days=1)).isoformat()
    ctx.weather = _weather(ctx, past_rain=12, past_et0=3.0, fut_rain=0, fut_et0=4.0)
    a = assess_farm(ctx, kb)
    assert a.water.status in ("adequate", "surplus")
    assert a.next_best_action.category == "irrigation"
    assert not any(r.risk_type == "water_stress" for r in a.risks)


def test_rainfed_farm_never_told_to_irrigate(kb):
    ctx = _farm("MH_NASHIK_SOYBEAN_DEMO")
    ctx.weather = _weather(ctx, past_rain=0, past_et0=6.0, fut_rain=0, fut_et0=6.0, tmax=35)
    a = assess_farm(ctx, kb)
    nba = a.next_best_action.action.lower()
    assert "rainfed" in nba
    assert not nba.startswith("irrigate")


def test_offline_weather_falls_back_to_qualitative(kb):
    ctx = _farm()
    ctx.weather = WeatherSnapshot(provenance=Provenance(source=DataSource.WEATHER_API, detail="offline"))
    a = assess_farm(ctx, kb)
    assert a.weather.available is False
    assert a.water.mode == "qualitative"
    assert a.health.score is not None
    # weather component excluded, not padded
    wc = next(b for b in a.health.breakdown if b.name == "Weather Condition")
    assert wc.available is False and wc.score is None
    assert a.health.assessed_weight < 1.0


def test_heat_stress_detected(kb):
    ctx = _farm()
    ctx.weather = _weather(ctx, past_rain=5, past_et0=5.0, fut_rain=0, fut_et0=7.0, tmax=43)
    a = assess_farm(ctx, kb)
    assert a.weather.heat_stress
    assert any(r.risk_type == "heat_stress" for r in a.risks)
    assert any(r.category == "protection" for r in a.actions)


# --------------------------------------------------------------------- NDVI
def test_ndvi_metrics_and_trend(kb):
    ctx = _farm()
    ctx.weather = _weather(ctx, 5, 4, 5, 4)
    a = assess_farm(ctx, kb)
    n = a.ndvi
    assert n.available and n.is_demo
    assert n.current == 0.63 and n.previous == 0.68
    assert n.change == pytest.approx(-0.05)
    assert n.change_pct == pytest.approx(-7.4, abs=0.05)
    assert n.trend == "declining" and n.stress_signal
    assert n.explanation.demo_data_used


def test_ndvi_decline_at_maturity_is_not_stress(kb):
    ctx = _farm()
    ctx.crop.sowing_date = (ctx.today() - timedelta(days=160)).isoformat()   # cotton boll opening
    ctx.weather = _weather(ctx, 5, 4, 5, 4)
    a = assess_farm(ctx, kb)
    assert "Picking" in a.stage.current_stage or "Opening" in a.stage.current_stage
    assert a.ndvi.trend == "declining" and not a.ndvi.stress_signal


def test_no_ndvi_series_is_reported_missing(kb):
    ctx = _farm()
    ctx.remote_sensing.ndvi_series = []
    ctx.weather = _weather(ctx, 5, 4, 5, 4)
    a = assess_farm(ctx, kb)
    assert a.ndvi.available is False
    veg = next(b for b in a.health.breakdown if b.name == "Vegetation Health")
    assert veg.available is False


# --------------------------------------------------------------------- soil / stage / health
def test_soil_flags_low_oc_and_alkaline(kb):
    ctx = _farm()
    a = assess_farm(ctx, kb)
    assert a.soil.available and a.soil.is_demo
    assert any("organic carbon" in l.lower() for l in a.soil.limitations)
    oc = next(p for p in a.soil.params if p.key == "organic_carbon_pct")
    assert oc.rating == "low"
    ph = next(p for p in a.soil.params if p.key == "ph")
    assert ph.rating == "moderately alkaline"


def test_soil_missing_values_do_not_score(kb):
    ctx = _farm()
    ctx.soil.ph = None; ctx.soil.organic_carbon_pct = None; ctx.soil.nitrogen_kg_ha = None
    ctx.soil.phosphorus_kg_ha = None; ctx.soil.potassium_kg_ha = None; ctx.soil.ec_ds_m = None
    a = assess_farm(ctx, kb)
    assert a.soil.score is None
    assert len(a.soil.explanation.missing) >= 5


def test_stage_timeline_cotton(kb):
    ctx = _farm()
    a = assess_farm(ctx, kb)
    assert a.stage.available and a.stage.crop == "Cotton"
    assert a.stage.current_stage == "Flowering" and a.stage.critical_water_window
    assert [s.status for s in a.stage.stages].count("current") == 1
    assert a.stage.reference_used == "Cotton"


def test_farm_health_breakdown_sums_and_labels(kb):
    ctx = _farm()
    ctx.weather = _weather(ctx, 5, 4, 5, 4)
    a = assess_farm(ctx, kb)
    h = a.health
    assert 0 <= h.score <= 100 and h.label in ("Healthy", "Fair", "Stressed", "Critical")
    assert len(h.breakdown) == 6
    assert abs(sum(b.weight for b in h.breakdown) - 1.0) < 1e-9
    assert h.demo_data_used and h.confidence <= 0.8
    assert h.explanation.summary.startswith("Farm health")


def test_financial_risk_when_uninsured(kb):
    ctx = _farm()
    ctx.weather = _weather(ctx, 5, 4, 5, 4)
    a = assess_farm(ctx, kb)
    assert any(r.risk_type == "financial" for r in a.risks)
    ctx2 = _farm(); ctx2.farmer.has_crop_insurance = True; ctx2.finance.input_cost_estimate_inr = 20000
    ctx2.weather = _weather(ctx2, 5, 4, 5, 4)
    a2 = assess_farm(ctx2, kb)
    assert not any(r.risk_type == "financial" for r in a2.risks)


# --------------------------------------------------------------------- advisor
@pytest.mark.parametrize("q,intent", [
    ("Should I irrigate today?", "irrigation"),
    ("Why is my farm health decreasing?", "health"),
    ("What government schemes may apply to me?", "schemes"),
    ("What loan options may suit me?", "loans"),
    ("What is causing crop stress?", "stress"),
    ("Which crop is best for my farm?", "crop_choice"),
    ("What should I do next?", "next_action"),
])
def test_intent_detection(q, intent):
    assert detect_intent(q) == intent


def test_advice_uses_farm_context_and_labels_methods(kb):
    ctx = _farm()
    ctx.weather = _weather(ctx, 0, 6.5, 0, 6.5, tmax=36)
    adv = generate_farm_advice(ctx, kb, "Should I irrigate today?")
    assert adv.intent == "irrigation"
    assert "rrigat" in adv.answer
    assert "Rule-based" in adv.method_labels and "Weather result" in adv.method_labels
    assert "DEMO" in " ".join(adv.explanation.sources) or adv.explanation.demo_data_used
    adv2 = generate_farm_advice(ctx, kb, "What schemes may apply to me?")
    assert adv2.intent == "schemes" and "Knowledge-base lookup" in adv2.method_labels
    assert adv2.kb_references and adv2.kb_references[0].startswith("CROP")
