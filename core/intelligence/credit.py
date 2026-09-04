"""Agricultural Credit Intelligence (bank-manager role) — MODELLED from the segment matrix.

All quantities are derived by weighting per-segment KB eligibility by scenario
household shares. Nothing here is an observed statistic.
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
class CreditIntelligence:
    scope_state: Optional[str]
    scenario_label: str
    basis: str
    kpis: Dict[str, Any]
    by_district: pd.DataFrame          # district ranking
    by_segment: pd.DataFrame           # segment distribution
    by_crop: pd.DataFrame              # crop grid (state) or district major crops
    by_product: pd.DataFrame           # product / loan-type demand
    by_bank: pd.DataFrame              # bank presence vs modelled product wins
    notes: List[str] = field(default_factory=list)
    stale: bool = False
    available: bool = True


def _weighted(df: pd.DataFrame, scenario: Scenario) -> pd.DataFrame:
    """Attach household weights (scenario shares × households per district)."""
    shares = scenario.normalised_shares()
    d = df.copy()
    d["share"] = d["segment_id"].map(shares).fillna(0.0)
    d["households"] = d["district"].map(lambda x: scenario.households_for(x)) * d["share"]
    d["loan_est_inr"] = pd.to_numeric(d["loan_est_inr"], errors="coerce").fillna(0.0)
    d["eligible_flag"] = (pd.to_numeric(d["n_loan_products_eligible"], errors="coerce").fillna(0) > 0) & (d["loan_rating"] != "Limited")
    d["eligible_households"] = d["households"] * d["eligible_flag"]
    d["demand_inr"] = d["eligible_households"] * d["loan_est_inr"]
    d["doc_readiness"] = pd.to_numeric(d["top_loan_doc_readiness_pct"], errors="coerce")
    d["fit_score"] = pd.to_numeric(d["top_loan_score"], errors="coerce").fillna(0.0)      # best product match score (0-100)
    d["rating_score"] = pd.to_numeric(d["loan_rating_score"], errors="coerce").fillna(0.0)
    d["crop_cover_available"] = d["crop_cover_available"].astype(bool)
    d["n_subsidies"] = pd.to_numeric(d["n_subsidies"], errors="coerce").fillna(0)
    return d


def _potential_label(score: float) -> str:
    return "High" if score >= 67 else ("Medium" if score >= 40 else "Low")


def _district_table(w: pd.DataFrame) -> pd.DataFrame:
    g = w.groupby(["state", "district"], as_index=False).agg(
        crop=("crop", "first"), households=("households", "sum"), eligible_households=("eligible_households", "sum"),
        demand_inr=("demand_inr", "sum"), avg_loan_est_inr=("loan_est_inr", lambda s: float(np.average(s, weights=w.loc[s.index, "households"]) if w.loc[s.index, "households"].sum() else s.mean())),
        branches=("branches_in_district", "max"), loan_desks=("branches_loan_desk", "max"),
        crop_cover=("crop_cover_available", "max"), avg_schemes=("n_schemes_eligible", "mean"), coverage=("coverage", "first"),
        doc_readiness=("doc_readiness", "mean"), fit_score=("fit_score", "mean"), rating_score=("rating_score", "mean"),
        avg_subsidies=("n_subsidies", "mean"),
    )
    g["eligible_pct"] = np.where(g["households"] > 0, 100 * g["eligible_households"] / g["households"], 0.0)
    g["demand_per_10k_inr"] = np.where(g["households"] > 0, g["demand_inr"] / g["households"] * 10_000, 0.0)
    # Potential score (0-100), all KB-derived signals:
    #   30 demand depth (modelled demand per household vs best district) · 25 product fit (best match score)
    #   15 credit-risk cover (a crop insurance cover is notified for the district's major crop)
    #   30 under-served bonus (few KB agri-loan desks relative to demand → untapped)
    dmax = g["demand_per_10k_inr"].max() or 1.0
    access_gap = np.clip(1 - g["loan_desks"] / 8.0, 0, 1)
    g["potential_score"] = (30 * g["demand_per_10k_inr"] / dmax + 25 * g["fit_score"] / 100 + 15 * g["crop_cover"].astype(float) + 30 * access_gap).round(1)
    g["potential"] = g["potential_score"].map(_potential_label)
    g["credit_opportunity"] = np.where((g["loan_desks"] == 0) & (g["demand_inr"] > 0), "No KB branch desk — untapped",
                                       np.where(g["loan_desks"] <= 3, "Thin branch presence", "Served"))
    return g.sort_values("potential_score", ascending=False).reset_index(drop=True)


def _segment_table(w: pd.DataFrame) -> pd.DataFrame:
    g = w.groupby(["segment_id", "segment_label", "segment_group"], as_index=False).agg(
        households=("households", "sum"), eligible_households=("eligible_households", "sum"), demand_inr=("demand_inr", "sum"),
        avg_loan_est_inr=("loan_est_inr", "mean"), avg_products=("n_loan_products_eligible", "mean"),
        top_product=("top_loan_product", lambda s: s.mode().iat[0] if len(s.mode()) else None),
        top_loan_type=("top_loan_type", lambda s: s.mode().iat[0] if len(s.mode()) else None),
        rating=("loan_rating", lambda s: s.mode().iat[0] if len(s.mode()) else None), doc_readiness=("doc_readiness", "mean"))
    g["eligible_pct"] = np.where(g["households"] > 0, 100 * g["eligible_households"] / g["households"], 0.0)
    g["tags"] = g["segment_id"].map(lambda i: ", ".join(SEGMENT_BY_ID[i].tags) if i in SEGMENT_BY_ID else "")
    return g.sort_values("demand_inr", ascending=False).reset_index(drop=True)


def _crop_table(kb, w: pd.DataFrame) -> pd.DataFrame:
    cols = ["crop", "districts", "households", "eligible_households", "demand_inr", "demand_per_10k_inr", "avg_loan_est_inr", "fit_score",
            "crop_cover_pct", "avg_schemes", "avg_subsidies", "crop_specific_products", "kb_recommended_loans", "market_category", "top_product", "credit_attractiveness"]
    d = w[w["crop"].notna()]
    if d.empty:
        return pd.DataFrame(columns=cols)
    g = d.groupby("crop", as_index=False).agg(
        districts=("district", "nunique"), households=("households", "sum"), eligible_households=("eligible_households", "sum"),
        demand_inr=("demand_inr", "sum"), avg_loan_est_inr=("loan_est_inr", "mean"), fit_score=("fit_score", "mean"),
        crop_cover_pct=("crop_cover_available", lambda s: 100 * float(s.astype(bool).mean())), avg_schemes=("n_schemes_eligible", "mean"),
        avg_subsidies=("n_subsidies", "mean"), top_product=("top_loan_product", lambda s: s.mode().iat[0] if len(s.mode()) else None))
    g["demand_per_10k_inr"] = np.where(g["households"] > 0, g["demand_inr"] / g["households"] * 10_000, 0.0)
    loans = kb.loans[~kb.loans["excluded"]]
    v = kb.vocab

    def _spec(crop: str) -> int:
        return int(sum(1 for c in loans["crop_specific"] if str(c).lower() not in ("no", "nan", "") and v.crop_matches(str(c), crop)))

    g["crop_specific_products"] = g["crop"].map(_spec)
    g["kb_recommended_loans"] = g["crop"].map(lambda c: "; ".join(kb.crop_row(c)["recommended_loans_list"]) if kb.crop_row(c) is not None else "")
    g["market_category"] = g["crop"].map(lambda c: kb.crop_row(c)["market_category"] if kb.crop_row(c) is not None else None)
    smax = g["avg_subsidies"].max() or 1.0
    g["credit_attractiveness"] = (40 * g["fit_score"] / 100 + 20 * g["crop_cover_pct"] / 100 + 20 * g["avg_subsidies"] / smax
                                  + 20 * np.clip(g["crop_specific_products"] / 4.0, 0, 1)).round(1)
    return g[cols].sort_values("credit_attractiveness", ascending=False).reset_index(drop=True)


def _product_table(w: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for _, r in w.iterrows():
        try:
            prods = json.loads(r["loan_products_json"]) if isinstance(r["loan_products_json"], str) else []
        except Exception:
            prods = []
        for p in prods:
            if (p.get("score") or 0) >= 50:
                rows.append({"product": p["title"], "bank": p.get("bank"), "loan_type": p.get("type"), "score": p["score"],
                             "households": r["households"], "segment_id": r["segment_id"], "district": r["district"]})
    if not rows:
        return pd.DataFrame(columns=["product", "bank", "loan_type", "eligible_households", "avg_score", "districts"])
    p = pd.DataFrame(rows)
    g = p.groupby(["product", "bank", "loan_type"], as_index=False).agg(eligible_households=("households", "sum"), avg_score=("score", "mean"), districts=("district", "nunique"))
    return g.sort_values("eligible_households", ascending=False).reset_index(drop=True)


def _bank_table(kb, w: pd.DataFrame, product_tbl: pd.DataFrame, state: Optional[str]) -> pd.DataFrame:
    br = kb.branches
    if state:
        br = br[br["state"] == state]
    presence = br.groupby("bank_name", as_index=False).agg(branches=("branch_name", "count"), loan_desks=("loan_available_bool", "sum"), districts=("district", "nunique"))
    wins = product_tbl.groupby("bank", as_index=False).agg(modelled_eligible_households=("eligible_households", "sum"), products=("product", "nunique")) if len(product_tbl) else pd.DataFrame(columns=["bank", "modelled_eligible_households", "products"])
    out = presence.merge(wins, left_on="bank_name", right_on="bank", how="outer")
    out["bank_name"] = out["bank_name"].fillna(out["bank"])
    out = out.drop(columns=["bank"]).fillna({"branches": 0, "loan_desks": 0, "districts": 0, "modelled_eligible_households": 0, "products": 0})
    return out.sort_values("modelled_eligible_households", ascending=False).reset_index(drop=True)


def credit_intelligence(user: User, kb, matrix: SegmentMatrix, state: Optional[str] = None,
                        scenario: Scenario = DEFAULT_SCENARIO, crop: Optional[str] = None,
                        segment_tags: Optional[List[str]] = None) -> CreditIntelligence:
    """Bank-manager analytics. Authorisation is enforced here, not only in the UI."""
    authorize(user, Permission.CREDIT_ANALYTICS, "view agricultural credit intelligence")
    notes = [f"Basis: {scenario.basis}. The knowledge base holds no observed loan-demand data; figures are KB eligibility × scenario household shares.",
             f"Scenario: {scenario.label}. Eligible = at least one KB loan product scoring ≥{scenario.eligible_min_loan_score:.0f} and eligibility rating not 'Limited'."]
    if not matrix.available:
        return CreditIntelligence(state, scenario.label, BASIS, {}, pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), pd.DataFrame(),
                                  notes + ["Segment matrix not built — run scripts/build_segment_matrix.py."], stale=True, available=False)
    d = matrix.districts(state)
    if segment_tags:
        keep = {sid for sid, s in SEGMENT_BY_ID.items() if set(segment_tags) & set(s.tags)}
        d = d[d["segment_id"].isin(keep)]
    if crop:
        d = d[d["crop"] == crop]
    w = _weighted(d, scenario)
    dist = _district_table(w) if len(w) else pd.DataFrame()
    seg = _segment_table(w) if len(w) else pd.DataFrame()
    grid = matrix.crop_grid(state) if state else pd.DataFrame()
    crop_tbl = _crop_table(kb, _weighted(grid, scenario)) if len(grid) else _crop_table(kb, w)
    prod = _product_table(w) if len(w) else pd.DataFrame()
    bank = _bank_table(kb, w, prod, state)
    hh = float(w["households"].sum()) if len(w) else 0.0
    kpis = {
        "districts": int(w["district"].nunique()) if len(w) else 0,
        "households_modelled": hh,
        "eligible_households": float(w["eligible_households"].sum()) if len(w) else 0.0,
        "eligible_pct": (100 * float(w["eligible_households"].sum()) / hh) if hh else 0.0,
        "demand_inr": float(w["demand_inr"].sum()) if len(w) else 0.0,
        "avg_ticket_inr": (float(w["demand_inr"].sum()) / float(w["eligible_households"].sum())) if len(w) and w["eligible_households"].sum() else 0.0,
        "high_potential_districts": int((dist["potential"] == "High").sum()) if len(dist) else 0,
        "demand_per_10k_inr": (float(w["demand_inr"].sum()) / hh * 10_000) if hh else 0.0,
        "avg_fit_score": float(np.average(w["fit_score"], weights=w["households"])) if hh else 0.0,
        "crop_cover_pct": float(100 * np.average(w["crop_cover_available"].astype(float), weights=w["households"])) if hh else 0.0,
        "untapped_districts": int((dist["credit_opportunity"] == "No KB branch desk — untapped").sum()) if len(dist) else 0,
        "top_crop": crop_tbl.iloc[0]["crop"] if len(crop_tbl) else None,
        "top_product": prod.iloc[0]["product"] if len(prod) else None,
        "top_loan_type": prod.iloc[0]["loan_type"] if len(prod) else None,
        "kb_branches": int(kb.branches[kb.branches["state"] == state].shape[0]) if state else int(len(kb.branches)),
        "doc_readiness_pct": float(w["doc_readiness"].mean()) if len(w) and w["doc_readiness"].notna().any() else None,
    }
    if matrix.stale:
        notes.append("Segment matrix was built with an earlier KB/override version — rebuild for current figures.")
    if state and kb.coverage_level(state) != "deep":
        notes.append(f"KB coverage for {state} is {kb.coverage_level(state)}: no state-specific branches; branch-access indicators are unavailable.")
    return CreditIntelligence(state, scenario.label, BASIS, kpis, dist, seg, crop_tbl, prod, bank, notes, stale=matrix.stale)
