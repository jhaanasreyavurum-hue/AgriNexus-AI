"""PDF builders for the Bank (Agricultural Credit Intelligence) and Government
(Financial Inclusion & Scheme Monitoring) reports. Every figure is a modelled
aggregate already shown on screen; the basis statement is printed on page 1."""
from __future__ import annotations

from datetime import datetime
from typing import List, Optional

import pandas as pd
from fpdf import FPDF

from ui.report_pdf import _s


class _Doc(FPDF):
    def __init__(self, title: str, subtitle: str, rgb=(18, 60, 105)):
        super().__init__()
        self.title_, self.subtitle_, self.rgb = title, subtitle, rgb
        self.set_auto_page_break(auto=True, margin=16)

    def header(self):
        self.set_fill_color(*self.rgb)
        self.rect(0, 0, 210, 16, "F")
        self.set_y(4)
        self.set_font("Helvetica", "B", 12)
        self.set_text_color(255, 255, 255)
        self.cell(150, 8, _s(f"AgriNexus AI - {self.title_}"), align="L")
        self.set_font("Helvetica", "B", 8.5)
        self.cell(0, 8, "MODELLED / KB-DERIVED", align="R")
        self.ln(14)
        self.set_text_color(18, 38, 28)

    def footer(self):
        self.set_y(-12)
        self.set_font("Helvetica", "I", 7)
        self.set_text_color(120, 130, 125)
        self.cell(0, 6, _s(f"Generated {datetime.now():%Y-%m-%d %H:%M} | modelled indicators from the knowledge base - not observed statistics | page {self.page_no()}"), align="C")

    def h2(self, t):
        self.ln(2); self.set_font("Helvetica", "B", 12); self.set_text_color(*self.rgb)
        self.cell(0, 8, _s(t), new_x="LMARGIN", new_y="NEXT"); self.set_text_color(18, 38, 28)

    def para(self, t, size=9, style=""):
        self.set_font("Helvetica", style, size); self.multi_cell(0, 5, _s(t), new_x="LMARGIN", new_y="NEXT")

    def kv(self, k, v):
        self.set_font("Helvetica", "B", 9); self.cell(52, 5.5, _s(k)); self.set_font("Helvetica", "", 9)
        self.multi_cell(0, 5.5, _s(str(v)), new_x="LMARGIN", new_y="NEXT")

    def bullet(self, t):
        self.set_font("Helvetica", "", 9); self.cell(5, 5, "-"); self.multi_cell(0, 5, _s(t), new_x="LMARGIN", new_y="NEXT")

    def tag(self, t):
        self.set_font("Helvetica", "I", 7.5); self.set_text_color(90, 107, 99)
        self.multi_cell(0, 4, _s(t), new_x="LMARGIN", new_y="NEXT"); self.set_text_color(18, 38, 28)

    def table(self, df: pd.DataFrame, cols: dict, max_rows: int = 15):
        """cols: {src: (label, width_mm, fmt)}"""
        keys = [c for c in cols if c in df.columns]
        self.set_font("Helvetica", "B", 7.5)
        self.set_fill_color(235, 240, 237)
        for c in keys:
            self.cell(cols[c][1], 6, _s(cols[c][0]), border=0, fill=True)
        self.ln(6)
        self.set_font("Helvetica", "", 7.5)
        for _, r in df.head(max_rows).iterrows():
            if self.get_y() > 270:
                self.add_page()
            for c in keys:
                label, w, fmt = cols[c]
                v = r[c]
                if fmt == "inr":
                    txt = inr(v) if pd.notna(v) else "-"
                elif fmt == "pct":
                    txt = f"{v:.0f}%" if pd.notna(v) else "-"
                elif fmt == "num":
                    txt = f"{v:,.1f}" if pd.notna(v) else "-"
                elif fmt == "int":
                    txt = f"{int(v):,}" if pd.notna(v) else "-"
                else:
                    txt = "-" if v is None or (isinstance(v, float) and pd.isna(v)) else str(v)
                txt = _s(txt)
                if len(txt) > int(w / 1.7):
                    txt = txt[: int(w / 1.7) - 1] + "…".encode("latin-1", "ignore").decode("latin-1")
                self.cell(w, 5.5, txt, border="B")
            self.ln(5.5)


def inr(v) -> str:
    v = float(v or 0)
    if v >= 1e7:
        return f"Rs {v / 1e7:.2f} Cr"
    if v >= 1e5:
        return f"Rs {v / 1e5:.1f} lakh"
    return f"Rs {v:,.0f}"


def build_credit_report(ci, user, sections: List[str]) -> bytes:
    pdf = _Doc("Agricultural Credit Intelligence Report", "", (18, 60, 105))
    pdf.add_page()
    k = ci.kpis
    pdf.h2("Scope & basis")
    pdf.kv("Prepared for", f"{user.display_name} ({user.role_label}, {user.organisation or '-'})")
    pdf.kv("Scope", ci.scope_state or "All KB districts")
    pdf.kv("Basis", f"{ci.basis}. Scenario: {ci.scenario_label}")
    for n in ci.notes:
        pdf.tag(n)
    pdf.h2("Headline indicators (modelled)")
    pdf.kv("Potential loan demand", f"{inr(k.get('demand_inr'))} across {k.get('districts')} district(s); {inr(k.get('demand_per_10k_inr'))} per 10,000 households")
    pdf.kv("Potentially eligible farmers", f"{k.get('eligible_households', 0):,.0f} of {k.get('households_modelled', 0):,.0f} scenario households ({k.get('eligible_pct', 0):.0f}%)")
    pdf.kv("Average ticket", inr(k.get("avg_ticket_inr")))
    pdf.kv("Top product / type", f"{k.get('top_product') or '-'} / {k.get('top_loan_type') or '-'}")
    pdf.kv("Most attractive crop", k.get("top_crop") or "-")
    pdf.kv("High-potential districts", f"{k.get('high_potential_districts')} ({k.get('untapped_districts')} with no KB agri-loan desk)")
    pdf.kv("Avg product fit / crop cover", f"{k.get('avg_fit_score', 0):.0f}/100 / {k.get('crop_cover_pct', 0):.0f}% of households")
    if "districts" in sections and len(ci.by_district):
        pdf.h2("High-potential districts (top 15)")
        pdf.table(ci.by_district, {"district": ("District", 34, "str"), "state": ("State", 26, "str"), "crop": ("Major crop", 26, "str"), "eligible_pct": ("Elig %", 14, "pct"),
                                   "demand_inr": ("Demand", 26, "inr"), "loan_desks": ("Desks", 12, "int"), "potential_score": ("Score", 14, "num"), "potential": ("Potential", 16, "str"),
                                   "credit_opportunity": ("Opportunity", 22, "str")})
    if "segments" in sections and len(ci.by_segment):
        pdf.h2("Farmer segments")
        pdf.table(ci.by_segment, {"segment_label": ("Segment", 44, "str"), "households": ("Households", 22, "int"), "eligible_pct": ("Elig %", 16, "pct"), "rating": ("Rating", 18, "str"),
                                  "avg_loan_est_inr": ("Avg ticket", 24, "inr"), "demand_inr": ("Demand", 28, "inr"), "top_loan_type": ("Top type", 38, "str")})
    if "crops" in sections and len(ci.by_crop):
        pdf.h2("Crop credit trends")
        pdf.table(ci.by_crop, {"crop": ("Crop", 36, "str"), "credit_attractiveness": ("Attract.", 16, "num"), "fit_score": ("Fit", 14, "num"), "crop_cover_pct": ("Cover %", 16, "pct"),
                               "avg_subsidies": ("Subsidies", 18, "num"), "crop_specific_products": ("Crop prod.", 18, "int"), "top_product": ("Top product", 72, "str")})
    if "products" in sections and len(ci.by_product):
        pdf.h2("Product demand (top 15)")
        pdf.table(ci.by_product, {"product": ("Product", 64, "str"), "bank": ("Bank", 34, "str"), "loan_type": ("Type", 46, "str"), "eligible_households": ("Elig. HH", 22, "int"), "avg_score": ("Score", 14, "num")})
    if "banks" in sections and len(ci.by_bank):
        pdf.h2("Bank presence vs modelled reach")
        pdf.table(ci.by_bank, {"bank_name": ("Bank", 50, "str"), "branches": ("Branches", 20, "int"), "loan_desks": ("Desks", 18, "int"), "districts": ("Districts", 20, "int"),
                               "products": ("Products", 20, "int"), "modelled_eligible_households": ("Modelled elig. HH", 40, "int")})
    pdf.h2("Method")
    pdf.tag("Real AgriNexus eligibility/matching engines were run for 11 explicit farmer-segment archetypes in every KB district; results were weighted by the stated household scenario. "
            "Eligible = at least one KB loan product scoring >= 50 and eligibility rating not 'Limited'. Potential score = 30 demand density + 25 product fit + 15 crop cover + 30 under-served bonus. "
            "No observed disbursement, demand or enrolment data is included. Use for prioritisation and field validation only.")
    return bytes(pdf.output())


def build_inclusion_report(ii, user, sections: List[str]) -> bytes:
    pdf = _Doc("Financial Inclusion & Scheme Monitoring Report", "", (94, 58, 0))
    pdf.add_page()
    k = ii.kpis
    pdf.h2("Scope & basis")
    pdf.kv("Prepared for", f"{user.display_name} ({user.role_label}, {user.organisation or '-'})")
    pdf.kv("Scope", ii.scope_state or "All KB districts")
    pdf.kv("Basis", f"{ii.basis}. Scenario: {ii.scenario_label}")
    for n in ii.notes:
        pdf.tag(n)
    pdf.h2("Headline indicators (modelled)")
    pdf.kv("Inclusion index", f"{k.get('inclusion_index', 0):.0f}/100 across {k.get('districts')} district(s)")
    pdf.kv("Scheme / credit reach", f"{k.get('scheme_reach_pct', 0):.0f}% / {k.get('credit_reach_pct', 0):.0f}% of scenario households")
    pdf.kv("Insurance / subsidy reach", f"{k.get('insurance_reach_pct', 0):.0f}% / {k.get('subsidy_reach_pct', 0):.0f}%")
    pdf.kv("Schemes with modelled reach", f"{k.get('schemes_active')} (widest: {k.get('top_scheme') or '-'})")
    pdf.kv("Avg eligible schemes / household", f"{k.get('avg_schemes_per_household', 0):.1f}")
    pdf.kv("Districts flagged", f"{k.get('low_districts')} ; weakest segment: {k.get('weakest_segment') or '-'}")
    if "schemes" in sections and len(ii.by_scheme):
        pdf.h2("Scheme reach (top 15)")
        pdf.table(ii.by_scheme, {"scheme": ("Scheme", 80, "str"), "scheme_type": ("Type", 36, "str"), "level": ("Level", 20, "str"), "reach_pct": ("Reach %", 18, "pct"),
                                 "avg_score": ("Score", 14, "num"), "districts": ("Districts", 18, "int")})
    if "districts" in sections and len(ii.by_district):
        pdf.h2("District performance (ranked)")
        pdf.table(ii.by_district, {"rank": ("#", 8, "int"), "district": ("District", 34, "str"), "state": ("State", 26, "str"), "crop": ("Crop", 22, "str"), "inclusion_index": ("Index", 14, "num"),
                                   "scheme_reach_pct": ("Scheme", 14, "pct"), "credit_reach_pct": ("Credit", 14, "pct"), "insurance_reach_pct": ("Insur.", 14, "pct"), "subsidy_reach_pct": ("Subsidy", 14, "pct"),
                                   "relative_band": ("Band", 26, "str")}, max_rows=20)
    if "low" in sections and len(ii.low_adoption):
        pdf.h2("Low-adoption / intervention areas")
        for _, r in ii.low_adoption.head(12).iterrows():
            pdf.bullet(f"{r['district']} ({r['state']}): index {r['inclusion_index']:.0f}; weakest pillar {r.get('weakest_pillar', '-')}; suggested: {r.get('intervention', '-')}")
    if "segments" in sections and len(ii.by_segment):
        pdf.h2("Inclusion by farmer segment")
        pdf.table(ii.by_segment, {"segment_label": ("Segment", 46, "str"), "inclusion_index": ("Index", 16, "num"), "scheme_reach_pct": ("Scheme", 16, "pct"), "credit_reach_pct": ("Credit", 16, "pct"),
                                  "insurance_reach_pct": ("Insur.", 16, "pct"), "subsidy_reach_pct": ("Subsidy", 16, "pct"), "top_scheme": ("Top scheme", 64, "str")})
    if "crops" in sections and len(ii.by_crop_scheme):
        pdf.h2("Crop-wise scheme association (top 20)")
        pdf.table(ii.by_crop_scheme.sort_values("households", ascending=False), {"crop": ("Crop", 36, "str"), "scheme": ("Scheme", 100, "str"), "households": ("Modelled HH", 26, "int"), "avg_score": ("Score", 14, "num")}, max_rows=20)
    pdf.h2("Method")
    pdf.tag("Reach = share of scenario households whose archetype the KB scheme matcher scores as eligible (>= 50). Inclusion index = 25 x [scheme depth + credit rating + insurance cover + subsidy depth]. "
            "Observed adoption (if uploaded by the officer) is compared against modelled reach to derive an adoption gap. No enrolment records are in the knowledge base.")
    return bytes(pdf.output())
