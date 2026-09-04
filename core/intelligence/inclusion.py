"""Financial-Inclusion & Scheme-Monitoring intelligence (government-officer role) — MODELLED.

"Adoption" in the KB sense is *modelled reach*: the share of scenario
households for which a scheme scores as eligible. There is no observed
enrolment data in the knowledge base; officers can upload observed adoption
figures (session-only) which are then compared against modelled reach to
produce an adoption gap.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd

from core.auth import Permission, User, authorize
from .matrix import SegmentMatrix
from .scenario import Scenario, DEFAULT_SCENARIO
from .segments import SEGMENT_BY_ID

BASIS = "MODELLED (KB-derived)"


@dataclass
class InclusionIntelligence:
    scope_state: Optional[str]
    scenario_label: str
    basis: str
    kpis: Dict[str, Any]
    by_district: pd.DataFrame
    by_scheme: pd.DataFrame
    by_segment: pd.DataFrame
    by_crop_scheme: pd.DataFrame
    low_adoption: pd.DataFrame
    notes: List[str] = field(default_factory=list)
    stale: bool = False
    available: bool = True


def _weighted(df: pd.DataFrame, scenario: Scenario) -> pd.DataFrame:
    shares = scenario.normalised_shares()
    d = df.copy()
    d["share"] = d["segment_id"].map(shares).fillna(0.0)
    d["households"] = d["district"].map(lambda x: scenario.households_for(x)) * d["share"]
    for c in ("n_schemes_eligible", "n_subsidies", "n_insurance", "n_loan_products_eligible", "subsidy_max_total_inr"):
        d[c] = pd.to_numeric(d[c], errors="coerce").fillna(0)
    d["scheme_reach_flag"] = d["n_schemes_eligible"] > 0
    d["credit_reach_flag"] = (d["n_loan_products_eligible"] > 0) & (d["loan_rating"] != "Limited")
    d["insurance_reach_flag"] = d["crop_cover_available"].astype(bool)
    d["subsidy_reach_flag"] = d["n_subsidies"] > 0
    # graded pillars (0-1) so the index discriminates between profiles, not just presence/absence:
    #   scheme depth (≥12 eligible schemes = full), credit rating (Good 1 / Moderate .6 / Limited .2),
    #   insurance (crop cover notified for the district's crop, or livestock cover for allied profiles), subsidy depth (≥3 = full)
    d["p_scheme"] = np.clip(d["n_schemes_eligible"] / 12.0, 0, 1)
    d["p_credit"] = d["loan_rating"].map({"Good": 1.0, "Moderate": 0.6, "Limited": 0.2}).fillna(0.0)
    d["p_insurance"] = np.where(d["insurance_reach_flag"], 1.0, np.where(d["n_insurance"] > 0, 0.5, 0.0))
    d["p_subsidy"] = np.clip(d["n_subsidies"] / 3.0, 0, 1)
    d["inclusion_index"] = 25 * (d["p_scheme"] + d["p_credit"] + d["p_insurance"] + d["p_subsidy"])
    return d


def _scheme_rows(w: pd.DataFrame, min_score: float) -> pd.DataFrame:
    rows = []
    for _, r in w.iterrows():
        try:
            items = json.loads(r["schemes_json"]) if isinstance(r["schemes_json"], str) else []
        except Exception:
            items = []
        for s in items:
            if (s.get("score") or 0) >= min_score:
                rows.append({"scheme": s["title"], "scheme_type": s.get("type"), "level": s.get("level"), "score": s["score"],
                             "households": r["households"], "district": r["district"], "segment_id": r["segment_id"], "crop": r["crop"]})
    return pd.DataFrame(rows, columns=["scheme", "scheme_type", "level", "score", "households", "district", "segment_id", "crop"])


def _district_table(w: pd.DataFrame, observed: Optional[pd.DataFrame]) -> pd.DataFrame:
    g = w.groupby(["state", "district"], as_index=False).agg(
        crop=("crop", "first"), households=("households", "sum"),
        scheme_reach=("households", lambda s: float((s * w.loc[s.index, "scheme_reach_flag"]).sum())),
        credit_reach=("households", lambda s: float((s * w.loc[s.index, "credit_reach_flag"]).sum())),
        insurance_reach=("households", lambda s: float((s * w.loc[s.index, "insurance_reach_flag"]).sum())),
        subsidy_reach=("households", lambda s: float((s * w.loc[s.index, "subsidy_reach_flag"]).sum())),
        avg_schemes=("n_schemes_eligible", "mean"), avg_subsidies=("n_subsidies", "mean"), branches=("branches_in_district", "max"), coverage=("coverage", "first"),
        p_scheme=("p_scheme", "mean"), p_credit=("p_credit", "mean"), p_insurance=("p_insurance", "mean"), p_subsidy=("p_subsidy", "mean"),
        inclusion_index=("inclusion_index", lambda s: float(np.average(s, weights=w.loc[s.index, "households"])) if w.loc[s.index, "households"].sum() else float(s.mean())),
    )
    for c in ("scheme", "credit", "insurance", "subsidy"):
        g[f"{c}_reach_pct"] = np.where(g["households"] > 0, 100 * g[f"{c}_reach"] / g["households"], 0.0)
    g["inclusion_index"] = g["inclusion_index"].round(1)
    # absolute band + relative rank within the scope (KB coverage makes states internally homogeneous, so the
    # relative rank is what an officer uses to prioritise; both are shown)
    g["performance"] = pd.cut(g["inclusion_index"], [-1, 55, 75, 101], labels=["Low", "Medium", "High"]).astype(str)
    g["rank"] = g["inclusion_index"].rank(ascending=False, method="min").astype(int)
    n = max(len(g), 1)
    g["relative_band"] = pd.cut(g["rank"], [0, max(1, round(n / 3)), max(2, round(2 * n / 3)), n], labels=["Upper third", "Middle third", "Lower third"]).astype(str)
    if observed is not None and len(observed):
        g = g.merge(observed, on="district", how="left")
        g["adoption_gap_pct"] = g["scheme_reach_pct"] - g["observed_adoption_pct"]
    else:
        g["observed_adoption_pct"] = np.nan
        g["adoption_gap_pct"] = np.nan
    return g.sort_values("inclusion_index", ascending=False).reset_index(drop=True)


def _scheme_table(sr: pd.DataFrame, total_hh: float) -> pd.DataFrame:
    if sr.empty:
        return pd.DataFrame(columns=["scheme", "scheme_type", "level", "modelled_reach_households", "reach_pct", "avg_score", "districts"])
    g = sr.groupby(["scheme", "scheme_type", "level"], as_index=False).agg(modelled_reach_households=("households", "sum"), avg_score=("score", "mean"), districts=("district", "nunique"))
    g["reach_pct"] = 100 * g["modelled_reach_households"] / (total_hh or 1)
    return g.sort_values("modelled_reach_households", ascending=False).reset_index(drop=True)


def _segment_table(w: pd.DataFrame) -> pd.DataFrame:
    g = w.groupby(["segment_id", "segment_label", "segment_group"], as_index=False).agg(
        households=("households", "sum"), avg_schemes=("n_schemes_eligible", "mean"), avg_subsidies=("n_subsidies", "mean"),
        inclusion_index=("inclusion_index", "mean"),
        scheme_reach_pct=("scheme_reach_flag", lambda s: 100 * float(s.mean())), credit_reach_pct=("credit_reach_flag", lambda s: 100 * float(s.mean())),
        insurance_reach_pct=("insurance_reach_flag", lambda s: 100 * float(s.mean())), subsidy_reach_pct=("subsidy_reach_flag", lambda s: 100 * float(s.mean())),
        top_scheme=("top_scheme", lambda s: s.mode().iat[0] if len(s.mode()) else None))
    g["tags"] = g["segment_id"].map(lambda i: ", ".join(SEGMENT_BY_ID[i].tags) if i in SEGMENT_BY_ID else "")
    return g.sort_values("inclusion_index").reset_index(drop=True)


def _crop_scheme_table(sr: pd.DataFrame) -> pd.DataFrame:
    d = sr[sr["crop"].notna()]
    if d.empty:
        return pd.DataFrame(columns=["crop", "scheme", "households", "avg_score"])
    g = d.groupby(["crop", "scheme"], as_index=False).agg(households=("households", "sum"), avg_score=("score", "mean"))
    return g.sort_values(["crop", "households"], ascending=[True, False]).reset_index(drop=True)


def inclusion_intelligence(user: User, kb, matrix: SegmentMatrix, state: Optional[str] = None, scenario: Scenario = DEFAULT_SCENARIO,
                           observed_adoption: Optional[pd.DataFrame] = None, segment_tags: Optional[List[str]] = None) -> InclusionIntelligence:
    """Government-officer analytics. ``observed_adoption`` (optional): columns district, observed_adoption_pct."""
    authorize(user, Permission.SCHEME_ANALYTICS, "view scheme adoption & financial-inclusion analytics")
    notes = [f"Basis: {scenario.basis}. 'Adoption' figures are modelled reach (share of scenario households for which the KB scores a scheme as eligible), not enrolment records.",
             "Inclusion index (0-100) = 25 × [scheme depth + credit rating + insurance cover + subsidy depth] per profile, weighted by scenario household share."]
    if not matrix.available:
        empty = pd.DataFrame()
        return InclusionIntelligence(state, scenario.label, BASIS, {}, empty, empty, empty, empty, empty,
                                     notes + ["Segment matrix not built — run scripts/build_segment_matrix.py."], stale=True, available=False)
    d = matrix.districts(state)
    if segment_tags:
        keep = {sid for sid, s in SEGMENT_BY_ID.items() if set(segment_tags) & set(s.tags)}
        d = d[d["segment_id"].isin(keep)]
    w = _weighted(d, scenario)
    obs = None
    if observed_adoption is not None and {"district", "observed_adoption_pct"} <= set(observed_adoption.columns):
        obs = observed_adoption[["district", "observed_adoption_pct"]].copy()
        obs["observed_adoption_pct"] = pd.to_numeric(obs["observed_adoption_pct"], errors="coerce")
        notes.append("Observed adoption column supplied by the user (session-only upload) — gap = modelled reach − observed adoption.")
    dist = _district_table(w, obs) if len(w) else pd.DataFrame()
    sr = _scheme_rows(w, scenario.eligible_min_scheme_score)
    hh = float(w["households"].sum()) if len(w) else 0.0
    sch = _scheme_table(sr, hh)
    seg = _segment_table(w) if len(w) else pd.DataFrame()
    cs = _crop_scheme_table(sr)
    low = dist[dist["performance"] == "Low"].copy() if len(dist) else pd.DataFrame()
    if len(dist):
        low = dist.sort_values("inclusion_index").head(max(5, int(0.3 * len(dist)))).copy()
        weakest = low[["p_scheme", "p_credit", "p_insurance", "p_subsidy"]].idxmin(axis=1)
        low["weakest_pillar"] = weakest.map({"p_scheme": "Scheme depth", "p_credit": "Credit access", "p_insurance": "Insurance cover", "p_subsidy": "Subsidy depth"})
        low["intervention"] = weakest.map({"p_insurance": "Notify crop cover for the major crop / PMFBY enrolment drive",
                                           "p_credit": "KCC saturation camp; tenant-farmer / cultivator certificates",
                                           "p_subsidy": "State subsidy awareness + micro-irrigation / mechanisation camps",
                                           "p_scheme": "Scheme awareness camps; KB lacks state schemes here (limited coverage)"})
    kpis = {
        "districts": int(w["district"].nunique()) if len(w) else 0,
        "households_modelled": hh,
        "scheme_reach_pct": 100 * float((w["households"] * w["scheme_reach_flag"]).sum()) / hh if hh else 0.0,
        "credit_reach_pct": 100 * float((w["households"] * w["credit_reach_flag"]).sum()) / hh if hh else 0.0,
        "insurance_reach_pct": 100 * float((w["households"] * w["insurance_reach_flag"]).sum()) / hh if hh else 0.0,
        "subsidy_reach_pct": 100 * float((w["households"] * w["subsidy_reach_flag"]).sum()) / hh if hh else 0.0,
        "inclusion_index": float(np.average(w["inclusion_index"], weights=w["households"])) if hh else 0.0,
        "schemes_active": int(len(sch)),
        "top_scheme": sch.iloc[0]["scheme"] if len(sch) else None,
        "low_districts": int(len(low)),
        "avg_schemes_per_household": float(np.average(w["n_schemes_eligible"], weights=w["households"])) if hh else 0.0,
        "weakest_segment": seg.iloc[0]["segment_label"] if len(seg) else None,
    }
    if matrix.stale:
        notes.append("Segment matrix was built with an earlier KB/override version — rebuild for current figures.")
    if state and kb.coverage_level(state) != "deep":
        notes.append(f"KB coverage for {state} is {kb.coverage_level(state)}: only central schemes are in the KB for this state, so reach is understated relative to Telangana.")
    return InclusionIntelligence(state, scenario.label, BASIS, kpis, dist, sch, seg, cs, low, notes, stale=matrix.stale)
