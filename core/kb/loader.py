"""Knowledge-base loader.

Loads the ten client-supplied CSVs from ``data/knowledge_base`` exactly as
delivered, verifies their checksums, applies the reviewed overrides from
``data/config/kb_overrides.yaml`` **in memory only**, and adds normalised
helper columns (``*_canonical``, parsed JSON, split lists).

Every applied override is recorded in ``KnowledgeBase.override_log`` so the
UI can show "corrected from KB" provenance badges.
"""
from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd
import yaml

from core import CONFIG_DIR, KB_DIR
from core.kb.vocab import Vocab, load_vocab

log = logging.getLogger(__name__)

# Logical name -> file stem. Engines refer to tables by logical name.
TABLES: Dict[str, str] = {
    "crops": "agrinexus_crop_master",
    "geo": "agrinexus_state_district_master",
    "schemes": "agrinexus_government_schemes",
    "eligibility_rules": "agrinexus_eligibility_rules",
    "ai_rules": "ai_recommendation_rules",
    "loans": "agrinexus_agri_loan_products",
    "subsidies": "agrinexus_agricultural_subsidies",
    "insurance": "agrinexus_crop_insurance_products",
    "documents": "agrinexus_required_documents",
    "branches": "agrinexus_bank_branches",
}
STEM_TO_LOGICAL = {v: k for k, v in TABLES.items()}

PRIMARY_KEYS: Dict[str, str] = {
    "crops": "crop_id", "geo": "district_id", "schemes": "scheme_id",
    "eligibility_rules": "rule_id", "ai_rules": "rule_id", "loans": "loan_id",
    "subsidies": "subsidy_id", "insurance": "insurance_id",
    "documents": "document_id", "branches": "bank_id",
}

YES = {"yes", "y", "true", "1"}


def _yes(v: Any) -> bool:
    return str(v).strip().lower() in YES


def _split(v: Any, sep: str) -> List[str]:
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return []
    return [x.strip() for x in str(v).split(sep) if x.strip()]


@dataclass
class OverrideRecord:
    override_id: str
    table: str
    key: Dict[str, Any]
    column: str
    original: Any
    new: Any
    reason: str
    reference: str


@dataclass
class KnowledgeBase:
    tables: Dict[str, pd.DataFrame]
    vocab: Vocab
    interpretation: Dict[str, Any]
    override_log: List[OverrideRecord] = field(default_factory=list)
    excluded_ids: Dict[str, set] = field(default_factory=dict)
    checksum_status: Dict[str, str] = field(default_factory=dict)

    # ----------------------------------------------------------- accessors
    def __getattr__(self, item: str) -> pd.DataFrame:  # kb.crops, kb.schemes ...
        tables = self.__dict__.get("tables", {})
        if item in tables:
            return tables[item]
        raise AttributeError(item)

    def table(self, name: str) -> pd.DataFrame:
        return self.tables[name]

    def overrides_for(self, table: str, key_value: Any) -> List[OverrideRecord]:
        pk = PRIMARY_KEYS[table]
        return [o for o in self.override_log if o.table == table and o.key.get(pk) == key_value]

    def summary(self) -> Dict[str, Any]:
        return {
            "tables": {k: len(v) for k, v in self.tables.items()},
            "overrides_applied": len(self.override_log),
            "exclusions": {k: len(v) for k, v in self.excluded_ids.items()},
            "checksums": self.checksum_status,
        }

    # -------------------------------------------------------------- lookups
    def crop_row(self, crop_name: str) -> Optional[pd.Series]:
        master = self.vocab.resolve_crop_name(crop_name)
        if master is None:
            return None
        df = self.crops
        hit = df[df["crop_name"] == master]
        return hit.iloc[0] if len(hit) else None

    def district_row(self, state: str, district: Optional[str] = None) -> Optional[pd.Series]:
        df = self.geo
        st = df[df["state_name"].str.lower() == str(state).lower()]
        if district:
            d = st[st["district_name"].str.lower() == str(district).lower()]
            if len(d):
                return d.iloc[0]
        return st.iloc[0] if len(st) else None

    def states(self) -> List[str]:
        return sorted(self.geo["state_name"].unique().tolist())

    def districts(self, state: str) -> List[str]:
        df = self.geo
        return sorted(df[df["state_name"] == state]["district_name"].tolist())

    def coverage_level(self, state: str) -> str:
        if state in self.interpretation.get("deep_coverage_states", []):
            return "deep"
        if state in self.interpretation.get("moderate_coverage_states", []):
            return "moderate"
        return "limited"


# =============================================================== checksums
def _verify_checksums(kb_dir: Path) -> Dict[str, str]:
    status: Dict[str, str] = {}
    sums_file = kb_dir / "CHECKSUMS.sha256"
    if not sums_file.exists():
        return {stem: "unverified" for stem in TABLES.values()}
    expected: Dict[str, str] = {}
    for line in sums_file.read_text().splitlines():
        parts = line.strip().split()
        if len(parts) == 2:
            expected[Path(parts[1]).name] = parts[0]
    for stem in TABLES.values():
        fname = f"{stem}.csv"
        p = kb_dir / fname
        if not p.exists():
            status[stem] = "missing"
            continue
        actual = hashlib.sha256(p.read_bytes()).hexdigest()
        exp = expected.get(fname)
        status[stem] = "ok" if exp == actual else ("modified" if exp else "unverified")
    return status


# =============================================================== overrides
def _apply_overrides(tables: Dict[str, pd.DataFrame], cfg: dict) -> tuple[List[OverrideRecord], Dict[str, set]]:
    log_records: List[OverrideRecord] = []
    excluded: Dict[str, set] = {k: set() for k in tables}
    for ov in cfg.get("overrides", []) or []:
        if not ov.get("enabled", True):
            continue
        logical = STEM_TO_LOGICAL.get(ov["table"], ov["table"])
        df = tables.get(logical)
        if df is None:
            log.warning("override %s: unknown table %s", ov.get("id"), ov["table"])
            continue
        mask = pd.Series(True, index=df.index)
        for k, v in ov["key"].items():
            mask &= df[k].astype(str) == str(v)
        if not mask.any():
            log.warning("override %s: key %s not found", ov.get("id"), ov["key"])
            continue
        for col, new in ov.get("set", {}).items():
            if col not in df.columns:
                df[col] = pd.NA
            for idx in df.index[mask]:
                original = df.at[idx, col]
                df.at[idx, col] = new
                log_records.append(OverrideRecord(
                    override_id=ov.get("id", "?"), table=logical, key=dict(ov["key"]),
                    column=col, original=original, new=new,
                    reason=str(ov.get("reason", "")).strip(), reference=str(ov.get("reference", "")),
                ))
    for ex in cfg.get("exclusions", []) or []:
        if not ex.get("enabled", True):
            continue
        logical = STEM_TO_LOGICAL.get(ex["table"], ex["table"])
        pk = PRIMARY_KEYS[logical]
        excluded[logical].add(str(ex["key"][pk]))
    return log_records, excluded


# ============================================================ normalisation
def normalise_loans(l: pd.DataFrame) -> pd.DataFrame:
    """Helper columns for the loans table (also used for session-added products)."""
    for col in ("collateral_required", "equipment_supported", "livestock_supported",
                "working_capital", "government_linked"):
        if col not in l.columns:
            l[col] = "No"
        l[f"{col}_bool"] = l[col].map(_yes)
    l["crop_specific_flag"] = ~l["crop_specific"].astype(str).str.lower().isin(["no", "nan", ""])
    l["documents_list"] = l["required_documents"].map(lambda v: _split(v, ";"))
    return l


def normalise_schemes(s: pd.DataFrame) -> pd.DataFrame:
    """Helper columns for the schemes table (also used for session-added schemes)."""
    for col in ("aadhaar_required", "bank_account_required", "soil_card_required",
                "insurance_required", "loan_support"):
        if col not in s.columns:
            s[col] = "No"
        s[f"{col}_bool"] = s[col].map(_yes)
    if "documents_required" not in s.columns:
        s["documents_required"] = pd.NA
    s["documents_list"] = s["documents_required"].map(lambda v: _split(v, ";"))
    s["is_active"] = s["active_status"].astype(str).str.lower().eq("active")
    return s


def _normalise(tables: Dict[str, pd.DataFrame], vocab: Vocab) -> None:
    """Add helper columns. Original columns are never changed here."""
    # crops
    c = tables["crops"]
    c["soil_canonical"] = c["soil_type"].map(vocab.canonical_soil)
    c["crop_groups"] = c["crop_name"].map(vocab.crop_groups_for)
    c["recommended_schemes_list"] = c["recommended_schemes"].map(lambda v: _split(v, ";"))
    c["recommended_loans_list"] = c["recommended_loans"].map(lambda v: _split(v, ";"))
    if "season_alternates" not in c.columns:
        c["season_alternates"] = pd.NA
    c["seasons_all"] = [
        [s] + ([] if pd.isna(alt) else _split(alt, ";")) for s, alt in zip(c["season"], c["season_alternates"])
    ]
    c["insurance_available_bool"] = c["insurance_available"].map(_yes)

    # schemes
    normalise_schemes(tables["schemes"])

    # eligibility rules
    e = tables["eligibility_rules"]
    e["soil_canonical"] = e["soil_type"].map(vocab.canonical_soil)
    e["aadhaar_required_bool"] = e["aadhaar_required"].map(_yes)

    # ai rules
    a = tables["ai_rules"]
    conds = a["condition_json"].map(json.loads)
    a["cond_state"] = conds.map(lambda d: d.get("state"))
    a["cond_crop"] = conds.map(lambda d: d.get("crop"))
    a["cond_land_band"] = conds.map(lambda d: d.get("land_acres"))
    a["cond_income_band"] = conds.map(lambda d: d.get("income_inr"))
    a["schemes_list"] = a["recommended_scheme"].map(lambda v: _split(v, ","))
    a["loans_list"] = a["recommended_loan"].map(lambda v: _split(v, ","))
    a["insurance_list"] = a["recommended_insurance"].map(lambda v: _split(v, ","))

    # loans
    normalise_loans(tables["loans"])

    # subsidies
    sb = tables["subsidies"]
    sb["documents_list"] = sb["documents"].map(lambda v: _split(v, ";"))
    sb["is_livestock_or_allied"] = sb["crop"].astype(str).str.startswith("Not Crop Specific -")

    # insurance
    i = tables["insurance"]
    i["documents_list"] = i["documents_required"].map(lambda v: _split(v, ";"))
    i["districts_list"] = i["district_applicable"].map(lambda v: _split(v, ","))
    i["is_livestock"] = i["covered_crop"].astype(str).str.startswith("Not Crop Specific -")

    # documents
    d = tables["documents"]
    d["mandatory_bool"] = d["mandatory"].map(_yes)
    d["verification_required_bool"] = d["verification_required"].map(_yes)

    # branches
    b = tables["branches"]
    b["loan_available_bool"] = b["loan_available"].map(_yes)
    b["insurance_available_bool"] = b["insurance_available"].map(_yes)


# =================================================================== load
@lru_cache(maxsize=1)
def load_knowledge_base(kb_dir: Optional[str] = None, config_dir: Optional[str] = None) -> KnowledgeBase:
    kb_path = Path(kb_dir) if kb_dir else KB_DIR
    cfg_path = Path(config_dir) if config_dir else CONFIG_DIR

    tables: Dict[str, pd.DataFrame] = {}
    for logical, stem in TABLES.items():
        f = kb_path / f"{stem}.csv"
        if not f.exists():
            raise FileNotFoundError(f"Knowledge-base file missing: {f}")
        tables[logical] = pd.read_csv(f)

    checksums = _verify_checksums(kb_path)
    for stem, st in checksums.items():
        if st == "modified":
            log.warning("KB file %s differs from pinned checksum — original KB may have been edited", stem)

    with open(cfg_path / "kb_overrides.yaml", "r", encoding="utf-8") as fh:
        ov_cfg = yaml.safe_load(fh) or {}
    override_log, excluded = _apply_overrides(tables, ov_cfg)

    vocab = load_vocab()
    _normalise(tables, vocab)

    # mark excluded rows (kept in the frame, flagged) so engines can skip them
    for logical, ids in excluded.items():
        pk = PRIMARY_KEYS[logical]
        tables[logical]["excluded"] = tables[logical][pk].astype(str).isin(ids)
    for logical in tables:
        if "excluded" not in tables[logical].columns:
            tables[logical]["excluded"] = False

    return KnowledgeBase(
        tables=tables, vocab=vocab,
        interpretation=ov_cfg.get("interpretation", {}),
        override_log=override_log, excluded_ids=excluded, checksum_status=checksums,
    )
