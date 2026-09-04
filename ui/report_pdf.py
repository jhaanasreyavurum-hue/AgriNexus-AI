"""PDF farm report — renders an existing FarmAssessment (no new logic).

fpdf2's core fonts are Latin-1 only, so text is sanitised (₹ → Rs, dashes,
arrows) to avoid glyph errors on Streamlit Community Cloud where no Unicode
TTF is guaranteed.
"""
from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from fpdf import FPDF

REPL = {"₹": "Rs ", "—": "-", "–": "-", "→": "->", "≈": "~", "·": "|", "×": "x", "✓": "+", "✗": "x", "•": "-", "°": " deg", "‘": "'", "’": "'", "“": '"', "”": '"', "…": "...", "≥": ">=", "≤": "<="}


def _s(x) -> str:
    t = "" if x is None else str(x)
    for k, v in REPL.items():
        t = t.replace(k, v)
    # strip emoji / anything outside latin-1
    return t.encode("latin-1", "ignore").decode("latin-1")


class _PDF(FPDF):
    def __init__(self, farm_name: str, is_demo: bool):
        super().__init__()
        self.farm_name, self.is_demo = farm_name, is_demo
        self.set_auto_page_break(auto=True, margin=16)

    def header(self):
        self.set_fill_color(27, 127, 76)
        self.rect(0, 0, 210, 16, "F")
        self.set_y(4)
        self.set_font("Helvetica", "B", 12)
        self.set_text_color(255, 255, 255)
        name = self.farm_name if len(self.farm_name) <= 60 else self.farm_name[:57] + "..."
        self.cell(160, 8, _s(f"AgriNexus AI - Farm Report - {name}"), align="L")
        if self.is_demo:
            self.set_font("Helvetica", "B", 9)
            self.cell(0, 8, "DEMO DATA", align="R")
        self.ln(14)
        self.set_text_color(18, 38, 28)

    def footer(self):
        self.set_y(-12)
        self.set_font("Helvetica", "I", 7)
        self.set_text_color(120, 130, 125)
        self.cell(0, 6, _s(f"Generated {datetime.now():%Y-%m-%d %H:%M} | decision support, not a substitute for local agronomic/financial advice | page {self.page_no()}"), align="C")

    def h2(self, txt: str):
        self.ln(2)
        self.set_font("Helvetica", "B", 12)
        self.set_text_color(15, 90, 53)
        self.cell(0, 8, _s(txt), new_x="LMARGIN", new_y="NEXT")
        self.set_text_color(18, 38, 28)

    def kv(self, k: str, v: str):
        self.set_font("Helvetica", "B", 9)
        self.cell(48, 5.5, _s(k))
        self.set_font("Helvetica", "", 9)
        self.multi_cell(0, 5.5, _s(v), new_x="LMARGIN", new_y="NEXT")

    def para(self, txt: str, size: int = 9, style: str = ""):
        self.set_font("Helvetica", style, size)
        self.multi_cell(0, 5, _s(txt), new_x="LMARGIN", new_y="NEXT")

    def bullet(self, txt: str, size: int = 9):
        self.set_font("Helvetica", "", size)
        self.cell(5, 5, "-")
        self.multi_cell(0, 5, _s(txt), new_x="LMARGIN", new_y="NEXT")

    def tag(self, txt: str):
        self.set_font("Helvetica", "I", 7.5)
        self.set_text_color(90, 107, 99)
        self.multi_cell(0, 4, _s(txt), new_x="LMARGIN", new_y="NEXT")
        self.set_text_color(18, 38, 28)


def build_pdf(a, sections: List[str], emi_info: Optional[dict] = None) -> bytes:
    ctx = a.ctx
    kr = a.knowledge
    pdf = _PDF(ctx.farm_name, ctx.is_demo)
    pdf.add_page()

    if ctx.is_demo:
        pdf.set_fill_color(255, 247, 223)
        pdf.set_font("Helvetica", "", 8.5)
        pdf.multi_cell(0, 5, _s("DEMO farm: soil, crop, NDVI and finance values are illustrative sample data. Knowledge-base results are real KB lookups; weather may be live."), fill=True, new_x="LMARGIN", new_y="NEXT")

    pdf.h2("Farm")
    pdf.kv("Farm", ctx.farm_name)
    pdf.kv("Farmer", f"{ctx.farmer.name} | {ctx.farmer.land_ownership} | objective {ctx.farmer.primary_objective}")
    pdf.kv("Location", f"{ctx.location.district}, {ctx.location.state} ({ctx.location.agro_climatic_zone or '-'})")
    pdf.kv("Area", f"{ctx.area_acres:.2f} acres ({ctx.area_hectares:.2f} ha)")
    pdf.kv("Crop", f"{ctx.crop.current_crop or '-'} | {ctx.crop.season or ''} | sown {ctx.crop.sowing_date or '-'} | stage {a.stage.current_stage or '-'}")
    pdf.kv("As of", ctx.today().isoformat())
    pdf.kv("Data sources", "; ".join(f"{k}: {v}" for k, v in ctx.data_sources().items()))

    if "financial" in sections and kr is not None:
        from core.reasoning.financial_summary import summarise_finances
        fs = summarise_finances(a)
        pdf.h2("Financial profile & readiness")
        pdf.kv("Farmer category", f"{fs.farmer_category} | income {('Rs %s' % format(fs.income_inr, ',.0f')) if fs.income_inr else 'not provided'} | existing loans Rs {fs.existing_loans_inr:,.0f}")
        pdf.kv("Indicative credit", f"Rs {fs.estimated_credit_inr:,.0f} ({fs.credit_rating}) - rule-based estimate from KB product ranges, not a sanction" if fs.estimated_credit_inr else "not assessed")
        pdf.kv("Eligibility summary", f"{fs.loan_products_strong + fs.loan_products_possible} loan products ({fs.loan_products_strong} strong) | {fs.scheme_strong + fs.scheme_possible} schemes ({fs.scheme_strong} strong) | "
                                      f"{fs.insurance_matches} insurance covers | {fs.subsidy_matches} subsidies (largest cap Rs {fs.subsidy_potential_inr:,.0f})")
        pdf.kv("Financial readiness", f"{fs.financial_readiness:.0f}/100 - {fs.readiness_label}")
        for f in (fs.readiness_explanation.limiting + fs.readiness_explanation.positive + fs.readiness_explanation.neutral)[:5]:
            pdf.bullet(f"{f.name}: {f.detail}")
        pdf.h2("FINANCIAL NEXT BEST ACTION")
        pdf.para(fs.next_best_action.action, 11, "B")
        pdf.para("Why: " + fs.next_best_action.explanation.summary)
        if emi_info:
            pdf.h2("EMI illustration")
            pdf.kv("Inputs", f"Rs {emi_info['principal']:,.0f} at {emi_info['annual_rate_pct']:.2f}% p.a. for {emi_info['tenure_months']} months")
            pdf.kv("Result", f"EMI Rs {emi_info['emi']:,.0f} | total interest Rs {emi_info['total_interest']:,.0f} | total repayment Rs {emi_info['total_repayment']:,.0f}")
            pdf.tag(emi_info.get("method", ""))

    if "nba" in sections:
        pdf.h2("NEXT BEST ACTION")
        nba = a.next_best_action
        pdf.para(nba.action, 11, "B")
        pdf.para("Why: " + nba.explanation.summary)
        pdf.tag(f"Method: {nba.method.value} | horizon {nba.horizon} | confidence {nba.confidence if nba.confidence is not None else 'n/a'} | sources: {', '.join(nba.explanation.sources)}")
        for f in (nba.explanation.risks + nba.explanation.positive + nba.explanation.limiting)[:6]:
            pdf.bullet(f"{f.name}: {f.detail}")
        pdf.h2("Action plan")
        for r in a.actions:
            pdf.bullet(f"{r.priority}. [{r.category} | {r.horizon} | {r.method.value}] {r.action}")

    if "health" in sections:
        pdf.h2("Farm Health")
        pdf.para(f"{a.health.score:.0f}/100 - {a.health.label} (confidence {a.health.confidence:.0%}, {a.health.assessed_weight:.0%} of components assessed)" if a.health.score is not None else "Not assessed", 10, "B")
        for b in a.health.breakdown:
            pdf.bullet(f"{b.name}: {('%.0f' % b.score) if b.score is not None else 'n/a'} ({b.label}, weight {b.weight:.0%}) - {b.explanation.summary}")

    if "risks" in sections:
        pdf.h2(f"Risks ({len(a.risks)})")
        if not a.risks:
            pdf.para("No active risks detected from the available data.")
        for r in a.risks:
            pdf.bullet(f"[{r.severity.value.upper()} {r.score:.0f}] {r.title}: {r.reason} -> {r.action}")

    if "analytics" in sections:
        pdf.h2("Analytics")
        pdf.kv("Stage", a.stage.explanation.summary)
        pdf.kv("NDVI", a.ndvi.explanation.summary + (" [DEMO series]" if a.ndvi.is_demo else ""))
        pdf.kv("Soil", a.soil.explanation.summary)
        pdf.kv("Weather", f"[{a.weather.provider_label or 'unavailable'}] {a.weather.explanation.summary}")
        pdf.kv("Water", f"({a.water.mode}) {a.water.explanation.summary}")

    if kr is not None:
        if "crops" in sections:
            pdf.h2("Crop Advisor")
            for i, m in enumerate(kr.crops[:6], 1):
                pdf.bullet(f"{i}. {m.title} - {m.score:.0f}% {m.label}{' (current)' if m.payload.get('is_current_crop') else ''}: {m.explanation.summary}")
        if "schemes" in sections:
            pdf.h2("Schemes")
            pdf.tag(kr.coverage_note)
            for i, m in enumerate(kr.schemes[:6], 1):
                p = m.payload
                pdf.bullet(f"{i}. {m.title} - {m.score:.0f}% {m.label} | docs {p.get('document_readiness_pct', 0):.0f}% ready | {p.get('scheme_type')} | {m.item_id}")
                pdf.tag("   why: " + "; ".join(f.detail for f in m.explanation.positive[:3]) + (" | to arrange: " + ", ".join(m.documents_missing[:3]) if m.documents_missing else ""))
        if "loans" in sections:
            la = kr.loans
            pdf.h2("Loan Advisor")
            pdf.para(f"Indicative eligibility Rs {la.estimated_eligibility_inr:,.0f} - {la.eligibility_rating} (not a sanction)" if la.estimated_eligibility_inr else "Eligibility not assessed", 10, "B")
            for i, m in enumerate(la.products[:5], 1):
                p = m.payload
                pdf.bullet(f"{i}. {m.title} - {m.score:.0f}% | {p.get('interest_rate')} | Rs {p.get('amount_min'):,}-{p.get('amount_max'):,} | collateral {'yes' if p.get('collateral_required') else 'no'} | docs {p.get('document_readiness_pct', 0):.0f}%")
            if la.branches:
                pdf.tag("Branches: " + "; ".join(f"{b['bank_name']} - {b['branch_name']} ({b['ifsc']})" for b in la.branches[:5]))
            else:
                pdf.tag(la.branch_coverage_note)
        if "insurance" in sections:
            pdf.h2("Insurance (informational)")
            if kr.insurance_gap_note:
                pdf.para(kr.insurance_gap_note)
            for i, m in enumerate(kr.insurance[:5], 1):
                p = m.payload
                pdf.bullet(f"{i}. {m.title} - {m.score:.0f}% | {p.get('coverage_type')} | risk {p.get('covered_risk')} | farmer premium ~{p.get('farmer_premium_pct')}% | {m.item_id}")
        if "subsidies" in sections:
            pdf.h2("Subsidies")
            for i, m in enumerate(kr.subsidies[:6], 1):
                p = m.payload
                pdf.bullet(f"{i}. {m.title} - {m.score:.0f}% | up to Rs {p.get('maximum_amount') or 0:,.0f} | {p.get('subcategory')} | because: {', '.join(p.get('need_hits', [])) or 'general fit'}")
        if "opportunities" in sections:
            pdf.h2("Opportunities")
            for o in kr.opportunities[:8]:
                pdf.bullet(f"{o.title} {('- ' + o.value_hint) if o.value_hint else ''}: {o.reason} -> {o.action}")
        if "documents" in sections:
            pdf.h2("Documents")
            pdf.kv("On record", ", ".join(sorted(kr.facts.documents_held)) or "none")
            need = {}
            for m in kr.schemes[:5] + kr.loans.products[:3] + kr.subsidies[:3]:
                for d in m.documents_missing:
                    need.setdefault(d, []).append(m.title)
            for d, t in sorted(need.items(), key=lambda kv: -len(kv[1])):
                pdf.bullet(f"{d} - needed by {len(t)} match(es)")

    pdf.h2("Method labels")
    pdf.tag("Rule-based = deterministic agronomic rules | Weather result = provider data interpreted by rules | Remote-sensing result = NDVI series (DEMO or uploaded) | "
            "Knowledge-base lookup = bundled KB tables with documented overrides | LLM-generated explanation = optional narrator, rephrasing only. "
            "Scheme/loan/insurance details are indicative; confirm with the issuing authority, bank or insurer.")
    return bytes(pdf.output())
