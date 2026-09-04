"""Segment × district eligibility matrix (the modelled backbone of bank / government analytics).

For every district in the KB district master and every farmer-segment
archetype, the **real** knowledge engines are run (scheme matcher, loan
advisor, insurance matcher, subsidy finder) on a sparse synthetic FarmContext.
Results are stored as one row per (district, crop, segment) in
``data/derived/segment_matrix.csv`` together with a fingerprint of the KB
checksums + overrides + segment definitions, so the platform can tell whether
the matrix is stale. Building takes a few minutes (≈0.4 s per profile), so it
is a build step (``scripts/build_segment_matrix.py``) rather than a page load.
"""
from __future__ import annotations

import hashlib
import json
import logging
import time
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

import pandas as pd

from core import DATA_DIR, KB_DIR, CONFIG_DIR
from .segments import SEGMENTS, SEGMENT_BY_ID, Segment, segment_context

log = logging.getLogger(__name__)

DERIVED_DIR = DATA_DIR / "derived"
MATRIX_PATH = DERIVED_DIR / "segment_matrix.csv"
META_PATH = DERIVED_DIR / "segment_matrix.meta.json"

# crops used for the state-level crop grid (bank "crop trends"); resolved against crop_master at build time
CROP_GRID = ["Paddy (Rice)", "Cotton", "Maize", "Groundnut", "Soybean", "Sugarcane", "Turmeric", "Red Chilli",
             "Pigeon Pea (Tur/Arhar)", "Wheat", "Chickpea (Gram)", "Onion"]
CROP_GRID_STATES_MAX = 2          # deep + moderate coverage states get a crop grid

MATRIX_COLUMNS = [
    "state", "district", "kind", "crop", "season", "segment_id", "segment_label", "segment_group", "coverage",
    "loan_est_inr", "loan_rating", "loan_rating_score", "n_loan_products_eligible", "top_loan_product", "top_loan_bank",
    "top_loan_type", "top_loan_score", "top_loan_doc_readiness_pct", "loan_products_json",
    "n_schemes_eligible", "top_scheme", "top_scheme_score", "schemes_json",
    "n_insurance", "crop_cover_available", "top_insurance", "insurance_json",
    "n_subsidies", "top_subsidy", "subsidy_max_total_inr", "subsidies_json",
    "branches_in_district", "branches_loan_desk", "fired_eligibility_rules", "fired_ai_rules",
]


# ---------------------------------------------------------------- fingerprint
def matrix_fingerprint() -> str:
    h = hashlib.sha256()
    for p in (KB_DIR / "CHECKSUMS.sha256", CONFIG_DIR / "kb_overrides.yaml", CONFIG_DIR / "vocab_mappings.yaml"):
        if p.exists():
            h.update(p.read_bytes())
    h.update(json.dumps([s.to_dict() for s in SEGMENTS], sort_keys=True, default=str).encode())
    h.update(json.dumps(CROP_GRID).encode())
    return h.hexdigest()[:16]


# ---------------------------------------------------------------- one profile
def _resolve_crop(kb, raw: Optional[str]) -> Optional[str]:
    if not raw or str(raw).startswith("Not Applicable"):
        return None
    return kb.vocab.resolve_crop_name(str(raw))


def _season_for(kb, crop: Optional[str]) -> Optional[str]:
    if not crop:
        return None
    row = kb.crop_row(crop)
    return None if row is None else str(row["season"])


def evaluate_profile(kb, seg: Segment, state: str, district: str, crop: Optional[str], kind: str,
                     lat: Optional[float], lon: Optional[float], zone: Optional[str]) -> Dict[str, Any]:
    """Run the knowledge engines for one synthetic profile. Pure function of (KB, segment, place, crop)."""
    from core.models import FarmContext
    from core.engines.facts import build_facts
    from core.engines.scheme_matcher import match_schemes, fire_eligibility_rules, fire_ai_rules
    from core.engines.loan_advisor import advise_loans
    from core.engines.insurance_matcher import match_insurance, crop_covers
    from core.engines.subsidy_finder import find_subsidies

    season = _season_for(kb, crop)
    purpose = "livestock" if seg.livestock else "crop_loan"
    ctx = FarmContext.from_dict(segment_context(seg, state, district, crop, season, purpose, lat, lon, zone))
    facts = build_facts(ctx, kb)
    soil = None
    schemes = match_schemes(kb, facts, soil, top_n=40)
    loans = advise_loans(kb, facts, 0.0, soil, top_n=40)
    ins = match_insurance(kb, facts, soil, top_n=10)
    subs = find_subsidies(kb, facts, {m.title: m.score for m in schemes}, top_n=20)
    elig = fire_eligibility_rules(kb, facts, soil)
    ai = fire_ai_rules(kb, facts)

    br = kb.branches
    mine = br[(br["state"].str.lower() == state.lower()) & (br["district"].str.lower() == district.lower())]
    prods = [m for m in loans.products if m.score >= 50]
    top = loans.products[0] if loans.products else None
    schemes_ok = [m for m in schemes if m.score >= 50]
    return {
        "state": state, "district": district, "kind": kind, "crop": crop, "season": season,
        "segment_id": seg.segment_id, "segment_label": seg.label, "segment_group": seg.group, "coverage": facts.kb_coverage,
        "loan_est_inr": loans.estimated_eligibility_inr, "loan_rating": loans.eligibility_rating, "loan_rating_score": loans.rating_score,
        "n_loan_products_eligible": len(prods),
        "top_loan_product": top.title if top else None, "top_loan_bank": top.payload.get("bank_short") if top else None,
        "top_loan_type": top.payload.get("loan_type") if top else None, "top_loan_score": top.score if top else None,
        "top_loan_doc_readiness_pct": top.payload.get("document_readiness_pct") if top else None,
        "loan_products_json": json.dumps([{"id": m.item_id, "title": m.title, "bank": m.payload.get("bank_short"), "type": m.payload.get("loan_type"),
                                           "score": round(m.score, 1), "amount_max": m.payload.get("amount_max"), "rate": m.payload.get("min_interest")} for m in loans.products]),
        "n_schemes_eligible": len(schemes_ok), "top_scheme": schemes[0].title if schemes else None, "top_scheme_score": schemes[0].score if schemes else None,
        "schemes_json": json.dumps([{"id": m.item_id, "title": m.title, "score": round(m.score, 1), "type": m.payload.get("scheme_type"),
                                     "level": m.payload.get("government_level")} for m in schemes]),
        "n_insurance": len(ins), "crop_cover_available": bool(crop_covers(ins)), "top_insurance": ins[0].title if ins else None,
        "insurance_json": json.dumps([{"id": m.item_id, "title": m.title, "score": round(m.score, 1), "crop": m.payload.get("covered_crop")} for m in ins]),
        "n_subsidies": len([m for m in subs if m.score >= 50]), "top_subsidy": subs[0].title if subs else None,
        "subsidy_max_total_inr": float(sum((m.payload.get("maximum_amount") or 0) for m in subs if m.score >= 50)),
        "subsidies_json": json.dumps([{"id": m.item_id, "title": m.title, "score": round(m.score, 1), "max": m.payload.get("maximum_amount")} for m in subs]),
        "branches_in_district": int(len(mine)), "branches_loan_desk": int(mine["loan_available_bool"].sum()) if len(mine) else 0,
        "fired_eligibility_rules": int(len(elig)), "fired_ai_rules": int(len(ai)),
    }


# ---------------------------------------------------------------- job planning
def plan_jobs(kb) -> List[Tuple[str, str, Optional[str], str, Optional[float], Optional[float], Optional[str]]]:
    """(state, district, crop, kind, lat, lon, zone) for every district × its major crop, plus a crop grid for covered states."""
    geo = kb.geo
    jobs = []
    for _, r in geo.iterrows():
        crop = _resolve_crop(kb, r.major_crop)
        jobs.append((str(r.state_name), str(r.district_name), crop, "district_major_crop",
                     float(r.latitude) if pd.notna(r.latitude) else None, float(r.longitude) if pd.notna(r.longitude) else None,
                     str(r.agriculture_zone) if pd.notna(r.agriculture_zone) else None))
    grid_states = [s for s in kb.interpretation.get("deep_coverage_states", []) + kb.interpretation.get("moderate_coverage_states", [])][:CROP_GRID_STATES_MAX]
    for st in grid_states:
        rows = geo[geo.state_name == st]
        if rows.empty:
            continue
        r = rows.iloc[0]
        for c in CROP_GRID:
            crop = _resolve_crop(kb, c)
            if crop:
                jobs.append((st, str(r.district_name), crop, "crop_grid", float(r.latitude), float(r.longitude), str(r.agriculture_zone)))
    return jobs


def _run_job(args) -> List[Dict[str, Any]]:
    from core.kb import load_knowledge_base
    kb = load_knowledge_base()
    state, district, crop, kind, lat, lon, zone = args
    out = []
    for seg in SEGMENTS:
        try:
            out.append(evaluate_profile(kb, seg, state, district, crop, kind, lat, lon, zone))
        except Exception as exc:  # keep the build going; record the failure
            log.exception("segment %s failed for %s/%s", seg.segment_id, state, district)
            out.append({"state": state, "district": district, "kind": kind, "crop": crop, "segment_id": seg.segment_id,
                        "segment_label": seg.label, "segment_group": seg.group, "error": str(exc)[:200]})
    return out


def build_segment_matrix(kb, workers: int = 2, limit: Optional[int] = None, progress=None) -> pd.DataFrame:
    jobs = plan_jobs(kb)
    if limit:
        jobs = jobs[:limit]
    rows: List[Dict[str, Any]] = []
    t0 = time.time()
    if workers > 1:
        with ProcessPoolExecutor(max_workers=workers) as ex:
            for i, res in enumerate(ex.map(_run_job, jobs, chunksize=4)):
                rows.extend(res)
                if progress:
                    progress(i + 1, len(jobs))
    else:
        for i, j in enumerate(jobs):
            rows.extend(_run_job(j))
            if progress:
                progress(i + 1, len(jobs))
    df = pd.DataFrame(rows)
    for c in MATRIX_COLUMNS:
        if c not in df.columns:
            df[c] = pd.NA
    df = df[MATRIX_COLUMNS + [c for c in df.columns if c not in MATRIX_COLUMNS]]
    log.info("segment matrix: %d rows from %d jobs in %.0f s", len(df), len(jobs), time.time() - t0)
    return df


def save_segment_matrix(df: pd.DataFrame, path: Path = MATRIX_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False)
    meta = {"fingerprint": matrix_fingerprint(), "built_at": time.strftime("%Y-%m-%dT%H:%M:%S"), "rows": int(len(df)),
            "districts": int(df["district"].nunique()), "segments": [s.segment_id for s in SEGMENTS],
            "basis": "MODELLED — real KB engines run over synthetic segment archetypes; no observed demand/adoption data",
            "errors": int(df["error"].notna().sum()) if "error" in df.columns else 0}
    META_PATH.write_text(json.dumps(meta, indent=2))


# ---------------------------------------------------------------- runtime access
@dataclass
class SegmentMatrix:
    df: pd.DataFrame
    meta: Dict[str, Any]
    stale: bool                    # KB / overrides / segments changed since build
    available: bool

    @property
    def basis(self) -> str:
        return "MODELLED (KB-derived)"

    def districts(self, state: Optional[str] = None) -> pd.DataFrame:
        d = self.df[self.df["kind"] == "district_major_crop"]
        return d if not state else d[d["state"] == state]

    def crop_grid(self, state: str) -> pd.DataFrame:
        d = self.df[(self.df["kind"] == "crop_grid") & (self.df["state"] == state)]
        return d


def load_segment_matrix(path: Path = MATRIX_PATH) -> SegmentMatrix:
    if not path.exists():
        return SegmentMatrix(pd.DataFrame(columns=MATRIX_COLUMNS), {}, stale=True, available=False)
    df = pd.read_csv(path)
    for c in ("crop_cover_available",):
        if c in df.columns:
            df[c] = df[c].astype(str).str.lower().isin(["true", "1"])
    meta = json.loads(META_PATH.read_text()) if META_PATH.exists() else {}
    stale = meta.get("fingerprint") != matrix_fingerprint()
    return SegmentMatrix(df, meta, stale=stale, available=True)
