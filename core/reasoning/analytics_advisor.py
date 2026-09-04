"""Role-aware analytics Copilot core for bank managers and government officers.

Answers are composed **only** from the already-computed intelligence objects
(:class:`CreditIntelligence` / :class:`InclusionIntelligence`) and the KB — the
same numbers the dashboards show. Rule-based intent detection; every answer
carries the MODELLED basis, its method labels and the factors used. The
optional LLM narrator (``core.reasoning.narrator``) may rephrase the answer but
never adds figures.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

from core.intelligence import CreditIntelligence, InclusionIntelligence
from core.models.results import Explanation, Factor, Method
from core.reasoning.advisor import Advice

_MODELLED = "Modelled (KB-derived)"


def _inr(v: float) -> str:
    v = float(v or 0)
    if v >= 1e7:
        return f"₹{v / 1e7:,.1f} crore"
    if v >= 1e5:
        return f"₹{v / 1e5:,.1f} lakh"
    return f"₹{v:,.0f}"


def _ex(summary: str, method: Method = Method.RULE_BASED, basis: str = "") -> Explanation:
    ex = Explanation(summary=summary, method=method, sources=[basis or _MODELLED])
    ex.data_considered.append("Segment matrix: KB eligibility engines run over farmer-segment archetypes per district")
    return ex


def _find_district(q: str, districts: List[str]) -> Optional[str]:
    ql = q.lower()
    hits = [d for d in districts if d and d.lower() in ql]
    return max(hits, key=len) if hits else None


def _find_from(q: str, values: List[str]) -> Optional[str]:
    ql = q.lower()
    hits = [v for v in values if isinstance(v, str) and v and v.lower() in ql]
    return max(hits, key=len) if hits else None


# --------------------------------------------------------------------------- bank
BANK_INTENTS: Dict[str, List[str]] = {
    "basis": [r"\breal\b", r"\bsource", r"how (is|are) (this|these|it) (computed|calculated|derived)", r"\bmodel(led)?\b.*\bmean", r"\bactual\b", r"\bassumption"],
    "documents": [r"\bdocument", r"\breadiness", r"\bpaperwork"],
    "banks": [r"\bbranch", r"\bcompetit", r"\bbank(s)? (presence|coverage|network)", r"\bwhich bank"],
    "products": [r"\bproduct", r"\bkcc\b", r"\bkisan credit", r"\bpopular", r"\bloan type", r"\bterm loan", r"\bgold loan"],
    "segments": [r"\bsegment", r"\bwomen\b", r"\bmarginal", r"\bsmall farmer", r"\btenant", r"\birrigat", r"\brainfed", r"\bsc\b|\bst\b|\bobc\b", r"\bcategor", r"\bincome band"],
    "crops": [r"\bcrop", r"\bcotton\b", r"\bpaddy\b|\brice\b", r"\bmaize\b", r"\bsoybean", r"\bchilli", r"\bturmeric", r"\bgroundnut", r"\bsugarcane"],
    "districts": [r"\bdistrict", r"\bwhere\b", r"\barea", r"\bregion", r"\bhigh[- ]potential", r"\bopportunit", r"\bexpand", r"\bmap\b"],
    "demand": [r"\bdemand", r"\bhow much", r"\btotal", r"\bpotential\b", r"\beligible farmers", r"\bhow many", r"\bsummary", r"\boverview"],
}


def bank_advice(ci: CreditIntelligence, question: str, kb=None) -> Advice:
    q = question.strip()
    ql = q.lower()
    scope = ci.scope_state or "all KB districts"
    k = ci.kpis
    d = ci.by_district
    intent = "demand"
    for name, pats in BANK_INTENTS.items():
        if any(re.search(p, ql) for p in pats):
            intent = name
            break
    district = _find_district(q, list(d["district"])) if len(d) else None
    crop = _find_from(q, list(ci.by_crop["crop"])) if len(ci.by_crop) else None
    if district and intent in ("demand", "districts"):
        intent = "district_detail"
    if crop and intent in ("crops", "demand"):
        intent = "crop_detail"

    refs: List[str] = []
    follow: List[str] = ["Which districts have the highest credit opportunity?", "Which segments are under-served?", "How real are these numbers?"]
    methods = [_MODELLED, "Rule-based"]
    basis = ci.basis

    if intent == "basis":
        ans = ("**These figures are modelled, not observed.** The knowledge base holds no loan-demand statistics. The platform runs the same KB eligibility and "
               "loan-matching engines that assess an individual farmer over a grid of farmer-segment archetypes for every district, then weights the results by "
               f"an explicit household scenario ({ci.scenario_label}).\n\n" + "\n".join(f"- {n}" for n in ci.notes) +
               "\n\nTreat outputs as *relative* prioritisation (which district / segment / product ranks higher), not as absolute market size.")
        ex = _ex("Explains provenance of the credit intelligence.", Method.RULE_BASED, basis)
        for n in ci.notes:
            ex.add(Factor("basis", "neutral", n, source=_MODELLED))
        return Advice(q, intent, ans, ex, methods, refs, ["Which product has the widest eligibility?", "Show demand by crop"])

    if intent == "demand":
        ans = (f"**Modelled credit picture — {scope}** ({ci.scenario_label}).\n\n"
               f"- Potential loan demand: **{_inr(k['demand_inr'])}** ({_inr(k['demand_per_10k_inr'])} per 10,000 households)\n"
               f"- Potentially eligible households: **{k['eligible_pct']:.0f}%** of {k['households_modelled']:,.0f} modelled ({k['eligible_households']:,.0f})\n"
               f"- Average modelled ticket: {_inr(k['avg_ticket_inr'])} · average product fit {k['avg_fit_score']:.0f}/100\n"
               f"- High-potential districts: {k['high_potential_districts']} of {k['districts']} · top crop {k['top_crop']} · top product {k['top_product']}\n"
               f"- Document readiness across segments: {k['doc_readiness_pct']:.0f}% (the main conversion brake)")
        ex = _ex("Aggregate of KB eligibility results weighted by the household scenario.", Method.RULE_BASED, basis)
        ex.add(Factor("eligible_pct", "positive", f"{k['eligible_pct']:.0f}% of modelled households clear at least one KB loan product (score ≥50, rating not Limited)", k["eligible_pct"], source=_MODELLED))
        ex.add(Factor("doc_readiness", "limiting", f"Average document readiness {k['doc_readiness_pct']:.0f}% — eligibility ≠ sanction until KYC/land papers are in place", k["doc_readiness_pct"], source=_MODELLED))
        ex.add(Factor("scenario", "neutral", f"Households per district and segment shares follow: {ci.scenario_label}", source=_MODELLED))
        return Advice(q, intent, ans, ex, methods, refs, follow)

    if intent == "districts":
        top = d.sort_values("potential_score", ascending=False).head(5)
        lines = [f"{i + 1}. **{r['district']}** — {r['potential']} potential · demand {_inr(r['demand_inr'])} · {r['eligible_pct']:.0f}% eligible · fit {r['fit_score']:.0f} · {int(r['branches'])} KB branches · opportunity: {r['credit_opportunity']}"
                 for i, (_, r) in enumerate(top.iterrows())]
        ans = f"**Highest-potential districts — {scope}** (modelled):\n\n" + "\n".join(lines)
        untapped = d[(d["potential"] == "High") & (d["branches"] == 0)] if "potential" in d else d.iloc[0:0]
        if len(untapped):
            ans += f"\n\nHigh potential but **no KB branch presence**: {', '.join(untapped['district'].head(6))}."
        ex = _ex("Districts ranked by potential score = eligibility, fit, demand per 10k households, crop cover and branch access.", Method.RULE_BASED, basis)
        for _, r in top.iterrows():
            ex.add(Factor(r["district"], "positive", f"{r['district']}: potential score {r['potential_score']:.0f}, major crop {r['crop'] or '—'}", r["potential_score"], source=_MODELLED))
        return Advice(q, intent, ans, ex, methods, refs, [f"Tell me about {top.iloc[0]['district']}", "Which crops drive demand?"])

    if intent == "district_detail" and district:
        r = d[d["district"] == district].iloc[0]
        ans = (f"**{district}, {r['state']}** — {r['potential']} potential (rank by score: {int((d['potential_score'] > r['potential_score']).sum()) + 1} of {len(d)}).\n\n"
               f"- Major crop (KB district master): {r['crop'] or '—'} · crop insurance notified: {r['crop_cover']}\n"
               f"- Modelled demand {_inr(r['demand_inr'])} from {r['households']:,.0f} households · {r['eligible_pct']:.0f}% potentially eligible · avg loan estimate {_inr(r['avg_loan_est_inr'])}\n"
               f"- Product fit {r['fit_score']:.0f}/100 · document readiness {r['doc_readiness']:.0f}% · avg {r['avg_schemes']:.1f} schemes & {r['avg_subsidies']:.1f} subsidies per household\n"
               f"- KB branches: {int(r['branches'])} ({int(r['loan_desks'])} with agri-loan desks) · KB coverage: {r['coverage']}\n"
               f"- Credit opportunity: **{r['credit_opportunity']}**")
        ex = _ex(f"District row from the modelled credit table for {district}.", Method.RULE_BASED, basis)
        ex.add(Factor("potential", "positive" if r["potential"] == "High" else "neutral", f"Potential score {r['potential_score']:.0f} → {r['potential']}", r["potential_score"], source=_MODELLED))
        if r["branches"] == 0:
            ex.add(Factor("branches", "limiting", "No branch of any KB-listed bank in this district — outreach would rely on BCs / neighbouring branches", source="Knowledge-base lookup"))
        if r["crop_cover"] != "Yes":
            ex.add(Factor("cover", "risk", "No crop-insurance product for the district major crop in the KB → higher unsecured risk", source="Knowledge-base lookup"))
        return Advice(q, intent, ans, ex, methods + ["Knowledge-base lookup"], refs, ["Which segments in this district are eligible?", "Show the products winning here"])

    if intent == "crops":
        c = ci.by_crop.sort_values(["credit_attractiveness", "demand_per_10k_inr"], ascending=False).head(6)
        grid = ci.scope_state is not None  # state scope → crop grid (each crop assessed per 10,000 households)
        lines = [f"{i + 1}. **{r['crop']}** — attractiveness {r['credit_attractiveness']:.0f}/100 · demand {_inr(r['demand_per_10k_inr'])} per 10,000 growers · fit {r['fit_score']:.0f} · "
                 f"{int(r['crop_specific_products'])} crop-specific KB products · cover {r['crop_cover_pct']:.0f}%" + (f" · grown as major crop in {int((d['crop'] == r['crop']).sum())} district(s)" if grid else f" · {int(r['districts'])} district(s)")
                 for i, (_, r) in enumerate(c.iterrows())]
        ans = f"**High-demand crops — {scope}** (modelled; " + ("each crop assessed on a per-10,000-household basis, ranked by credit attractiveness = fit, cover, subsidies, crop-specific products" if grid else "by district major crop") + "):\n\n" + "\n".join(lines)
        ex = _ex("Crops ranked by modelled demand; attractiveness blends fit, cover and crop-specific product depth.", Method.RULE_BASED, basis)
        for _, r in c.iterrows():
            ex.add(Factor(r["crop"], "positive", f"{r['crop']}: {r['credit_attractiveness']} attractiveness, top product {r['top_product']}", source=_MODELLED))
        return Advice(q, intent, ans, ex, methods, refs, [f"Which districts grow {c.iloc[0]['crop']}?", "Which products fit these crops?"])

    if intent == "crop_detail" and crop:
        r = ci.by_crop[ci.by_crop["crop"] == crop].iloc[0]
        dd = d[d["crop"] == crop].sort_values("potential_score", ascending=False)
        ans = (f"**{crop} — {scope}**: credit attractiveness {r['credit_attractiveness']:.0f}/100 (rank {int((ci.by_crop['credit_attractiveness'] > r['credit_attractiveness']).sum()) + 1} of {len(ci.by_crop)} crops).\n\n"
               f"- Modelled demand {_inr(r['demand_per_10k_inr'])} per 10,000 {crop} growers · KB major crop in {len(dd)} district(s)" + (f" ({', '.join(dd['district'].head(6))}{'…' if len(dd) > 6 else ''})" if len(dd) else "") + "\n"
               f"- Product fit {r['fit_score']:.0f}/100 · top product {r['top_product']} · {int(r['crop_specific_products'])} crop-specific KB loan products · KB recommends: {r['kb_recommended_loans'] or '—'}\n"
               f"- Crop insurance available in {r['crop_cover_pct']:.0f}% of these districts · market category (KB): {r['market_category'] or '—'}")
        ex = _ex(f"Crop row from the modelled credit table for {crop}.", Method.RULE_BASED, basis)
        ex.add(Factor("fit", "positive" if r["fit_score"] >= 70 else "limiting", f"Average product fit {r['fit_score']:.0f}/100", r["fit_score"], source=_MODELLED))
        if r["crop_cover_pct"] < 100:
            ex.add(Factor("cover", "risk", f"Crop cover notified in only {r['crop_cover_pct']:.0f}% of {crop} districts", source="Knowledge-base lookup"))
        return Advice(q, intent, ans, ex, methods + ["Knowledge-base lookup"], refs, [f"Tell me about {dd.iloc[0]['district']}" if len(dd) else "Which districts are high potential?"])

    if intent == "products":
        p = ci.by_product.head(6)
        lines = [f"{i + 1}. **{r['product']}** ({r['bank']}, {r['loan_type']}) — {r['eligible_households']:,.0f} eligible households · avg score {r['avg_score']:.0f} · {int(r['districts'])} district(s)"
                 for i, (_, r) in enumerate(p.iterrows())]
        ans = f"**Product demand — {scope}** (modelled wins of KB loan products):\n\n" + "\n".join(lines) + f"\n\nTop loan type overall: **{k['top_loan_type']}**."
        ex = _ex("Products ranked by the number of modelled households for which they are the best-scoring KB match.", Method.RULE_BASED, basis)
        for _, r in p.iterrows():
            ex.add(Factor(r["product"], "positive", f"{r['product']}: avg match score {r['avg_score']:.0f}", r["avg_score"], source="Knowledge-base lookup"))
        return Advice(q, intent, ans, ex, methods + ["Knowledge-base lookup"], refs, ["Which banks have branches where demand is highest?", "Which segments are under-served?"])

    if intent == "segments":
        s = ci.by_segment.copy()
        tag = _find_from(q, sorted({t for ts in s["tags"] for t in str(ts).split(",") if t}))
        sub = s[s["tags"].str.contains(tag, na=False)] if tag else s
        sub = sub.sort_values("eligible_pct")
        lines = [f"- **{r['segment_label']}** — {r['eligible_pct']:.0f}% eligible · avg loan {_inr(r['avg_loan_est_inr'])} · rating {r['rating']} · top product {r['top_product']} · doc readiness {r['doc_readiness']:.0f}%"
                 for _, r in sub.iterrows()]
        ans = f"**Farmer segments — {scope}**" + (f" (filtered: {tag})" if tag else "") + " (modelled, weakest first):\n\n" + "\n".join(lines)
        ex = _ex("Segment archetypes run through the KB loan engine; eligibility = product score ≥50 and rating not Limited.", Method.RULE_BASED, basis)
        for _, r in sub.head(4).iterrows():
            ex.add(Factor(r["segment_id"], "limiting" if r["eligible_pct"] < 50 else "positive", f"{r['segment_label']}: {r['eligible_pct']:.0f}% eligible, {r['households']:,.0f} households", r["eligible_pct"], source=_MODELLED))
        if (s["segment_id"] == "TENANT").any():
            t = s[s["segment_id"] == "TENANT"].iloc[0]
            ex.add(Factor("tenant", "risk", f"Tenant / sharecropper households: {t['eligible_pct']:.0f}% eligible — KB rules require land records or a cultivator certificate", source="Knowledge-base lookup"))
        return Advice(q, intent, ans, ex, methods, refs, ["What documents block conversion?", "Which product suits small farmers?"])

    if intent == "banks":
        b = ci.by_bank.sort_values("modelled_eligible_households", ascending=False).head(8)
        lines = [f"- **{r['bank_name']}** — {int(r['branches'])} KB branches / {int(r['loan_desks'])} agri desks in {int(r['districts'])} district(s) · modelled product wins {r['modelled_eligible_households']:,.0f} households · products: {r['products'] or '—'}"
                 for _, r in b.iterrows()]
        ans = f"**Bank presence vs modelled product wins — {scope}**:\n\n" + "\n".join(lines) + "\n\nBranch directory is a KB reference (Telangana only)."
        ex = _ex("KB branch directory joined to modelled product wins per bank.", Method.KNOWLEDGE_BASE, basis)
        return Advice(q, intent, ans, ex, ["Knowledge-base lookup", _MODELLED], refs, ["Which districts have no branch presence?"])

    if intent == "documents":
        s = ci.by_segment.sort_values("doc_readiness")
        lines = [f"- {r['segment_label']}: {r['doc_readiness']:.0f}%" for _, r in s.head(5).iterrows()]
        ans = (f"**Document readiness — {scope}**: average {k['doc_readiness_pct']:.0f}% (modelled). Lowest segments:\n\n" + "\n".join(lines) +
               "\n\nReadiness compares each segment's assumed document set with the KB checklist of its best-matching product; camp-mode KYC and land-record drives lift conversion fastest.")
        ex = _ex("Document readiness = held documents ÷ KB required documents for the best-fit product.", Method.RULE_BASED, basis)
        return Advice(q, intent, ans, ex, methods + ["Knowledge-base lookup"], refs, ["Which segments are under-served?"])

    return bank_advice(ci, "summary", kb)


# --------------------------------------------------------------------- government
GOV_INTENTS: Dict[str, List[str]] = {
    "basis": [r"\breal\b", r"\bsource", r"how (is|are) (this|these|it) (computed|calculated|derived)", r"\bactual\b", r"\bassumption", r"\bobserved"],
    "low": [r"\blow[- ]adoption", r"\bintervention", r"\bweak", r"\bpriorit", r"\bworst", r"\blagging", r"\bfocus"],
    "segments": [r"\bsegment", r"\bwomen\b", r"\bmarginal", r"\bsmall farmer", r"\btenant", r"\birrigat", r"\brainfed", r"\bexclu"],
    "crop_scheme": [r"\bcrop[- ]wise", r"\bcrop\b.*\bscheme", r"\bscheme.*\bcrop"],
    "schemes": [r"\bscheme", r"\badopt", r"\bpm[- ]kisan", r"\bpmfby", r"\brythu", r"\bcoverage", r"\bwhich (schemes|programmes)"],
    "inclusion": [r"\binclusion", r"\bindex", r"\bcredit reach", r"\binsurance reach", r"\bpillar", r"\bsummary", r"\boverview", r"\bhow many"],
    "districts": [r"\bdistrict", r"\bperform", r"\bbest\b", r"\brank", r"\bwhere\b", r"\bmap\b"],
}


def gov_advice(ii: InclusionIntelligence, question: str, kb=None) -> Advice:
    q = question.strip()
    ql = q.lower()
    scope = ii.scope_state or "all KB districts"
    k = ii.kpis
    d = ii.by_district
    intent = "inclusion"
    for name, pats in GOV_INTENTS.items():
        if any(re.search(p, ql) for p in pats):
            intent = name
            break
    district = _find_district(q, list(d["district"])) if len(d) else None
    scheme = _find_from(q, list(ii.by_scheme["scheme"])) if len(ii.by_scheme) else None
    if district and intent in ("inclusion", "districts", "low"):
        intent = "district_detail"
    if scheme and intent in ("schemes", "inclusion"):
        intent = "scheme_detail"
    methods = [_MODELLED, "Rule-based"]
    basis = ii.basis
    refs: List[str] = []
    obs = "observed_adoption_pct" in d.columns and d["observed_adoption_pct"].notna().any()

    if intent == "basis":
        ans = ("**Adoption and inclusion figures here are modelled, not survey statistics.** The KB holds no enrolment or coverage data. The platform runs the KB scheme, loan, "
               f"insurance and subsidy engines over farmer-segment archetypes per district and weights them by a household scenario ({ii.scenario_label}). The inclusion index is "
               "the household-weighted mean of four pillars (scheme depth, credit, insurance, subsidy), each scored 0–25.\n\n" + "\n".join(f"- {n}" for n in ii.notes) +
               ("\n\nAn observed-adoption upload is active for this session; modelled vs observed gaps are shown where districts match." if obs else
                "\n\nUpload observed adoption on the Scheme Adoption page to compare modelled eligibility against real enrolment."))
        ex = _ex("Explains provenance of the inclusion intelligence.", Method.RULE_BASED, basis)
        for n in ii.notes:
            ex.add(Factor("basis", "neutral", n, source=_MODELLED))
        return Advice(q, intent, ans, ex, methods, refs, ["Which districts need intervention?", "Which schemes have the widest reach?"])

    if intent == "inclusion":
        ans = (f"**Financial-inclusion picture — {scope}** ({ii.scenario_label}).\n\n"
               f"- Inclusion index **{k['inclusion_index']:.0f}/100** across {k['districts']} districts, {k['households_modelled']:,.0f} modelled households\n"
               f"- Scheme reach {k['scheme_reach_pct']:.0f}% · credit reach {k['credit_reach_pct']:.0f}% · insurance cover {k['insurance_reach_pct']:.0f}% · subsidy reach {k['subsidy_reach_pct']:.0f}%\n"
               f"- {k['schemes_active']} KB schemes active in scope · avg {k['avg_schemes_per_household']:.1f} eligible schemes per household · top scheme {k['top_scheme']}\n"
               f"- Weakest segment: {k['weakest_segment']} · districts flagged for intervention: {k['low_districts']}")
        ex = _ex("Household-weighted aggregate of the four inclusion pillars.", Method.RULE_BASED, basis)
        for key, name in (("scheme_reach_pct", "Scheme reach"), ("credit_reach_pct", "Credit reach"), ("insurance_reach_pct", "Insurance cover"), ("subsidy_reach_pct", "Subsidy reach")):
            ex.add(Factor(key, "positive" if k[key] >= 80 else "limiting", f"{name} {k[key]:.0f}%", k[key], source=_MODELLED))
        return Advice(q, intent, ans, ex, methods, refs, ["Which districts have low adoption?", "Which segments are excluded?", "How real are these numbers?"])

    if intent == "schemes":
        s = ii.by_scheme.head(8)
        lines = [f"{i + 1}. **{r['scheme']}** ({r['scheme_type']}, {r['level']}) — modelled reach {r['reach_pct']:.0f}% of households · avg match {r['avg_score']:.0f} · {int(r['districts'])} district(s)"
                 for i, (_, r) in enumerate(s.iterrows())]
        ans = f"**Scheme reach — {scope}** (modelled eligibility, not enrolment):\n\n" + "\n".join(lines)
        ex = _ex("Schemes ranked by modelled households scoring ≥50 in the KB scheme matcher.", Method.KNOWLEDGE_BASE, basis)
        for _, r in s.head(5).iterrows():
            ex.add(Factor(r["scheme"], "positive", f"{r['scheme']}: reach {r['reach_pct']:.0f}%", r["reach_pct"], source="Knowledge-base lookup"))
        return Advice(q, intent, ans, ex, ["Knowledge-base lookup", _MODELLED], refs, ["Which crops are linked to which schemes?", "Which districts have low adoption?"])

    if intent == "scheme_detail" and scheme:
        r = ii.by_scheme[ii.by_scheme["scheme"] == scheme].iloc[0]
        cs = ii.by_crop_scheme[ii.by_crop_scheme["scheme"] == scheme].sort_values("households", ascending=False)
        ans = (f"**{scheme}** ({r['scheme_type']}, {r['level']}) — modelled reach **{r['reach_pct']:.0f}%** of households ({r['modelled_reach_households']:,.0f}) in {int(r['districts'])} district(s), avg match score {r['avg_score']:.0f}."
               + (f"\n\nCrops most associated: {', '.join(cs['crop'].head(6))}." if len(cs) else ""))
        ex = _ex(f"Scheme row from the modelled reach table for {scheme}.", Method.KNOWLEDGE_BASE, basis)
        return Advice(q, intent, ans, ex, ["Knowledge-base lookup", _MODELLED], refs, ["Which districts need intervention?"])

    if intent == "districts":
        best = d.head(3)
        worst = d.tail(3).iloc[::-1]
        ans = (f"**District performance — {scope}** (modelled inclusion index):\n\n"
               "Strongest: " + "; ".join(f"**{r['district']}** {r['inclusion_index']:.0f}" for _, r in best.iterrows()) +
               "\n\nWeakest: " + "; ".join(f"**{r['district']}** {r['inclusion_index']:.0f} ({r['relative_band']})" for _, r in worst.iterrows()) +
               f"\n\nSpread is {d['inclusion_index'].max() - d['inclusion_index'].min():.0f} points; within one state the KB rules are uniform, so variation mainly reflects the district's major crop and insurance notification.")
        ex = _ex("Districts ranked by the modelled inclusion index; bands are relative to the scope.", Method.RULE_BASED, basis)
        for _, r in worst.iterrows():
            ex.add(Factor(r["district"], "limiting", f"{r['district']}: index {r['inclusion_index']:.0f}, major crop {r['crop'] or '—'}", r["inclusion_index"], source=_MODELLED))
        return Advice(q, intent, ans, ex, methods, refs, [f"Tell me about {worst.iloc[0]['district']}", "Which districts need intervention?"])

    if intent == "district_detail" and district:
        r = d[d["district"] == district].iloc[0]
        low = ii.low_adoption[ii.low_adoption["district"] == district]
        ans = (f"**{district}, {r['state']}** — inclusion index **{r['inclusion_index']:.0f}** (rank {int(r['rank'])} of {len(d)}, {r['relative_band']}).\n\n"
               f"- Scheme reach {r['scheme_reach_pct']:.0f}% (avg {r['avg_schemes']:.1f} schemes/household) · credit {r['credit_reach_pct']:.0f}% · insurance {r['insurance_reach_pct']:.0f}% · subsidy {r['subsidy_reach_pct']:.0f}%\n"
               f"- Major crop {r['crop'] or '—'} · {int(r['branches'])} KB branches · KB coverage {r['coverage']}")
        if obs and pd.notna(r.get("observed_adoption_pct")):
            ans += f"\n- Observed adoption (your upload): {r['observed_adoption_pct']:.0f}% → gap vs modelled eligibility {r['adoption_gap_pct']:.0f} pp"
        if len(low):
            ans += f"\n\n⚠ Flagged for intervention — weakest pillar **{low.iloc[0]['weakest_pillar']}**: {low.iloc[0]['intervention']}."
        ex = _ex(f"District row from the modelled inclusion table for {district}.", Method.RULE_BASED, basis)
        for key, name in (("p_scheme", "Scheme"), ("p_credit", "Credit"), ("p_insurance", "Insurance"), ("p_subsidy", "Subsidy")):
            ex.add(Factor(key, "positive" if r[key] >= 0.8 else "limiting", f"{name} pillar {25 * r[key]:.0f}/25", 25 * r[key], source=_MODELLED))
        return Advice(q, intent, ans, ex, methods, refs, ["Which schemes reach this district?", "Which segments are excluded?"])

    if intent == "low":
        low = ii.low_adoption.head(6)
        if low.empty:
            ans = "No districts are flagged in this scope."
        else:
            lines = [f"{i + 1}. **{r['district']}** — index {r['inclusion_index']:.0f} · weakest pillar {r['weakest_pillar']} · {r['intervention']}" for i, (_, r) in enumerate(low.iterrows())]
            ans = f"**Intervention shortlist — {scope}** (bottom 30% of scope by modelled index):\n\n" + "\n".join(lines)
        ex = _ex("Bottom 30% of districts by modelled inclusion index; intervention keyed to the weakest pillar.", Method.RULE_BASED, basis)
        for _, r in low.iterrows():
            ex.add(Factor(r["district"], "limiting", f"{r['district']}: {r['weakest_pillar']} pillar weakest", r["inclusion_index"], source=_MODELLED))
        return Advice(q, intent, ans, ex, methods, refs, [f"Tell me about {low.iloc[0]['district']}" if len(low) else "Show district performance", "How real are these numbers?"])

    if intent == "segments":
        s = ii.by_segment.sort_values("inclusion_index")
        tag = _find_from(q, sorted({t for ts in s["tags"] for t in str(ts).split(",") if t}))
        sub = s[s["tags"].str.contains(tag, na=False)] if tag else s
        lines = [f"- **{r['segment_label']}** — index {r['inclusion_index']:.0f} · scheme {r['scheme_reach_pct']:.0f}% · credit {r['credit_reach_pct']:.0f}% · insurance {r['insurance_reach_pct']:.0f}% · subsidy {r['subsidy_reach_pct']:.0f}% · top scheme {r['top_scheme']}"
                 for _, r in sub.iterrows()]
        ans = f"**Inclusion by segment — {scope}**" + (f" (filtered: {tag})" if tag else "") + " (modelled, weakest first):\n\n" + "\n".join(lines)
        ex = _ex("Segment archetypes through all four KB engines.", Method.RULE_BASED, basis)
        for _, r in sub.head(4).iterrows():
            ex.add(Factor(r["segment_id"], "limiting" if r["inclusion_index"] < 80 else "positive", f"{r['segment_label']}: index {r['inclusion_index']:.0f}", r["inclusion_index"], source=_MODELLED))
        if (s["segment_id"] == "TENANT").any():
            t = s[s["segment_id"] == "TENANT"].iloc[0]
            ex.add(Factor("tenant", "risk", f"Tenant / sharecropper credit reach {t['credit_reach_pct']:.0f}% — land-record requirement in KB loan rules", source="Knowledge-base lookup"))
        return Advice(q, intent, ans, ex, methods, refs, ["Which districts need intervention?"])

    if intent == "crop_scheme":
        cs = ii.by_crop_scheme.sort_values("households", ascending=False)
        crops = cs.groupby("crop")["scheme"].apply(lambda s: ", ".join(list(s)[:3]))
        lines = [f"- **{c}**: {v}" for c, v in crops.head(8).items()]
        ans = f"**Crop-wise scheme association — {scope}** (top KB schemes per district major crop, modelled):\n\n" + "\n".join(lines)
        ex = _ex("Scheme matches grouped by district major crop.", Method.KNOWLEDGE_BASE, basis)
        return Advice(q, intent, ans, ex, ["Knowledge-base lookup", _MODELLED], refs, ["Which schemes have the widest reach?"])

    return gov_advice(ii, "summary", kb)
