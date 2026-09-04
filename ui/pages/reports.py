"""📊 Reports — PDF farm report + data exports, all from the existing assessment."""
from __future__ import annotations

import json
from datetime import date

import pandas as pd
import streamlit as st

from ui import state
from ui.components import demo_banner, esc, footer, inr, kpi, md, table
from ui.report_pdf import build_pdf

SECTIONS = {"financial": "Financial profile, eligibility summary, readiness & EMI", "nba": "Next Best Action & action plan", "health": "Farm Health breakdown", "risks": "Risk Center", "analytics": "Analytics summary (stage, NDVI, soil, weather, water)",
            "crops": "Crop Advisor", "schemes": "Schemes", "loans": "Loan Advisor & branches", "insurance": "Insurance (informational)",
            "subsidies": "Subsidies", "opportunities": "Opportunities", "documents": "Document checklist"}


def _matches_df(items, kind: str) -> pd.DataFrame:
    rows = []
    for m in items:
        p = m.payload
        rows.append({"type": kind, "id": m.item_id, "title": m.title, "score": m.score, "label": m.label,
                     "summary": m.explanation.summary, "docs_ready_pct": p.get("document_readiness_pct"),
                     "documents_missing": "; ".join(m.documents_missing), "kb_method": m.explanation.method.value})
    df = pd.DataFrame(rows, columns=["type", "id", "title", "score", "label", "summary", "docs_ready_pct", "documents_missing", "kb_method"])
    return df.astype({"score": "float64", "docs_ready_pct": "float64"})


def render() -> None:
    ctx = state.ensure_context()
    st.title("📊 Reports")
    demo_banner(ctx)
    render_body(ctx, state.get_assessment())


def render_body(ctx, a) -> None:
    kr = a.knowledge

    c = st.columns(4)
    with c[0]:
        kpi("Farm", ctx.farm_name.split("—")[0].strip(), f"{ctx.location.district}, {ctx.location.state}")
    with c[1]:
        kpi("Farm Health", f"{a.health.score:.0f}" if a.health.score is not None else "—", a.health.label)
    with c[2]:
        kpi("Next best action", a.next_best_action.action[:38] + ("…" if len(a.next_best_action.action) > 38 else ""), a.next_best_action.method.value)
    with c[3]:
        kpi("Matches", f"{len(kr.schemes)} / {len(kr.loans.products)} / {len(kr.insurance)} / {len(kr.subsidies)}" if kr else "—", "schemes / loans / insurance / subsidies")

    st.subheader("PDF report — take it to the bank")
    st.caption("Farmer / farm / financial profile, eligibility, recommended loans, schemes, insurance, subsidies, document checklist, EMI illustration, reasons and next best action. Every number is on screen elsewhere in the app; method labels and DEMO flags are preserved.")
    chosen = st.multiselect("Sections", list(SECTIONS), default=list(SECTIONS), format_func=SECTIONS.get)
    if not chosen:
        st.warning("Select at least one section.")
    else:
        emi_info = None
        if "financial" in chosen and st.session_state.get("emi_amt"):
            try:
                from core.finance import emi as _emi
                emi_info = _emi(st.session_state["emi_amt"], st.session_state.get("emi_rate", 7.0), int(st.session_state.get("emi_months", 12))).to_dict()
                st.caption(f"EMI illustration included from the Loans calculator: ₹{emi_info['principal']:,.0f} at {emi_info['annual_rate_pct']:.2f}% for {emi_info['tenure_months']} months.")
            except Exception:
                emi_info = None
        try:
            pdf_bytes = build_pdf(a, chosen, emi_info)
            st.download_button("⬇️ Download PDF report", data=pdf_bytes, file_name=f"agrinexus_{ctx.farm_id}_{date.today().isoformat()}.pdf",
                               mime="application/pdf", type="primary")
            st.caption(f"{len(pdf_bytes) / 1024:.0f} KB")
        except Exception as exc:
            st.error(f"PDF generation failed: {exc}")

    st.subheader("Data exports")
    e1, e2, e3 = st.columns(3)
    with e1:
        summary = a.headline()
        summary["actions"] = [{"priority": r.priority, "action": r.action, "category": r.category, "horizon": r.horizon, "method": r.method.value,
                               "confidence": r.confidence, "why": r.explanation.summary} for r in a.actions]
        summary["risks"] = [{"title": r.title, "severity": r.severity.value, "score": r.score, "reason": r.reason, "action": r.action} for r in a.risks]
        summary["health_breakdown"] = [{"component": b.name, "score": b.score, "weight": b.weight, "label": b.label} for b in a.health.breakdown]
        st.download_button("⬇️ Assessment summary (JSON)", data=json.dumps(summary, indent=2, default=str), file_name=f"agrinexus_{ctx.farm_id}_summary.json", mime="application/json")
    with e2:
        if kr:
            df = _matches_df(kr.schemes, "scheme")
            for items, kind in ((kr.loans.products, "loan"), (kr.insurance, "insurance"), (kr.subsidies, "subsidy"), (kr.crops, "crop")):
                if items:
                    df = pd.concat([df, _matches_df(items, kind)], ignore_index=True) if len(df) else _matches_df(items, kind)
            st.download_button("⬇️ All matches (CSV)", data=df.to_csv(index=False).encode("utf-8"), file_name=f"agrinexus_{ctx.farm_id}_matches.csv", mime="text/csv")
    with e3:
        st.download_button("⬇️ Farm Digital Twin (JSON)", data=json.dumps(ctx.to_dict(), indent=2, default=str), file_name=f"{ctx.farm_id}.json", mime="application/json",
                           help="Re-loadable farm context with provenance for every block.")

    st.subheader("Preview — action plan")
    table(pd.DataFrame([{"#": r.priority, "Action": r.action, "Category": r.category, "Horizon": r.horizon, "Method": r.method.value,
                         "Confidence": f"{r.confidence:.0%}" if r.confidence is not None else "n/a"} for r in a.actions]))
    if kr:
        st.subheader("Preview — top matches")
        prev = pd.DataFrame()
        for items, kind in ((kr.schemes[:5], "scheme"), (kr.loans.products[:3], "loan"), (kr.insurance[:3], "insurance"), (kr.subsidies[:3], "subsidy")):
            if items:
                prev = pd.concat([prev, _matches_df(items, kind)], ignore_index=True) if len(prev) else _matches_df(items, kind)
        if len(prev):
            table(prev[["type", "title", "score", "label", "docs_ready_pct", "documents_missing"]])
    footer()
