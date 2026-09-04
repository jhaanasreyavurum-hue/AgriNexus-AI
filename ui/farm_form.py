"""Farm profile editor — builds a *user-entered* FarmContext (never demo-labelled).

Only what the user actually enters is stored; blank optional fields stay None
so the engines report "not available" instead of inventing values.
"""
from __future__ import annotations

import io
from datetime import date
from typing import List, Optional

import pandas as pd
import streamlit as st

from core.models import (CropStatus, DataSource, FarmContext, FarmLocation, FarmerProfile, FieldGeometry, FinancialProfile,
                         IrrigationProfile, NDVIObservation, Provenance, RemoteSensing, SoilProfile, WeatherSnapshot)
from ui import state

OBJECTIVES = {"profit": "Maximise profit", "food_security": "Food security", "low_risk": "Low risk", "sustainability": "Sustainability"}
LOAN_PURPOSES = {None: "Not looking for credit", "crop_loan": "Crop loan / working capital", "equipment": "Equipment / tractor",
                 "irrigation": "Irrigation (drip / sprinkler / solar pump)", "storage": "Storage / post-harvest", "livestock": "Livestock / dairy",
                 "horticulture": "Horticulture / plantation", "fpo": "FPO term loan"}


def _opt_float(v: float, sentinel: float = -1.0) -> Optional[float]:
    return None if v is None or v == sentinel else float(v)


def _parse_ndvi_csv(file) -> List[NDVIObservation]:
    df = pd.read_csv(io.BytesIO(file.getvalue()))
    cols = {c.lower().strip(): c for c in df.columns}
    if "date" not in cols or "ndvi" not in cols:
        raise ValueError("CSV needs 'date' and 'ndvi' columns (optional 'ndwi').")
    out = []
    for _, r in df.iterrows():
        d = pd.to_datetime(r[cols["date"]], errors="coerce")
        v = pd.to_numeric(r[cols["ndvi"]], errors="coerce")
        if pd.isna(d) or pd.isna(v) or not (-1 <= v <= 1):
            continue
        w = pd.to_numeric(r[cols["ndwi"]], errors="coerce") if "ndwi" in cols else None
        out.append(NDVIObservation(date=d.date().isoformat(), ndvi=float(v), ndwi=None if w is None or pd.isna(w) else float(w)))
    if len(out) < 2:
        raise ValueError("Need at least two valid NDVI observations.")
    return sorted(out, key=lambda o: o.date)


def farm_editor(current: FarmContext) -> None:
    kb = state.get_kb()
    geo = kb.geo
    states = sorted(geo.state_name.unique())
    crops = sorted(kb.crops.crop_name.unique())
    soils = [v["label"] for v in kb.vocab.soil_canonical.values()]
    docs = sorted(set(kb.vocab.doc_alias_to_canonical.values()))

    st.caption("Values you enter are labelled *User entered*. Leave a field blank if you don't know it — the engines will say what is missing rather than guess.")
    with st.form("farm_form", border=False):
        c1, c2, c3 = st.columns(3)
        with c1:
            farm_name = st.text_input("Farm name *", value="" if current.is_demo else current.farm_name)
            farmer_name = st.text_input("Farmer name *", value="" if current.is_demo else current.farmer.name)
            age = st.number_input("Age", 0, 110, value=0, help="0 = not provided")
            gender = st.selectbox("Gender", ["Not specified", "female", "male", "other"])
            ownership = st.selectbox("Land ownership", ["owner", "tenant", "sharecropper"])
            objective = st.selectbox("Primary objective", list(OBJECTIVES), format_func=OBJECTIVES.get)
        with c2:
            st_ = st.selectbox("State *", states, index=states.index(current.location.state) if current.location.state in states else 0)
            dists = sorted(geo[geo.state_name == st_].district_name.unique())
            district = st.selectbox("District *", dists + ["Other (type below)"])
            district_other = st.text_input("District (if not listed)")
            area = st.number_input("Area *", 0.0, 10000.0, value=0.0, step=0.5)
            unit = st.selectbox("Unit", ["acres", "hectares"])
            crop = st.selectbox("Current crop", ["None / fallow"] + crops)
            season = st.selectbox("Season", ["Kharif", "Rabi", "Zaid (Summer)", "Year-round (Perennial)"])
            sowing = st.date_input("Sowing date", value=None, min_value=date(2015, 1, 1), max_value=date(2100, 12, 31))
            prev_crop = st.selectbox("Previous crop", ["Unknown"] + crops)
        with c3:
            soil = st.selectbox("Soil type", ["Unknown"] + soils)
            ph = st.number_input("Soil pH (blank = -1)", -1.0, 14.0, value=-1.0, step=0.1)
            oc = st.number_input("Organic carbon % (blank = -1)", -1.0, 10.0, value=-1.0, step=0.01)
            n = st.number_input("Available N kg/ha (blank = -1)", -1.0, 2000.0, value=-1.0, step=5.0)
            p = st.number_input("Available P kg/ha (blank = -1)", -1.0, 500.0, value=-1.0, step=1.0)
            k = st.number_input("Available K kg/ha (blank = -1)", -1.0, 2000.0, value=-1.0, step=5.0)
            irrigated = st.checkbox("Irrigation available")
            irr_source = st.selectbox("Irrigation source", ["borewell", "canal", "tank", "river", "rainfed"])
            irr_method = st.selectbox("Irrigation method", ["flood", "furrow", "drip", "sprinkler"])
            irr_rel = st.selectbox("Irrigation reliability", ["partial", "assured", "unreliable"])
            last_irr = st.date_input("Last irrigation date", value=None)
        st.markdown("**Finance & documents**")
        f1, f2, f3 = st.columns(3)
        with f1:
            income = st.number_input("Annual household income ₹ (0 = not provided)", 0, 100_000_000, value=0, step=10_000)
            loans = st.number_input("Existing farm loans ₹", 0, 100_000_000, value=0, step=10_000)
            purpose = st.selectbox("Credit need", list(LOAN_PURPOSES), format_func=LOAN_PURPOSES.get)
            collateral = st.checkbox("Collateral available")
        with f2:
            has_aadhaar = st.checkbox("Aadhaar", value=True)
            has_bank = st.checkbox("Bank account", value=True)
            has_records = st.checkbox("Land records in hand", value=True)
            has_shc = st.checkbox("Soil Health Card")
            has_kcc = st.checkbox("Holds a KCC")
            has_ins = st.checkbox("Crop currently insured")
            fpo = st.checkbox("FPO / SHG member")
            livestock = st.checkbox("Keeps livestock")
        with f3:
            held = st.multiselect("Documents held", docs)
            ndvi_file = st.file_uploader("NDVI series CSV (date, ndvi[, ndwi])", type=["csv"], help="Optional. Real satellite integration can be added later; uploaded series are labelled Remote sensing · user upload.")
        submitted = st.form_submit_button("Save & assess this farm", type="primary")

    if not submitted:
        return
    errors = []
    if not farm_name.strip():
        errors.append("Farm name is required.")
    if not farmer_name.strip():
        errors.append("Farmer name is required.")
    if area <= 0:
        errors.append("Area must be greater than zero.")
    dist_final = district_other.strip() if district == "Other (type below)" else district
    if not dist_final:
        errors.append("District is required.")
    if sowing and sowing > date.today():
        errors.append("Sowing date cannot be in the future.")
    if crop == "None / fallow" and sowing:
        errors.append("Sowing date given but no crop selected.")
    ndvi_series: List[NDVIObservation] = []
    if ndvi_file is not None:
        try:
            ndvi_series = _parse_ndvi_csv(ndvi_file)
        except Exception as exc:
            errors.append(f"NDVI CSV: {exc}")
    if errors:
        for e in errors:
            st.error(e)
        return

    user = Provenance(source=DataSource.USER_ENTERED, observed_at=date.today().isoformat())
    row = geo[(geo.state_name == st_) & (geo.district_name == dist_final)]
    lat = float(row.iloc[0].latitude) if len(row) else None
    lon = float(row.iloc[0].longitude) if len(row) else None
    zone = str(row.iloc[0].agriculture_zone) if len(row) else None
    ctx = FarmContext(
        farm_id="USER_" + "".join(ch for ch in farm_name.upper() if ch.isalnum())[:24],
        farm_name=farm_name.strip(),
        farmer=FarmerProfile(farmer_id="USER", name=farmer_name.strip(), age=age or None, gender=None if gender == "Not specified" else gender,
                             land_ownership=ownership, has_land_records=has_records, is_fpo_member=fpo, has_aadhaar=has_aadhaar,
                             has_bank_account=has_bank, has_soil_health_card=has_shc, has_kcc=has_kcc, has_crop_insurance=has_ins,
                             annual_income_inr=float(income) if income > 0 else None, existing_loans_inr=float(loans), documents_held=list(held),
                             livestock=livestock, primary_objective=objective),
        location=FarmLocation(state=st_, district=dist_final, latitude=lat, longitude=lon, agro_climatic_zone=zone,
                              provenance=Provenance(source=DataSource.KNOWLEDGE_BASE if lat is not None else DataSource.USER_ENTERED,
                                                    detail="state_district_master (district centroid)" if lat is not None else "district not in KB — no coordinates")),
        geometry=FieldGeometry(area_value=float(area), area_unit=unit, provenance=user),
        crop=CropStatus(current_crop=None if crop == "None / fallow" else crop, season=season, sowing_date=sowing.isoformat() if sowing else None,
                        previous_crop=None if prev_crop == "Unknown" else prev_crop, provenance=user),
        soil=SoilProfile(soil_type=None if soil == "Unknown" else soil, ph=_opt_float(ph), organic_carbon_pct=_opt_float(oc), nitrogen_kg_ha=_opt_float(n),
                         phosphorus_kg_ha=_opt_float(p), potassium_kg_ha=_opt_float(k), provenance=user),
        irrigation=IrrigationProfile(source=irr_source if irrigated else "rainfed", method=irr_method if irrigated else None, available=irrigated,
                                     reliability=irr_rel if irrigated else None, last_irrigation_date=last_irr.isoformat() if (irrigated and last_irr) else None, provenance=user),
        weather=WeatherSnapshot(provenance=Provenance(source=DataSource.UNKNOWN, detail="fetched live when weather mode is on")),
        remote_sensing=RemoteSensing(ndvi_series=ndvi_series, sensor="user upload" if ndvi_series else None,
                                     provenance=Provenance(source=DataSource.REMOTE_SENSING if ndvi_series else DataSource.UNKNOWN,
                                                           detail="user-uploaded NDVI CSV" if ndvi_series else "no NDVI series")),
        finance=FinancialProfile(loan_purpose=purpose, collateral_available=collateral, provenance=user),
        is_demo=False, as_of=date.today().isoformat(),
    )
    state.set_context(ctx)
    st.success(f"Saved **{ctx.farm_name}** — assessment below uses your data (weather {'live' if st.session_state.get('weather_mode') == 'live' else 'off'}).")
    st.rerun()
