"""Farmer onboarding: Farmer Profile → Farm Details → Financial Details → Analyze My Farm.

Only fields the engines actually use are asked. Everything left blank stays
None so results say "not assessed" instead of guessing. Builds a *user-entered*
FarmContext and hands it to ``state.set_context``; no reasoning happens here.
"""
from __future__ import annotations

from datetime import date
from typing import Any, Dict, Optional

import streamlit as st

from core.models import (CropStatus, DataSource, FarmContext, FarmLocation, FarmerProfile, FieldGeometry, FinancialProfile,
                         IrrigationProfile, Provenance, RemoteSensing, SoilProfile, WeatherSnapshot)
from ui import state
from ui.components import md, esc, badge

LOAN_PURPOSES = {"crop_loan": "Crop loan / working capital", "equipment": "Equipment / tractor", "irrigation": "Irrigation (drip / sprinkler / solar pump)",
                 "storage": "Storage / post-harvest", "livestock": "Livestock / dairy", "horticulture": "Horticulture / plantation", "fpo": "FPO term loan",
                 None: "Not looking for credit right now"}
STEPS = ["Farmer profile", "Farm details", "Financial details", "Analyze"]


def _ob() -> Dict[str, Any]:
    return st.session_state.setdefault("onboard", {"step": 0, "data": {}})


def _progress(step: int) -> None:
    cells = []
    for i, s in enumerate(STEPS):
        kind = "green" if i < step else ("blue" if i == step else "grey")
        cells.append(badge(f"{i + 1}. {s}", kind))
    md('<div style="margin:.2rem 0 .8rem 0">' + "".join(cells) + "</div>")


def _step_profile(d: Dict[str, Any], kb) -> bool:
    geo = kb.geo
    states = sorted(geo.state_name.unique())
    # state sits outside the form so the district list refreshes immediately
    st_ = st.selectbox("State *", states, index=states.index(d["state"]) if d.get("state") in states else (states.index("Telangana") if "Telangana" in states else 0), key="ob_state")
    with st.form("ob_profile", border=False):
        c1, c2 = st.columns(2)
        with c1:
            name = st.text_input("Your name *", value=d.get("name", ""))
            gender = st.selectbox("Gender", ["Prefer not to say", "female", "male", "other"], index=["Prefer not to say", "female", "male", "other"].index(d.get("gender") or "Prefer not to say"),
                                  help="Women-farmer schemes are matched when 'female' is selected.")
            age = st.number_input("Age", 0, 110, value=int(d.get("age") or 0), help="0 = not provided. Some schemes have age limits (e.g. PM-KMY 18–40).")
        with c2:
            dists = sorted(geo[geo.state_name == st_].district_name.unique())
            opts = dists + ["Other (type below)"]
            district = st.selectbox("District *", opts, index=opts.index(d["district"]) if d.get("district") in opts else 0)
            district_other = st.text_input("District (if not listed)", value=d.get("district_other", ""))
        ownership = st.radio("Land ownership", ["owner", "tenant", "sharecropper"], index=["owner", "tenant", "sharecropper"].index(d.get("ownership", "owner")), horizontal=True)
        st.caption("State is the first thing the knowledge base uses (deep coverage: Telangana; moderate: Maharashtra; other states: national schemes only). Farmer category (marginal/small/…) is derived from land size in the next step — you don't need to enter it.")
        ok = st.form_submit_button("Continue → Farm details", type="primary")
    if ok:
        errs = []
        if not name.strip():
            errs.append("Name is required.")
        dist_final = district_other.strip() if district == "Other (type below)" else district
        if not dist_final:
            errs.append("District is required.")
        if errs:
            for e in errs:
                st.error(e)
            return False
        d.update(name=name.strip(), state=st_, district=district, district_other=district_other, district_final=dist_final,
                 gender=None if gender == "Prefer not to say" else gender, age=int(age) or None, ownership=ownership)
        return True
    return False


def _step_farm(d: Dict[str, Any], kb) -> bool:
    crops = sorted(kb.crops.crop_name.unique())
    soils = [v["label"] for v in kb.vocab.soil_canonical.values()]
    with st.form("ob_farm", border=False):
        c1, c2 = st.columns(2)
        with c1:
            area = st.number_input("Land holding *", 0.0, 10000.0, value=float(d.get("area", 0.0)), step=0.5)
            unit = st.selectbox("Unit", ["acres", "hectares"], index=["acres", "hectares"].index(d.get("unit", "acres")))
            crop_opts = ["None / fallow"] + crops
            crop = st.selectbox("Current / planned crop", crop_opts, index=crop_opts.index(d["crop"]) if d.get("crop") in crop_opts else 0)
            seasons = ["Kharif", "Rabi", "Zaid (Summer)", "Year-round (Perennial)"]
            season = st.selectbox("Season", seasons, index=seasons.index(d.get("season", "Kharif")))
            sowing = st.date_input("Sowing date (if sown)", value=d.get("sowing"), min_value=date(2015, 1, 1), max_value=date(2100, 12, 31))
        with c2:
            irrigated = st.checkbox("Irrigation available", value=d.get("irrigated", False))
            irr_source = st.selectbox("Irrigation source", ["borewell", "canal", "tank", "river"], index=["borewell", "canal", "tank", "river"].index(d.get("irr_source", "borewell")))
            irr_rel = st.selectbox("Irrigation reliability", ["partial", "assured", "unreliable"], index=["partial", "assured", "unreliable"].index(d.get("irr_rel", "partial")))
            soil_opts = ["Unknown"] + soils
            soil = st.selectbox("Soil type", soil_opts, index=soil_opts.index(d["soil"]) if d.get("soil") in soil_opts else 0)
            livestock = st.checkbox("I also keep livestock (dairy / small ruminants / poultry)", value=d.get("livestock", False))
        st.caption("Soil test values, NDVI uploads and other advanced inputs can be added later in Crop / Farm Intelligence → Edit farm.")
        b1, b2 = st.columns([1, 5])
        back = b1.form_submit_button("← Back")
        ok = b2.form_submit_button("Continue → Financial details", type="primary")
    if back:
        _ob()["step"] = 0
        st.rerun()
    if ok:
        errs = []
        if area <= 0:
            errs.append("Land holding must be greater than zero.")
        if sowing and sowing > date.today():
            errs.append("Sowing date cannot be in the future.")
        if crop == "None / fallow" and sowing:
            errs.append("Sowing date given but no crop selected.")
        if errs:
            for e in errs:
                st.error(e)
            return False
        d.update(area=float(area), unit=unit, crop=crop, season=season, sowing=sowing, irrigated=irrigated, irr_source=irr_source,
                 irr_rel=irr_rel, soil=soil, livestock=livestock)
        return True
    return False


def _step_finance(d: Dict[str, Any], kb) -> bool:
    docs = sorted(set(kb.vocab.doc_alias_to_canonical.values()))
    with st.form("ob_fin", border=False):
        c1, c2 = st.columns(2)
        with c1:
            income = st.number_input("Annual household income ₹ (0 = not provided)", 0, 100_000_000, value=int(d.get("income", 0)), step=10_000,
                                     help="Used for scheme income limits and loan coverage — not shared anywhere.")
            loans = st.number_input("Existing farm loans outstanding ₹", 0, 100_000_000, value=int(d.get("loans", 0)), step=10_000)
            keys = list(LOAN_PURPOSES)
            purpose = st.selectbox("What do you need credit for?", keys, index=keys.index(d.get("purpose", "crop_loan")), format_func=LOAN_PURPOSES.get)
            collateral = st.checkbox("I can offer collateral (land / gold / FD)", value=d.get("collateral", False))
        with c2:
            has_kcc = st.checkbox("I already hold a Kisan Credit Card", value=d.get("has_kcc", False))
            has_ins = st.checkbox("My crop is currently insured", value=d.get("has_ins", False))
            fpo = st.checkbox("FPO / SHG member", value=d.get("fpo", False))
            has_shc = st.checkbox("I have a Soil Health Card", value=d.get("has_shc", False))
            credit_hist = st.selectbox("Repayment history (self-declared)", ["Not specified", "No previous loans", "Regular repayment", "Some delays", "Defaulted / NPA"],
                                       index=["Not specified", "No previous loans", "Regular repayment", "Some delays", "Defaulted / NPA"].index(d.get("credit_hist", "Not specified")))
        held = st.multiselect("Documents you have in hand", docs, default=[x for x in d.get("held", ["Aadhaar Card", "Bank Statement (6 months)"]) if x in docs],
                              help="Aadhaar and bank account are assumed unless you untick below. Land records matter most for loans.")
        c3, c4, c5 = st.columns(3)
        has_aadhaar = c3.checkbox("Aadhaar", value=d.get("has_aadhaar", True))
        has_bank = c4.checkbox("Bank account", value=d.get("has_bank", True))
        has_records = c5.checkbox("Land records (pattadar passbook / RoR)", value=d.get("has_records", d.get("ownership") == "owner"))
        b1, b2 = st.columns([1, 5])
        back = b1.form_submit_button("← Back")
        ok = b2.form_submit_button("🔎 Analyze My Farm", type="primary")
    if back:
        _ob()["step"] = 1
        st.rerun()
    if ok:
        d.update(income=int(income), loans=int(loans), purpose=purpose, collateral=collateral, has_kcc=has_kcc, has_ins=has_ins, fpo=fpo, has_shc=has_shc,
                 credit_hist=credit_hist, held=list(held), has_aadhaar=has_aadhaar, has_bank=has_bank, has_records=has_records)
        return True
    return False


def build_context(d: Dict[str, Any], kb, farmer_id: str) -> FarmContext:
    geo = kb.geo
    user = Provenance(source=DataSource.USER_ENTERED, observed_at=date.today().isoformat())
    row = geo[(geo.state_name == d["state"]) & (geo.district_name == d["district_final"])]
    lat = float(row.iloc[0].latitude) if len(row) else None
    lon = float(row.iloc[0].longitude) if len(row) else None
    zone = str(row.iloc[0].agriculture_zone) if len(row) else None
    crop = None if d.get("crop") in (None, "None / fallow") else d["crop"]
    notes = None
    if d.get("credit_hist") and d["credit_hist"] != "Not specified":
        notes = f"Self-declared repayment history: {d['credit_hist']}"
    return FarmContext(
        farm_id=f"USER_{farmer_id.upper()}"[:40],
        farm_name=f"{d['name']}'s farm — {d['district_final']}",
        farmer=FarmerProfile(farmer_id=farmer_id, name=d["name"], age=d.get("age"), gender=d.get("gender"), land_ownership=d.get("ownership", "owner"),
                             has_land_records=bool(d.get("has_records", True)), is_fpo_member=bool(d.get("fpo")), has_aadhaar=bool(d.get("has_aadhaar", True)),
                             has_bank_account=bool(d.get("has_bank", True)), has_soil_health_card=bool(d.get("has_shc")), has_kcc=bool(d.get("has_kcc")),
                             has_crop_insurance=bool(d.get("has_ins")), annual_income_inr=float(d["income"]) if d.get("income") else None,
                             existing_loans_inr=float(d.get("loans") or 0), documents_held=list(d.get("held", [])), livestock=bool(d.get("livestock")), primary_objective="profit"),
        location=FarmLocation(state=d["state"], district=d["district_final"], latitude=lat, longitude=lon, agro_climatic_zone=zone,
                              provenance=Provenance(source=DataSource.KNOWLEDGE_BASE if lat is not None else DataSource.USER_ENTERED,
                                                    detail="state_district_master (district centroid)" if lat is not None else "district not in KB — no coordinates")),
        geometry=FieldGeometry(area_value=float(d["area"]), area_unit=d.get("unit", "acres"), provenance=user),
        crop=CropStatus(current_crop=crop, season=d.get("season"), sowing_date=d["sowing"].isoformat() if d.get("sowing") else None, provenance=user),
        soil=SoilProfile(soil_type=None if d.get("soil") in (None, "Unknown") else d["soil"], provenance=user),
        irrigation=IrrigationProfile(source=d.get("irr_source") if d.get("irrigated") else "rainfed", available=bool(d.get("irrigated")),
                                     reliability=d.get("irr_rel") if d.get("irrigated") else None, provenance=user),
        weather=WeatherSnapshot(provenance=Provenance(source=DataSource.UNKNOWN, detail="fetched live when weather mode is on")),
        remote_sensing=RemoteSensing(provenance=Provenance(source=DataSource.UNKNOWN, detail="no NDVI series")),
        finance=FinancialProfile(loan_purpose=d.get("purpose"), collateral_available=bool(d.get("collateral")), provenance=user),
        is_demo=False, as_of=date.today().isoformat(), notes=notes,
    )


def render(user, kb) -> bool:
    """Render the wizard. Returns True once a context has been created."""
    ob = _ob()
    step, d = ob["step"], ob["data"]
    st.subheader("Set up your farm profile")
    st.caption("Four short steps. Only information the matching engines use is requested; anything you skip is reported as 'not provided' rather than assumed.")
    _progress(step)
    if step == 0:
        if _step_profile(d, kb):
            ob["step"] = 1
            st.rerun()
    elif step == 1:
        if _step_farm(d, kb):
            ob["step"] = 2
            st.rerun()
    elif step == 2:
        if _step_finance(d, kb):
            ctx = build_context(d, kb, user.username)
            state.set_context(ctx)
            ob["step"] = 3
            st.session_state["just_analyzed"] = True
            st.rerun()
    return False
