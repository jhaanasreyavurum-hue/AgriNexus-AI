"""Farm Digital Twin — the single context object every engine consumes.

Design rules
------------
* Every measured quantity carries a :class:`Provenance` so the UI can label it
  *measured / modelled / remote-sensing / demo / user-entered / API*.
* Missing data is ``None`` — engines must handle ``None`` and say "not
  available" rather than invent a value.
* The class is plain Python (dataclasses) with no Streamlit dependency, so it
  can be built from a YAML demo file, a Streamlit form, or a database row.
"""
from __future__ import annotations

import dataclasses
from dataclasses import dataclass, field
from datetime import date, datetime
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

from core import DEMO_FARMS_DIR


class DataSource(str, Enum):
    MEASURED = "measured"            # lab / sensor / survey
    MODELLED = "modelled"            # derived by a model (e.g. water balance)
    REMOTE_SENSING = "remote_sensing"
    WEATHER_API = "weather_api"
    USER_ENTERED = "user_entered"
    KNOWLEDGE_BASE = "knowledge_base"
    REFERENCE = "reference"          # published reference tables (FAO, ICAR)
    DEMO = "demo"                    # sample data — clearly labelled in UI
    UNKNOWN = "unknown"


@dataclass
class Provenance:
    source: DataSource = DataSource.UNKNOWN
    observed_at: Optional[str] = None     # ISO date/datetime
    detail: Optional[str] = None          # e.g. "Soil Health Card 2024", "Open-Meteo"

    @property
    def is_demo(self) -> bool:
        return self.source == DataSource.DEMO

    def label(self) -> str:
        base = {
            DataSource.MEASURED: "Measured", DataSource.MODELLED: "Modelled",
            DataSource.REMOTE_SENSING: "Remote sensing", DataSource.WEATHER_API: "Weather API",
            DataSource.USER_ENTERED: "User entered", DataSource.KNOWLEDGE_BASE: "Knowledge base",
            DataSource.REFERENCE: "Reference table", DataSource.DEMO: "DEMO DATA",
            DataSource.UNKNOWN: "Unknown source",
        }[self.source]
        return f"{base} · {self.detail}" if self.detail else base


# ----------------------------------------------------------------------------
@dataclass
class FarmerProfile:
    farmer_id: str
    name: str
    age: Optional[int] = None
    gender: Optional[str] = None                # "female" enables women-farmer schemes
    land_ownership: str = "owner"               # owner | tenant | sharecropper
    has_land_records: bool = True
    is_fpo_member: bool = False
    has_aadhaar: bool = True
    has_bank_account: bool = True
    has_soil_health_card: bool = False
    has_kcc: bool = False
    has_crop_insurance: bool = False
    annual_income_inr: Optional[float] = None
    existing_loans_inr: float = 0.0
    credit_score: Optional[int] = None
    documents_held: List[str] = field(default_factory=list)
    livestock: bool = False
    primary_objective: str = "profit"           # profit | food_security | low_risk | sustainability

    def category_attrs(self, hectares: float, vocab) -> List[str]:
        """Canonical attribute list for KB farmer-term matching."""
        attrs = ["any"]
        cat = vocab.farmer_category_from_land(hectares)
        if cat in ("Marginal Farmer", "Small Farmer"):
            attrs.append("small_marginal")
        elif cat == "Medium Farmer":
            attrs.append("medium")
        else:
            attrs.append("large")
        if self.land_ownership == "owner" and self.has_land_records:
            attrs.append("landowner")
        if self.land_ownership == "tenant":
            attrs.append("tenant")
        if self.land_ownership == "sharecropper":
            attrs.append("sharecropper")
        if (self.gender or "").lower() == "female":
            attrs.append("women")
        if self.is_fpo_member:
            attrs.append("fpo_member")
        if self.has_kcc:
            attrs.append("loanee")
        if self.livestock:
            attrs.append("livestock")
        return attrs


@dataclass
class FarmLocation:
    state: str
    district: str
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    village: Optional[str] = None
    agro_climatic_zone: Optional[str] = None
    provenance: Provenance = field(default_factory=Provenance)


@dataclass
class FieldGeometry:
    """Farm boundary as GeoJSON-like polygon (list of [lon, lat] rings)."""
    area_value: float
    area_unit: str = "acres"                    # acres | hectares
    polygon: Optional[List[List[List[float]]]] = None  # GeoJSON Polygon coordinates
    provenance: Provenance = field(default_factory=Provenance)

    @property
    def area_acres(self) -> float:
        from core.kb.vocab import Vocab
        return Vocab.acres_from(self.area_value, self.area_unit)

    @property
    def area_hectares(self) -> float:
        from core.kb.vocab import Vocab
        return Vocab.hectares_from(self.area_value, self.area_unit)

    def to_geojson(self) -> Optional[Dict[str, Any]]:
        if not self.polygon:
            return None
        return {"type": "Feature", "properties": {}, "geometry": {"type": "Polygon", "coordinates": self.polygon}}


@dataclass
class CropStatus:
    current_crop: Optional[str] = None          # crop_master name or alias
    season: Optional[str] = None                # Kharif | Rabi | Zaid (Summer)
    sowing_date: Optional[str] = None           # ISO date
    expected_harvest_date: Optional[str] = None
    previous_crop: Optional[str] = None
    variety: Optional[str] = None
    provenance: Provenance = field(default_factory=Provenance)

    def days_after_sowing(self, today: Optional[date] = None) -> Optional[int]:
        if not self.sowing_date:
            return None
        today = today or date.today()
        return (today - date.fromisoformat(self.sowing_date)).days


@dataclass
class SoilProfile:
    soil_type: Optional[str] = None             # any KB/user spelling; canonicalised by vocab
    ph: Optional[float] = None
    organic_carbon_pct: Optional[float] = None
    nitrogen_kg_ha: Optional[float] = None
    phosphorus_kg_ha: Optional[float] = None
    potassium_kg_ha: Optional[float] = None
    ec_ds_m: Optional[float] = None             # electrical conductivity (salinity)
    texture: Optional[str] = None
    depth_cm: Optional[float] = None
    moisture_pct: Optional[float] = None        # volumetric %, if sensor available
    provenance: Provenance = field(default_factory=Provenance)


@dataclass
class IrrigationProfile:
    source: Optional[str] = None                # borewell | canal | tank | rainfed | river
    method: Optional[str] = None                # flood | drip | sprinkler | furrow
    available: bool = False
    reliability: Optional[str] = None           # assured | partial | unreliable
    last_irrigation_date: Optional[str] = None
    provenance: Provenance = field(default_factory=Provenance)


@dataclass
class WeatherSnapshot:
    """Recent + forecast weather. Filled by integrations/weather; may be None."""
    observed_at: Optional[str] = None
    temp_max_c: Optional[float] = None
    temp_min_c: Optional[float] = None
    humidity_pct: Optional[float] = None
    wind_kmh: Optional[float] = None
    rain_last_7d_mm: Optional[float] = None
    rain_next_24h_mm: Optional[float] = None
    rain_next_7d_mm: Optional[float] = None
    et0_next_7d_mm: Optional[float] = None      # reference evapotranspiration
    forecast_daily: List[Dict[str, Any]] = field(default_factory=list)  # [{date,tmax,tmin,rain_mm,et0_mm}]
    annual_rainfall_normal_mm: Optional[float] = None  # long-term normal, if known
    provenance: Provenance = field(default_factory=Provenance)


@dataclass
class NDVIObservation:
    date: str
    ndvi: float
    ndwi: Optional[float] = None
    cloud_pct: Optional[float] = None


@dataclass
class RemoteSensing:
    ndvi_series: List[NDVIObservation] = field(default_factory=list)
    sensor: Optional[str] = None                # e.g. "Sentinel-2 L2A"
    provenance: Provenance = field(default_factory=Provenance)

    @property
    def latest(self) -> Optional[NDVIObservation]:
        return self.ndvi_series[-1] if self.ndvi_series else None

    @property
    def previous(self) -> Optional[NDVIObservation]:
        return self.ndvi_series[-2] if len(self.ndvi_series) >= 2 else None


@dataclass
class FinancialProfile:
    input_cost_estimate_inr: Optional[float] = None
    expected_revenue_inr: Optional[float] = None
    loan_purpose: Optional[str] = None          # crop_loan | equipment | irrigation | storage | livestock
    collateral_available: bool = False
    provenance: Provenance = field(default_factory=Provenance)


# ============================================================================
@dataclass
class FarmContext:
    """The Farm Digital Twin."""
    farm_id: str
    farm_name: str
    farmer: FarmerProfile
    location: FarmLocation
    geometry: FieldGeometry
    crop: CropStatus = field(default_factory=CropStatus)
    soil: SoilProfile = field(default_factory=SoilProfile)
    irrigation: IrrigationProfile = field(default_factory=IrrigationProfile)
    weather: WeatherSnapshot = field(default_factory=WeatherSnapshot)
    remote_sensing: RemoteSensing = field(default_factory=RemoteSensing)
    finance: FinancialProfile = field(default_factory=FinancialProfile)
    is_demo: bool = False
    notes: Optional[str] = None
    as_of: Optional[str] = None                 # ISO date the twin describes

    # ---------------------------------------------------------- convenience
    @property
    def area_acres(self) -> float:
        return self.geometry.area_acres

    @property
    def area_hectares(self) -> float:
        return self.geometry.area_hectares

    def today(self) -> date:
        return date.fromisoformat(self.as_of) if self.as_of else date.today()

    def data_sources(self) -> Dict[str, str]:
        """Provenance label per block — used by the 'Data sources' panel."""
        return {
            "location": self.location.provenance.label(),
            "geometry": self.geometry.provenance.label(),
            "crop": self.crop.provenance.label(),
            "soil": self.soil.provenance.label(),
            "irrigation": self.irrigation.provenance.label(),
            "weather": self.weather.provenance.label(),
            "remote_sensing": self.remote_sensing.provenance.label(),
            "finance": self.finance.provenance.label(),
        }

    def missing_blocks(self) -> List[str]:
        out = []
        if not self.crop.current_crop:
            out.append("current crop")
        if self.soil.soil_type is None:
            out.append("soil type")
        if self.weather.temp_max_c is None and not self.weather.forecast_daily:
            out.append("weather")
        if not self.remote_sensing.ndvi_series:
            out.append("NDVI")
        if self.farmer.annual_income_inr is None:
            out.append("annual income")
        return out

    def to_dict(self) -> Dict[str, Any]:
        return _to_plain(dataclasses.asdict(self))

    # ------------------------------------------------------------ builders
    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "FarmContext":
        def prov(x: Optional[dict]) -> Provenance:
            x = x or {}
            return Provenance(source=DataSource(x.get("source", "unknown")),
                              observed_at=x.get("observed_at"), detail=x.get("detail"))

        def build(klass, block: Optional[dict]):
            block = dict(block or {})
            names = {f.name for f in dataclasses.fields(klass)}
            if "provenance" in names:
                block["provenance"] = prov(block.get("provenance"))
            return klass(**{k: v for k, v in block.items() if k in names})

        rs_block = dict(d.get("remote_sensing") or {})
        rs_series = [NDVIObservation(**o) for o in rs_block.pop("ndvi_series", []) or []]
        rs = build(RemoteSensing, rs_block)
        rs.ndvi_series = rs_series

        return cls(
            farm_id=d["farm_id"], farm_name=d["farm_name"],
            farmer=build(FarmerProfile, d["farmer"]),
            location=build(FarmLocation, d["location"]),
            geometry=build(FieldGeometry, d["geometry"]),
            crop=build(CropStatus, d.get("crop")),
            soil=build(SoilProfile, d.get("soil")),
            irrigation=build(IrrigationProfile, d.get("irrigation")),
            weather=build(WeatherSnapshot, d.get("weather")),
            remote_sensing=rs,
            finance=build(FinancialProfile, d.get("finance")),
            is_demo=bool(d.get("is_demo", False)),
            notes=d.get("notes"), as_of=d.get("as_of"),
        )


def _to_plain(o: Any) -> Any:
    if isinstance(o, Enum):
        return o.value
    if isinstance(o, dict):
        return {k: _to_plain(v) for k, v in o.items()}
    if isinstance(o, list):
        return [_to_plain(v) for v in o]
    if isinstance(o, (date, datetime)):
        return o.isoformat()
    return o


# ----------------------------------------------------------------- loaders
def list_demo_farms(directory: Optional[Path] = None) -> List[Dict[str, str]]:
    d = directory or DEMO_FARMS_DIR
    out = []
    for p in sorted(d.glob("*.yaml")):
        with open(p, "r", encoding="utf-8") as fh:
            raw = yaml.safe_load(fh)
        out.append({"farm_id": raw["farm_id"], "farm_name": raw["farm_name"],
                    "state": raw["location"]["state"], "district": raw["location"]["district"],
                    "path": str(p)})
    return out


def load_farm_context(path: str | Path) -> FarmContext:
    with open(path, "r", encoding="utf-8") as fh:
        raw = yaml.safe_load(fh)
    return FarmContext.from_dict(raw)
