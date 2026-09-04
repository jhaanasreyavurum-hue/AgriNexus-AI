"""Environmental & agricultural analytics.

Every function here is a pure function of a :class:`FarmContext` (plus the
KnowledgeBase where needed) and returns explainable result objects. No
Streamlit, no I/O. All logic is *rule-based* and labelled as such unless a
module explicitly says otherwise.
"""
from core.analytics.ndvi import analyse_ndvi, NDVIAnalysis
from core.analytics.soil import analyse_soil, SoilAnalysis
from core.analytics.weather import analyse_weather, WeatherAnalysis
from core.analytics.water_balance import analyse_water, WaterAnalysis
from core.analytics.crop_stage import analyse_stage, StageAnalysis
from core.analytics.farm_health import compute_farm_health, FarmHealth
from core.analytics.risk import detect_risks

__all__ = [
    "analyse_ndvi", "NDVIAnalysis", "analyse_soil", "SoilAnalysis",
    "analyse_weather", "WeatherAnalysis", "analyse_water", "WaterAnalysis",
    "analyse_stage", "StageAnalysis", "compute_farm_health", "FarmHealth", "detect_risks",
]
