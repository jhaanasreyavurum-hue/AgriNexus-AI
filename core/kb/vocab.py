"""Vocabulary canonicalisation for the AgriNexus knowledge base.

The KB files use different spellings for soil types, crops, land bands and
farmer categories. This module loads ``data/config/vocab_mappings.yaml`` and
exposes pure functions that translate between farm-profile values and KB
spellings. Nothing here mutates the KB.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Dict, List, Optional, Sequence

import yaml

from core import CONFIG_DIR

ACRES_PER_HECTARE = 2.47105


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", str(s)).strip().lower()


@dataclass
class Vocab:
    raw: dict

    # ------------------------------------------------------------------ soil
    soil_aliases: Dict[str, str] = field(default_factory=dict)
    soil_canonical: Dict[str, dict] = field(default_factory=dict)
    soil_similarity: Dict[str, Dict[str, float]] = field(default_factory=dict)

    # ------------------------------------------------------------------ crop
    crop_groups: Dict[str, List[str]] = field(default_factory=dict)
    crop_aliases: Dict[str, str] = field(default_factory=dict)
    group_labels: List[str] = field(default_factory=list)

    # ----------------------------------------------------------------- bands
    land_bands: List[dict] = field(default_factory=list)
    income_bands: List[dict] = field(default_factory=list)
    farmer_cat_by_land: List[dict] = field(default_factory=list)
    farmer_kb_terms: Dict[str, List[str]] = field(default_factory=dict)
    seasons: Dict[str, dict] = field(default_factory=dict)
    risk_to_cover_keywords: Dict[str, List[str]] = field(default_factory=dict)
    doc_alias_to_canonical: Dict[str, str] = field(default_factory=dict)
    doc_implied_by_profile: Dict[str, List[str]] = field(default_factory=dict)
    doc_obtainable: List[str] = field(default_factory=list)
    loan_purpose_to_types: Dict[str, List[str]] = field(default_factory=dict)
    subsidy_relevance: Dict[str, dict] = field(default_factory=dict)
    objective_category_bonus: Dict[str, Dict[str, float]] = field(default_factory=dict)

    def __post_init__(self) -> None:
        r = self.raw
        soil = r.get("soil", {})
        self.soil_canonical = soil.get("canonical", {})
        self.soil_aliases = {_norm(k): v for k, v in soil.get("aliases", {}).items()}
        self.soil_similarity = soil.get("similarity", {})

        cg = r.get("crop_groups", {})
        self.crop_groups = {k: list(v or []) for k, v in cg.get("map", {}).items()}
        self.crop_aliases = {_norm(k): v for k, v in cg.get("aliases", {}).items()}
        self.group_labels = list(cg.get("group_labels", []))
        # every crop_master name is also an alias of itself
        for name in self.crop_groups:
            self.crop_aliases.setdefault(_norm(name), name)

        self.land_bands = list(r.get("land_bands", []))
        self.income_bands = list(r.get("income_bands", []))
        fc = r.get("farmer_category", {})
        self.farmer_cat_by_land = list(fc.get("by_land_hectares", []))
        self.farmer_kb_terms = {k: list(v) for k, v in fc.get("kb_terms", {}).items()}
        self.seasons = dict(r.get("seasons", {}))
        self.risk_to_cover_keywords = {k: list(v) for k, v in r.get("risk_to_cover_keywords", {}).items()}

        docs = r.get("documents", {})
        for canon, spellings in docs.get("canonical", {}).items():
            self.doc_alias_to_canonical[_norm(canon)] = canon
            for sp in spellings:
                self.doc_alias_to_canonical[_norm(sp)] = canon
        self.doc_implied_by_profile = {k: list(v) for k, v in docs.get("implied_by_profile", {}).items()}
        self.doc_obtainable = list(docs.get("obtainable_at_application", []))
        self.doc_conditional = {k: list(v) for k, v in docs.get("conditional", {}).items()}
        self.loan_purpose_to_types = {k: list(v) for k, v in r.get("loan_purpose_to_types", {}).items()}
        self.subsidy_relevance = dict(r.get("subsidy_relevance", {}))
        self.objective_category_bonus = {k: dict(v) for k, v in r.get("objective_category_bonus", {}).items()}

    # ================================================================== SOIL
    def canonical_soil(self, kb_or_user_value: Optional[str]) -> Optional[str]:
        """Map any KB / user soil string to a canonical class (or None)."""
        if not kb_or_user_value:
            return None
        key = _norm(kb_or_user_value)
        if key in self.soil_aliases:
            return self.soil_aliases[key]
        if key in self.soil_canonical:
            return key
        # fuzzy contains-match on keywords
        for kw, canon in (
            ("black", "black"), ("regur", "black"), ("alluvial", "alluvial"),
            ("laterite", "laterite"), ("red", "red"), ("saline", "saline_alkaline"),
            ("alkaline", "saline_alkaline"), ("sandy", "sandy"), ("clay", "clay"), ("loam", "loam"),
        ):
            if kw in key:
                return canon
        return None

    def soil_label(self, canonical: str) -> str:
        return self.soil_canonical.get(canonical, {}).get("label", canonical)

    def soil_match_score(self, crop_soil: Optional[str], farm_soil: Optional[str]) -> Optional[float]:
        """0..1 similarity between a crop's preferred soil and the farm soil."""
        a, b = self.canonical_soil(crop_soil), self.canonical_soil(farm_soil)
        if a is None or b is None:
            return None
        return float(self.soil_similarity.get(a, {}).get(b, 0.3))

    # ================================================================== CROP
    def resolve_crop_name(self, user_value: Optional[str]) -> Optional[str]:
        """Free-text / KB group name -> crop_master crop_name (or None)."""
        if not user_value:
            return None
        key = _norm(user_value)
        if key in self.crop_aliases:
            return self.crop_aliases[key]
        # try stripping parentheses: "Paddy (Rice)" -> "paddy"
        base = _norm(re.sub(r"\(.*?\)", "", user_value))
        if base in self.crop_aliases:
            return self.crop_aliases[base]
        # substring match against master names
        for name in self.crop_groups:
            if key and key in _norm(name):
                return name
        return None

    def crop_groups_for(self, crop_name: Optional[str]) -> List[str]:
        """All KB group labels a crop belongs to (plus the crop name itself)."""
        if not crop_name:
            return []
        master = self.resolve_crop_name(crop_name) or crop_name
        groups = list(self.crop_groups.get(master, []))
        base = re.sub(r"\s*\(.*?\)", "", master).strip()
        for extra in (master, base):
            if extra not in groups:
                groups.append(extra)
        return groups

    def crop_matches(self, kb_crop_value: Optional[str], farm_crop: Optional[str],
                     universal_terms: Sequence[str] = ("All Crops", "Not Crop Specific")) -> bool:
        """Does a KB crop cell apply to the farmer's crop?"""
        if kb_crop_value is None or str(kb_crop_value).strip() == "" or str(kb_crop_value) == "nan":
            return True
        kb = str(kb_crop_value).strip()
        if kb in universal_terms or kb.lower().startswith("not crop specific"):
            # livestock/fisheries "Not Crop Specific - X" rows are NOT crop matches
            return kb in universal_terms
        if not farm_crop:
            return False
        groups = {_norm(g) for g in self.crop_groups_for(farm_crop)}
        return _norm(kb) in groups

    # ================================================================= BANDS
    @staticmethod
    def acres_from(area: float, unit: str = "acres") -> float:
        unit = (unit or "acres").lower()
        if unit.startswith("ha") or unit.startswith("hect"):
            return float(area) * ACRES_PER_HECTARE
        return float(area)

    @staticmethod
    def hectares_from(area: float, unit: str = "acres") -> float:
        unit = (unit or "acres").lower()
        if unit.startswith("ha") or unit.startswith("hect"):
            return float(area)
        return float(area) / ACRES_PER_HECTARE

    def land_band_labels(self, acres: float) -> List[str]:
        """All KB land-band labels the holding satisfies (bands overlap)."""
        out = []
        for b in self.land_bands:
            lo, hi = b["min"], b["max"]
            if acres >= lo and (hi is None or acres < hi):
                out.append(b["label"])
        return out

    def income_band_labels(self, income_inr: Optional[float]) -> List[str]:
        if income_inr is None:
            return []
        out = []
        for b in self.income_bands:
            lo, hi = b["min"], b["max"]
            if income_inr >= lo and (hi is None or income_inr < hi):
                out.append(b["label"])
        return out

    def farmer_category_from_land(self, hectares: float) -> str:
        for row in self.farmer_cat_by_land:
            if row["max_ha"] is None or hectares <= row["max_ha"]:
                return row["label"]
        return "Large Farmer"

    def farmer_terms_satisfied(self, profile_attrs: Sequence[str]) -> List[str]:
        """Given canonical profile attributes (e.g. ['any','landowner','small_marginal']),
        return every KB farmer-term spelling the profile satisfies."""
        terms: List[str] = []
        for attr in profile_attrs:
            terms.extend(self.farmer_kb_terms.get(attr, []))
        return sorted(set(terms))

    # ============================================================= DOCUMENTS
    def canonical_document(self, name: Optional[str]) -> Optional[str]:
        if not name:
            return None
        return self.doc_alias_to_canonical.get(_norm(name), str(name).strip())

    def canonical_documents(self, names: Sequence[str]) -> List[str]:
        out: List[str] = []
        for n in names or []:
            c = self.canonical_document(n)
            if c and c not in out:
                out.append(c)
        return out

    # =============================================================== SEASONS
    def season_for_month(self, month: int) -> Optional[str]:
        for name, cfg in self.seasons.items():
            if month in cfg.get("sowing_months", []):
                return name
        return None


@lru_cache(maxsize=1)
def load_vocab(path: Optional[str] = None) -> Vocab:
    p = CONFIG_DIR / "vocab_mappings.yaml" if path is None else path
    with open(p, "r", encoding="utf-8") as fh:
        return Vocab(raw=yaml.safe_load(fh))
