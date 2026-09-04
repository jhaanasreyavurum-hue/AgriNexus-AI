"""``generate_farm_advice(farm_context, question)`` — the Copilot's brain (§17).

Rule-based, context-aware intent routing over the FarmAssessment (and, from
Phase 3, the knowledge engines). Returns an :class:`Advice` with the answer,
the evidence factors, method labels and the KB references used. The optional
LLM narrator (``narrator.py``) may rephrase ``Advice`` but never changes the
recommendation.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from core.models.farm_context import FarmContext
from core.models.results import Explanation, Factor, Method
from core.reasoning.assessment import FarmAssessment, assess_farm

INTENTS: Dict[str, List[str]] = {
    "irrigation": [r"irrigat", r"water(ing)?\b", r"moisture", r"should i water"],
    "health": [r"health", r"decreas", r"declin", r"going down", r"how is my farm", r"status"],
    "stress": [r"stress", r"yellow", r"wilt", r"ndvi", r"vegetation", r"canopy"],
    "risk": [r"\brisk", r"danger", r"threat", r"drought", r"flood", r"heat", r"rain"],
    "crop_choice": [r"which crop", r"best crop", r"what (should|can) i (grow|sow|plant)", r"next season", r"crop recommend"],
    "schemes": [r"scheme", r"subsid", r"pm-?kisan", r"rythu", r"government", r"yojana"],
    "loans": [r"\bloan", r"credit", r"kcc", r"finance", r"borrow", r"bank"],
    "insurance": [r"insur", r"pmfby", r"bima", r"cover"],
    "soil": [r"\bsoil", r"fertili[sz]", r"nutrient", r"organic carbon", r"\bph\b", r"npk"],
    "weather": [r"weather", r"forecast", r"temperature", r"rainfall"],
    "stage": [r"stage", r"harvest", r"timeline", r"days after", r"flowering"],
    "next_action": [r"what should i do", r"next (best )?action", r"what now", r"priority", r"today"],
    "opportunities": [r"opportunit", r"benefit", r"what (can|could) i (get|claim|avail)", r"money"],
    "documents": [r"document", r"paper", r"certificate", r"passbook", r"what do i need to apply"],
}


@dataclass
class Advice:
    question: str
    intent: str
    answer: str                                # rule-based answer text
    explanation: Explanation
    method_labels: List[str] = field(default_factory=list)
    kb_references: List[str] = field(default_factory=list)
    follow_ups: List[str] = field(default_factory=list)
    narrated: Optional[str] = None             # filled by LLM narrator if enabled
    data: Dict[str, Any] = field(default_factory=dict)


def detect_intent(question: str) -> str:
    q = question.lower()
    scores = {k: sum(1 for p in pats if re.search(p, q)) for k, pats in INTENTS.items()}
    best = max(scores, key=scores.get)
    return best if scores[best] > 0 else "next_action"


def _fmt_factors(ex: Explanation, limit: int = 4) -> str:
    lines = []
    for f in ex.risks[:limit]:
        lines.append(f"⚠ {f.detail}")
    for f in ex.limiting[:limit]:
        lines.append(f"– {f.detail}")
    for f in ex.neutral[:limit]:
        lines.append(f"· {f.detail}")
    for f in ex.positive[:limit]:
        lines.append(f"✓ {f.detail}")
    for f in ex.missing[:2]:
        lines.append(f"? {f.detail}")
    return "\n".join(lines)


def generate_farm_advice(ctx: FarmContext, kb, question: str, assessment: Optional[FarmAssessment] = None,
                         knowledge_results: Optional[Dict[str, Any]] = None) -> Advice:
    """Answer a farmer question using the farm context.

    ``knowledge_results`` (Phase 3) may carry pre-computed scheme / loan /
    insurance / crop-advisor matches; until then those intents return a
    KB-lookup-lite answer from crop_master's recommended lists.
    """
    a = assessment or assess_farm(ctx, kb)
    intent = detect_intent(question)
    kr = knowledge_results or (a.knowledge.as_advisor_dict() if getattr(a, "knowledge", None) else {})
    demo_note = " (Note: this farm uses DEMO data.)" if ctx.is_demo else ""
    refs: List[str] = []

    if intent == "irrigation":
        nba = a.actions[0]
        ex = nba.explanation
        ans = f"{nba.action}\n\nWhy: {ex.summary}\n{_fmt_factors(ex)}"
        methods = [Method.RULE_BASED.value, Method.WEATHER.value] + ([Method.REMOTE_SENSING.value] if a.ndvi.available else [])
        fu = ["What is causing crop stress?", "What is the 7-day weather outlook?"]

    elif intent in ("health", "stress"):
        h = a.health
        ex = h.explanation if intent == "health" else (a.ndvi.explanation if a.ndvi.available else h.explanation)
        weakest = sorted([b for b in h.breakdown if b.available and b.score is not None], key=lambda b: b.score)
        drivers = "; ".join(f"{b.name} {b.score:.0f}" for b in weakest[:3])
        ans = (f"Farm health is {h.score:.0f}/100 ({h.label}).{demo_note}\nWeakest components: {drivers}.\n"
               f"{a.ndvi.explanation.summary if a.ndvi.available else 'No NDVI data.'}\n{_fmt_factors(ex)}")
        if a.risks:
            ans += f"\nTop risk: {a.risks[0].title} — {a.risks[0].reason}"
        methods = [Method.RULE_BASED.value, Method.REMOTE_SENSING.value]
        fu = ["Should I irrigate today?", "What risks does my farm face?"]

    elif intent == "risk":
        if a.risks:
            body = "\n".join(f"• [{r.severity.value.upper()}] {r.title}: {r.reason} → {r.action}" for r in a.risks[:5])
        else:
            body = "No active risk detected from current data."
        ex = a.risks[0].explanation if a.risks else Explanation(summary="No risks")
        ans = f"{len(a.risks)} active risk(s) detected:{demo_note}\n{body}"
        methods = [Method.RULE_BASED.value, Method.WEATHER.value]
        fu = ["Which insurance covers these risks?", "Should I irrigate today?"]

    elif intent == "weather":
        w = a.weather
        ex = w.explanation
        sig = "\n".join(f"• {s.title} ({s.value}): {s.meaning} → {s.action}" for s in w.signals[:5]) if w.available else "Weather data unavailable."
        ans = f"Weather interpretation [{w.provider_label}]:\n{sig}"
        methods = [Method.WEATHER.value]
        fu = ["Should I irrigate today?", "Is there an excess-rainfall risk?"]

    elif intent == "soil":
        s = a.soil
        ex = s.explanation
        ans = f"{s.explanation.summary}{demo_note}\n{_fmt_factors(ex, 6)}"
        methods = [Method.RULE_BASED.value]
        fu = ["Which crop suits my soil?", "Which subsidies cover soil health inputs?"]

    elif intent == "stage":
        st = a.stage
        ex = st.explanation
        ans = st.explanation.summary + ("\n" + "\n".join(f"• {r.name}: day {r.start_day}–{r.end_day} [{r.status}]" for r in st.stages) if st.available else "")
        methods = [Method.RULE_BASED.value, Method.REFERENCE.value]
        fu = ["Should I irrigate today?", "When should I stop irrigating before harvest?"]

    elif intent in ("crop_choice", "schemes", "loans", "insurance"):
        key = {"crop_choice": "crops", "schemes": "schemes", "loans": "loans", "insurance": "insurance"}[intent]
        items = kr.get(key)
        if key == "insurance" and not items and kr.get("insurance_gap_note"):
            ex = Explanation(summary=kr["insurance_gap_note"], method=Method.KNOWLEDGE_BASE, sources=["Knowledge base · crop_insurance_products"])
            return Advice(question, intent, kr["insurance_gap_note"] + demo_note, ex, [Method.KNOWLEDGE_BASE.value], [], ["Which schemes apply to me?"])
        if items:
            top = items[:3]
            lines = []
            for i, m in enumerate(top):
                pos = "; ".join(f.detail for f in m.explanation.positive[:2])
                extra = ""
                if key == "insurance":
                    extra = f" · farmer premium ≈{m.payload['farmer_premium_pct']}% (informational)"
                if key == "loans":
                    extra = f" · {m.payload['interest_rate']}, {m.payload['bank_short']}"
                if key == "schemes" and m.documents_missing:
                    extra = f" · arrange: {', '.join(m.documents_missing[:2])}"
                lines.append(f"{i+1}. {m.title} — {m.score:.0f}%{extra}\n   ✓ {pos}")
            body = "\n".join(lines)
            refs = [m.item_id for m in top]
            ex = top[0].explanation
            head = {"crops": "Ranked crop options", "schemes": "Schemes you may be eligible for", "loans": "Loan products that fit", "insurance": "Insurance covers that fit"}[key]
            if key == "loans" and kr.get("loan_advice") is not None:
                la = kr["loan_advice"]
                head += f" (indicative eligibility ₹{la.estimated_eligibility_inr:,.0f}, {la.eligibility_rating})"
            if key == "insurance" and kr.get("insurance_gap_note"):
                head = "No crop cover notified for your district in the knowledge base; livestock covers that fit"
                body = kr["insurance_gap_note"] + "\n" + body
            ans = f"{head}:{demo_note}\n{body}"
        else:
            # Phase-2 fallback: crop_master recommended lists (KB lookup)
            row = a.crop_row
            ex = Explanation(summary="Knowledge-base lookup from crop_master for the current crop.", method=Method.KNOWLEDGE_BASE,
                             sources=["Knowledge base · crop_master"], kb_references=[row.get("crop_id", "")])
            if key == "schemes" and row:
                ans = f"Schemes linked to {row['crop_name']} in the knowledge base: {row['recommended_schemes']}.\nPersonalised eligibility matching arrives with the Scheme Finder engine."
            elif key == "loans" and row:
                ans = f"Loan products linked to {row['crop_name']} in the knowledge base: {row['recommended_loans']}."
            elif key == "insurance" and row:
                ans = f"Insurance available for {row['crop_name']}: {row['insurance_available']}. Active risks to cover: " + (", ".join(r.title for r in a.risks) or "none detected") + "."
            else:
                ans = "Crop recommendations require the Crop Advisor engine (Phase 3)."
            refs = [row.get("crop_id", "")] if row else []
        methods = [Method.KNOWLEDGE_BASE.value, Method.RULE_BASED.value]
        fu = ["What documents do I need?", "What is my next best action?"]

    elif intent == "opportunities":
        opps = kr.get("opportunities") or []
        ex = opps[0].explanation if opps else Explanation(summary="No opportunities computed.")
        body = "\n".join(f"• {o.title}" + (f" — {o.value_hint}" if o.value_hint else "") + f"\n   {o.reason}\n   → {o.action}" for o in opps[:5]) or "Run the knowledge engines to detect opportunities."
        ans = f"Opportunities detected for your farm:{demo_note}\n{body}"
        refs = [o.kb_reference for o in opps[:5] if o.kb_reference]
        methods = [Method.KNOWLEDGE_BASE.value, Method.RULE_BASED.value]
        fu = ["What documents do I need?", "Which insurance covers my risks?"]

    elif intent == "documents":
        sch = (kr.get("schemes") or [])[:2]
        lo = (kr.get("loans") or [])[:1]
        ex = sch[0].explanation if sch else Explanation(summary="No matches computed.")
        parts = []
        for m in sch + lo:
            miss = ", ".join(m.documents_missing) if m.documents_missing else "none missing"
            parts.append(f"• {m.title}: needs {len(m.documents)} documents; to arrange → {miss}")
        held = sorted(a.knowledge.facts.documents_held) if getattr(a, "knowledge", None) else []
        ans = ("Documents on record: " + (", ".join(held) or "none") + f"{demo_note}\n" + "\n".join(parts)) if parts else "Run the scheme/loan matchers first."
        refs = [m.item_id for m in sch + lo]
        methods = [Method.KNOWLEDGE_BASE.value]
        fu = ["What schemes may apply to me?", "What loan options may suit me?"]

    else:  # next_action
        nba = a.actions[0]
        ex = nba.explanation
        others = "\n".join(f"{r.priority}. {r.action}" for r in a.actions[1:4])
        ans = (f"NEXT BEST ACTION: {nba.action}\nWhy: {ex.summary}{demo_note}\n{_fmt_factors(ex)}"
               + (f"\n\nThen:\n{others}" if others else ""))
        methods = [Method.RULE_BASED.value]
        fu = ["Why is my farm health at this level?", "What schemes may apply to me?"]

    ex.kb_references = list(dict.fromkeys((ex.kb_references or []) + refs))
    return Advice(question, intent, ans, ex, methods, ex.kb_references, fu, None, a.headline())
