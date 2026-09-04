"""Government Scheme Finder (§11) — personalised matches from three KB tables.

1. ``government_schemes``  — the scheme records (eligibility columns, benefits, docs, portal)
2. ``eligibility_rules``   — 300 crop × state × soil × farmer-category × land rules that
                             *recommend* a scheme (+ loan + insurance) with a priority
3. ``ai_recommendation_rules`` — 500 state × crop × land-band × income-band rules with a
                             confidence and a reason text

Scoring per scheme (0–100), governed by ``interpretation`` in kb_overrides.yaml:
  HARD filters (score → 0, hard_fail): inactive; state mismatch; income above
      limit (mode=hard); age outside range (mode=hard); excluded rows.
  SOFT factors: region (state-specific bonus), land range, crop, farmer term,
      document readiness (Aadhaar / bank / soil card flags), KB priority_score.
  BOOSTS: each eligibility rule that fires for this scheme (+ by priority),
      each ai_rule whose recommended list names this scheme (+ by confidence).
"""
from __future__ import annotations

import re
from typing import Dict, List, Optional

import pandas as pd

from core.engines.documents import resolve_documents
from core.engines.facts import FarmerFacts
from core.models.results import Explanation, Factor, MatchResult, Method, score_label


def _isnull(x) -> bool:
    return x is None or (isinstance(x, float) and pd.isna(x)) or str(x) == "nan"


def _region_ok(kb_state: str, farm_state: str, universal: List[str]) -> bool:
    return kb_state in universal or kb_state.strip().lower() == farm_state.strip().lower()


def _scheme_key(name: str) -> str:
    """Normalise scheme names so 'PM-KISAN' matches 'Pradhan Mantri Kisan Samman Nidhi (PM-KISAN)'."""
    return re.sub(r"[^a-z0-9]", "", name.lower())


def _ai_rule_names_match(short: str, full: str) -> bool:
    s, f = _scheme_key(short), _scheme_key(full)
    if s == f or s in f:
        return True
    # acronym inside parentheses of the full name
    m = re.search(r"\(([^)]+)\)", full)
    if m and _scheme_key(m.group(1)) == s:
        return True
    # first three significant words
    sw = [w for w in re.findall(r"[a-z]+", short.lower()) if len(w) > 3][:3]
    return bool(sw) and all(w in full.lower() for w in sw)


_LIVESTOCK_KW = ("livestock", "dairy", "poultry", "sheep", "goat", "cattle", "gokul", "milk", "animal", "fodder", "bee", "honey")
_FISH_KW = ("fish", "matsya", "aquacultur", "fisher")


def _crop_named_in(v, name: str, facts: FarmerFacts) -> Optional[str]:
    """If the scheme title names a crop-master crop other than the farmer's, return it."""
    text = " " + re.sub(r"[^a-z0-9 ]", " ", str(name).lower()) + " "
    for alias, master in v.crop_aliases.items():
        if len(alias) < 4 or master in facts.crop_groups or master == facts.crop_master:
            continue
        if f" {alias} " in text or f" {alias}s " in text:
            return master
    return None


def _allied_kind(row) -> Optional[str]:
    text = f"{row.scheme_name} {row.scheme_type} {row.beneficiary_type}".lower()
    if any(k in text for k in _FISH_KW):
        return "fisheries"
    if any(k in text for k in _LIVESTOCK_KW):
        return "livestock"
    return None


def fire_eligibility_rules(kb, facts: FarmerFacts, soil_canonical: Optional[str]) -> pd.DataFrame:
    """Rows of eligibility_rules that apply to this farm (state, crop, soil, category, land, income)."""
    v = kb.vocab
    df = kb.eligibility_rules
    uni = kb.interpretation.get("universal_region_terms", ["All India"])
    m_state = df["state"].isin(uni) | (df["state"].str.lower() == facts.state.lower())
    m_crop = df["crop"].apply(lambda c: v.crop_matches(c, facts.crop_master, tuple(kb.interpretation.get("universal_crop_terms", ["All Crops"]))))
    m_soil = (df["soil_canonical"].isna() | (df["soil_canonical"] == soil_canonical)) if soil_canonical else pd.Series(True, index=df.index)
    m_cat = df["farmer_category"].isin(facts.farmer_terms)
    # land unit for this table is an explicit interpretation decision (see kb_overrides.yaml)
    land = facts.hectares if kb.interpretation.get("eligibility_rules_land_unit", "acres") == "hectares" else facts.acres
    m_land = (df["land_min"].fillna(0) <= land) & (df["land_max"].fillna(1e9) >= land)
    m_inc = df["income_limit"].isna() | (facts.income is None) | (df["income_limit"] >= (facts.income or 0))
    # KB land ranges per rule are narrow synthetic bands; the farmer category already encodes land size,
    # so a rule still fires when the farm is within 30 % of the band (soft, weighted down).
    m_land_soft = (df["land_min"].fillna(0) * 0.7 <= land) & (df["land_max"].fillna(1e9) * 1.3 >= land)
    # state, crop, category and income are required; soil and exact land band are soft criteria
    fired = df[m_state & m_crop & m_cat & m_inc & m_land_soft].copy()
    fired["soil_match"] = m_soil.loc[fired.index]
    fired["land_match"] = m_land.loc[fired.index]
    fired["match_strength"] = 4 + fired["soil_match"].astype(int) + fired["land_match"].astype(int)   # 6 = full match
    fired["effective_priority"] = (fired["priority"] * fired["soil_match"].map({True: 1.0, False: 0.6})
                                   * fired["land_match"].map({True: 1.0, False: 0.8}))
    return fired.sort_values("effective_priority", ascending=False)


def fire_ai_rules(kb, facts: FarmerFacts) -> pd.DataFrame:
    df = kb.ai_rules
    v = kb.vocab
    m_state = df["cond_state"].str.lower() == facts.state.lower()
    m_crop = df["cond_crop"].apply(lambda c: v.crop_matches(c, facts.crop_master))
    m_land = df["cond_land_band"].isin(facts.land_bands)
    m_inc = df["cond_income_band"].isin(facts.income_bands) if facts.income_bands else pd.Series(True, index=df.index)
    return df[m_state & m_crop & m_land & m_inc].sort_values("confidence", ascending=False)


def match_schemes(kb, facts: FarmerFacts, soil_canonical: Optional[str] = None, top_n: int = 12,
                  min_score: float = 35.0) -> List[MatchResult]:
    v = kb.vocab
    interp = kb.interpretation
    uni_region = interp.get("universal_region_terms", ["All India"])
    uni_crop = tuple(interp.get("universal_crop_terms", ["All Crops"]))
    schemes = kb.schemes[~kb.schemes["excluded"]]

    elig = fire_eligibility_rules(kb, facts, soil_canonical)
    ai = fire_ai_rules(kb, facts)
    elig_by_scheme: Dict[str, List[pd.Series]] = {}
    for _, r in elig.iterrows():
        elig_by_scheme.setdefault(r.recommended_scheme, []).append(r)

    out: List[MatchResult] = []
    for _, s in schemes.iterrows():
        ex = Explanation(summary="", method=Method.KNOWLEDGE_BASE, kb_references=[s.scheme_id],
                         sources=["Knowledge base · government_schemes", "Knowledge base · eligibility_rules", "Knowledge base · ai_recommendation_rules"],
                         data_considered=["state", "land holding", "annual income", "age", "crop", "farmer category", "documents held"])
        hard = False
        score = 0.0

        # ---- hard filters ---------------------------------------------------
        if not s.is_active:
            hard = True
            ex.add(Factor("Status", "risk", f"Scheme status is {s.active_status}."))
        if not _region_ok(str(s.state), facts.state, uni_region):
            hard = True
            ex.add(Factor("Region", "risk", f"Scheme is specific to {s.state}; farm is in {facts.state}."))
        if interp.get("scheme_income_limit_mode", "hard") == "hard" and not _isnull(s.income_limit) and facts.income is not None and facts.income > float(s.income_limit):
            hard = True
            ex.add(Factor("Income limit", "risk", f"Annual income ₹{facts.income:,.0f} exceeds the scheme limit ₹{float(s.income_limit):,.0f}."))
        if interp.get("scheme_age_range_mode", "hard") == "hard" and facts.age is not None:
            lo = None if _isnull(s.minimum_age) else float(s.minimum_age)
            hi = None if _isnull(s.maximum_age) else float(s.maximum_age)
            if (lo is not None and facts.age < lo) or (hi is not None and facts.age > hi):
                hard = True
                ex.add(Factor("Age", "risk", f"Age {facts.age} is outside {lo or '—'}–{hi or '—'} years."))

        if ("women" in f"{s.scheme_name} {s.eligible_farmer} {s.beneficiary_type}".lower()) and not facts.is_woman:
            score -= 25
            ex.add(Factor("Targeted at women farmers", "limiting", "Scheme is for women farmers / women-headed households; profile does not indicate this.", weight=-25))
        named_crop = _crop_named_in(v, s.scheme_name, facts)
        if named_crop:
            score -= 12
            ex.add(Factor("Crop-specific scheme", "limiting", f"Scheme is named for {named_crop}; farm grows {facts.crop_master or 'a different crop'}.", weight=-12))
        allied = _allied_kind(s)
        if allied == "fisheries":
            hard = True
            ex.add(Factor("Allied activity", "risk", "Fisheries scheme — no fisheries activity in the farm profile."))
        elif allied == "livestock" and not facts.livestock:
            score -= 30
            ex.add(Factor("Allied activity", "limiting", "Livestock / dairy / poultry scheme — farmer has no livestock recorded.", weight=-30))
        elif allied == "livestock":
            score += 6
            ex.add(Factor("Allied activity", "positive", "Livestock-linked scheme; farmer keeps livestock.", weight=6))

        # ---- soft factors -----------------------------------------------------
        # region relevance
        if str(s.state).lower() == facts.state.lower():
            score += 18
            ex.add(Factor("Relevant state", "positive", f"State scheme for {s.state}.", weight=18))
        elif str(s.state) in uni_region:
            score += 14
            ex.add(Factor("Relevant state", "positive", f"{s.government_level} scheme available across India.", weight=14))
        # income (when not hard-failed)
        if not _isnull(s.income_limit) and facts.income is not None and facts.income <= float(s.income_limit):
            score += 10
            ex.add(Factor("Income criteria satisfied", "positive", f"Income ₹{facts.income:,.0f} ≤ limit ₹{float(s.income_limit):,.0f}.", weight=10))
        elif _isnull(s.income_limit):
            score += 8
            ex.add(Factor("No income ceiling", "positive", "Scheme has no income limit.", weight=8))
        elif facts.income is None:
            score += 4
            ex.add(Factor("Income", "missing", "Annual income not provided — income criterion not verified.", weight=4))
        # land
        lo = 0.0 if _isnull(s.minimum_land) else float(s.minimum_land)
        hi = None if _isnull(s.maximum_land) else float(s.maximum_land)
        if facts.acres >= lo and (hi is None or facts.acres <= hi):
            score += 14
            ex.add(Factor("Land criteria satisfied", "positive", f"{facts.acres:.1f} ac within {lo:g}–{hi if hi is not None else '∞'} ac.", weight=14))
        else:
            if interp.get("scheme_land_range_mode", "scored") == "hard":
                hard = True
            score += 2
            ex.add(Factor("Land criteria", "limiting", f"{facts.acres:.1f} ac outside the KB range {lo:g}–{hi if hi is not None else '∞'} ac.", weight=2))
        # crop
        if v.crop_matches(s.eligible_crop, facts.crop_master, uni_crop):
            score += 12 if str(s.eligible_crop) not in uni_crop else 8
            ex.add(Factor("Crop eligible", "positive", f"Eligible crop: {s.eligible_crop}.", weight=12))
        else:
            ex.add(Factor("Crop focus differs", "limiting", f"KB lists eligible crop '{s.eligible_crop}'; farm grows {facts.crop_master or 'unspecified'}." +
                          (" (soft criterion)" if interp.get("scheme_eligible_crop_mode") == "soft" else ""), weight=0))
            if interp.get("scheme_eligible_crop_mode") == "hard":
                hard = True
        # farmer term
        ft = facts.satisfies_farmer_term(s.eligible_farmer)
        if ft:
            score += 12
            ex.add(Factor("Eligible farmer profile", "positive", f"Profile matches '{s.eligible_farmer}' ({facts.category}).", weight=12))
        elif ft is None:
            score += 5
            ex.add(Factor("Farmer profile", "neutral", f"KB farmer term '{s.eligible_farmer}' could not be verified from profile.", weight=5))
        else:
            ex.add(Factor("Farmer profile differs", "limiting", f"Scheme targets '{s.eligible_farmer}'; profile is {facts.category}, {'tenant/sharecropper' if facts.is_tenant_or_sharecropper else 'landowner'}.", weight=0))
            if interp.get("scheme_eligible_farmer_mode") == "hard":
                hard = True
        # document / prerequisite flags
        # Aadhaar / bank account are genuine gatekeepers (DBT). The KB flags soil-card and insurance as
        # "required" on ~75 % of schemes, which is not how these programmes work; they are treated as
        # *supporting* items (small bonus if held, informational note if not) — see kb_overrides interpretation.
        prereq_ok, prereq_missing, support_missing = 0, [], []
        for flag, have, label in (("aadhaar_required_bool", facts.has_aadhaar, "Aadhaar"), ("bank_account_required_bool", facts.has_bank_account, "bank account")):
            if bool(s[flag]):
                if have:
                    prereq_ok += 1
                else:
                    prereq_missing.append(label)
        soft_mode = interp.get("scheme_soft_prerequisites", ["soil_card_required", "insurance_required"])
        for flag, have, label in (("soil_card_required", facts.has_soil_card, "Soil Health Card"), ("insurance_required", facts.has_insurance, "crop insurance")):
            if bool(s[flag + "_bool"]):
                if have:
                    prereq_ok += 1
                elif flag in soft_mode:
                    support_missing.append(label)
                else:
                    prereq_missing.append(label)
        score += 2 * prereq_ok
        if prereq_missing:
            score -= 6 * len(prereq_missing)
            ex.add(Factor("Prerequisites missing", "limiting", "Scheme requires: " + ", ".join(prereq_missing) + ".", weight=-6 * len(prereq_missing)))
        elif prereq_ok:
            ex.add(Factor("Prerequisites met", "positive", f"{prereq_ok} prerequisite(s) already in place.", weight=2 * prereq_ok))
        if support_missing:
            ex.add(Factor("Supporting items", "neutral", "KB lists " + " and ".join(support_missing) + " as supporting; verify at application (not treated as a blocker).", weight=0))
        # KB priority
        pr = 0.0 if _isnull(s.priority_score) else float(s.priority_score)
        score += pr  # 0..10
        # eligibility-rule boosts
        rules = elig_by_scheme.get(s.scheme_name, [])
        if rules:
            boost = min(15.0, sum(float(r.effective_priority) for r in rules) * 0.8)
            score += boost
            top = rules[0]
            notes = []
            if not top.soil_match:
                notes.append(f"rule soil {top.soil_type} differs from farm soil")
            if not top.land_match:
                notes.append(f"rule land band {top.land_min:.1f}–{top.land_max:.1f} {kb.interpretation.get('eligibility_rules_land_unit', 'acres')[:2]} vs farm {facts.hectares:.2f} ha")
            soil_note = f" (partial weight: {'; '.join(notes)})" if notes else ""
            ex.add(Factor("Eligibility rule fired", "positive",
                          f"{len(rules)} KB rule(s) recommend this scheme for {top.crop} / {top.farmer_category} in {top.state} (e.g. {top.rule_id}: {top.rule_name}){soil_note}.",
                          weight=round(boost, 1), source="Knowledge base · eligibility_rules"))
            ex.kb_references += [r.rule_id for r in rules[:3]]
        # ai-rule boosts
        ai_hits = [r for _, r in ai.iterrows() if any(_ai_rule_names_match(x, s.scheme_name) for x in r.schemes_list)]
        if ai_hits:
            conf = max(float(r.confidence) for r in ai_hits)
            boost = 12.0 * conf
            score += boost
            ex.add(Factor("Profile-segment rule", "positive",
                          f"Recommended for {facts.state} / {ai_hits[0].cond_crop} / {ai_hits[0].cond_land_band} / income {ai_hits[0].cond_income_band} (rule {ai_hits[0].rule_id}, confidence {conf:.2f}).",
                          weight=round(boost, 1), source="Knowledge base · ai_recommendation_rules"))
            ex.kb_references += [f"AI-RULE-{r.rule_id}" for r in ai_hits[:2]]
            ex.data_considered.append("ai-rule reason: " + str(ai_hits[0].reason)[:220])

        score = 0.0 if hard else max(0.0, min(100.0, score))
        doc_ctx = ["livestock"] if allied == "livestock" else []
        if "fpo" in str(s.scheme_name).lower() or "fpo" in str(s.beneficiary_type).lower():
            doc_ctx.append("fpo_member")
        checklist = resolve_documents(kb, facts, list(s.documents_list), scheme_name=s.scheme_name, contexts=doc_ctx)
        lbl = "Not eligible" if hard else score_label(score, 70, 45)
        pos = [f.name for f in ex.positive][:4]
        ex.summary = (f"{lbl} ({score:.0f}%): " + ", ".join(pos) if not hard else f"Not eligible — {ex.risks[0].detail}")
        if checklist.missing_blocking:
            ex.add(Factor("Documents to arrange", "limiting", ", ".join(checklist.missing_blocking[:4]) + ("…" if len(checklist.missing_blocking) > 4 else "")))
        out.append(MatchResult(
            s.scheme_id, s.scheme_name, "scheme", float(score), lbl, ex, hard_fail=hard,
            documents=[i.name for i in checklist.applicable], documents_missing=checklist.missing_blocking,
            payload={"scheme_type": s.scheme_type, "government_level": s.government_level, "state": s.state, "ministry": s.ministry,
                     "objective": s.objective, "description": s.description, "beneficiary_type": s.beneficiary_type,
                     "eligible_crop": s.eligible_crop, "eligible_farmer": s.eligible_farmer,
                     "land_range_acres": [lo, hi], "income_limit": None if _isnull(s.income_limit) else float(s.income_limit),
                     "age_range": [None if _isnull(s.minimum_age) else int(s.minimum_age), None if _isnull(s.maximum_age) else int(s.maximum_age)],
                     "maximum_subsidy": None if _isnull(s.maximum_subsidy) else float(s.maximum_subsidy),
                     "subsidy_percentage": None if _isnull(s.subsidy_percentage) else float(s.subsidy_percentage),
                     "interest_subvention": None if _isnull(s.interest_subvention) else s.interest_subvention,
                     "loan_support": bool(s.loan_support_bool), "processing_time_days": None if _isnull(s.processing_time_days) else int(s.processing_time_days),
                     "application_mode": s.application_mode, "official_portal": s.official_portal, "priority_score": pr,
                     "document_readiness_pct": checklist.readiness_pct, "checklist": checklist,
                     "kb_overrides": [o.column for o in kb.overrides_for("schemes", s.scheme_id)],
                     "fired_rules": [r.rule_id for r in rules], "ai_rules": [int(r.rule_id) for r in ai_hits]},
        ))
    out.sort(key=lambda m: (-m.score, m.hard_fail))
    return [m for m in out if m.score >= min_score][:top_n]
