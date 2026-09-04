"""Reusable rendering components. Pure presentation — every value shown comes
from a ``core`` result object; nothing is computed here beyond formatting."""
from __future__ import annotations

import html
from typing import Iterable, List, Optional, Sequence

import plotly.graph_objects as go
import streamlit as st

from core.models.results import Explanation, Factor, MatchResult, Method, Opportunity, Recommendation, Risk
from ui import theme

# ----------------------------------------------------------------------------- helpers
def esc(x) -> str:
    return html.escape("" if x is None else str(x))


def inr(v: Optional[float]) -> str:
    if v is None:
        return "—"
    v = float(v)
    if v >= 1e7:
        return f"₹{v / 1e7:.2f} Cr"
    if v >= 1e5:
        return f"₹{v / 1e5:.1f} lakh"
    return f"₹{v:,.0f}"


def score_color(score: Optional[float], strong: float = 75, possible: float = 50) -> str:
    if score is None:
        return theme.GREY
    return theme.GREEN if score >= strong else (theme.AMBER if score >= possible else theme.RED)


def health_color(score: Optional[float]) -> str:
    if score is None:
        return theme.GREY
    return theme.GREEN if score >= 80 else ("#6BA84F" if score >= 65 else (theme.AMBER if score >= 50 else theme.RED))


METHOD_STYLE = {
    Method.RULE_BASED: ("Rule-based", "grey"),
    Method.ML_MODEL: ("ML prediction", "purple"),
    Method.REMOTE_SENSING: ("Remote sensing", "blue"),
    Method.WEATHER: ("Weather result", "blue"),
    Method.KNOWLEDGE_BASE: ("Knowledge base", "green"),
    Method.LLM: ("LLM explanation", "purple"),
    Method.REFERENCE: ("Reference table", "grey"),
}

SEVERITY_STYLE = {"low": "grey", "moderate": "amber", "high": "red", "critical": "red"}
HORIZON_LABEL = {"today": "Today", "24h": "Next 24–48 h", "48h": "Next 48 h", "this_week": "This week",
                 "this_season": "This season", "before_next_season": "Before next season"}
CATEGORY_ICON = {"irrigation": "💧", "nutrient": "🧪", "protection": "🛡️", "finance": "💳", "scheme": "🏛️",
                 "insurance": "☂️", "crop_plan": "🌱", "monitoring": "🛰️"}
OPP_ICON = {"subsidy": "💰", "scheme": "🏛️", "loan": "💳", "insurance": "☂️", "crop_diversification": "🌱", "market": "🏪", "quick_win": "⚡"}


def badge(text: str, kind: str = "grey") -> str:
    return f'<span class="an-badge {kind}">{esc(text)}</span>'


def method_badge(m: Method) -> str:
    lbl, kind = METHOD_STYLE.get(m, (str(m), "grey"))
    return badge(lbl, kind)


def demo_badge(flag: bool) -> str:
    return badge("DEMO DATA", "demo") if flag else ""


def md(html_str: str) -> None:
    st.markdown(html_str, unsafe_allow_html=True)


def _supports_width() -> bool:
    import inspect
    try:
        return "width" in inspect.signature(st.plotly_chart).parameters
    except Exception:
        return False


def plot(fig, key: Optional[str] = None) -> None:
    """Full-width Plotly chart, compatible with Streamlit 1.36 → 1.6x."""
    kw = {"width": "stretch"} if _supports_width() else {"use_container_width": True}
    st.plotly_chart(fig, config={"displayModeBar": False}, key=key, **kw)


def table(df, **kwargs) -> None:
    kw = {"width": "stretch"} if _supports_width() else {"use_container_width": True}
    kwargs.setdefault("hide_index", True)
    kwargs = {k: v for k, v in kwargs.items() if v is not None}
    st.dataframe(df, **kw, **kwargs)


# ------------------------------------------------------------------------------ blocks
def demo_banner(ctx) -> None:
    if ctx.is_demo:
        md('<div class="an-demo">🧪 <b>DEMO farm.</b> Soil, crop, NDVI and finance values are illustrative sample data '
           '(labelled <i>DEMO DATA</i>). Weather can be live (Open-Meteo) and the knowledge-base results are real KB lookups. '
           'Replace with your own farm via <b>Farm Home → Edit farm</b>.</div>')


def kpi(label: str, value: str, sub: str = "", badge_html: str = "") -> None:
    md(f'<div class="an-kpi"><div class="lbl">{esc(label)}</div><div class="val">{esc(value)}</div>'
       f'<div class="sub">{esc(sub)} {badge_html}</div></div>')


def bar(pct: Optional[float], color: Optional[str] = None) -> str:
    if pct is None:
        return '<div class="an-bar"><div style="width:0%"></div></div>'
    c = color or score_color(pct)
    return f'<div class="an-bar"><div style="width:{max(0, min(100, pct)):.0f}%;background:{c}"></div></div>'


def ring(score: Optional[float], color: Optional[str] = None, size: int = 74) -> str:
    c = color or score_color(score)
    pct = 0 if score is None else max(0, min(100, score))
    txt = "n/a" if score is None else f"{score:.0f}"
    inner = size - 16
    return (f'<div class="an-ring" style="width:{size}px;height:{size}px;background:conic-gradient({c} {pct * 3.6:.0f}deg, #EEF2F0 0deg)">'
            f'<div class="inner" style="width:{inner}px;height:{inner}px">{txt}</div></div>')


FACTOR_ICON = {"positive": "✅", "limiting": "⚠️", "risk": "⛔", "neutral": "•", "missing": "❔"}


def factor_lines(factors: Sequence[Factor], limit: int = 6) -> str:
    out = []
    for f in list(factors)[:limit]:
        src = f' <span class="src">· {esc(f.source)}</span>' if f.source else ""
        out.append(f'<div class="an-factor"><div class="ic">{FACTOR_ICON.get(f.effect, "•")}</div>'
                   f'<div><span class="nm">{esc(f.name)}</span> — <span class="dt">{esc(f.detail)}</span>{src}</div></div>')
    return "".join(out)


def explanation_block(ex: Explanation, show_method: bool = True, limit: int = 6) -> None:
    """Full WHY panel: summary, method/provenance badges, factors, data considered, KB refs."""
    badges = (method_badge(ex.method) if show_method else "") + demo_badge(ex.demo_data_used)
    md(f'<div style="margin-bottom:.4rem">{badges}</div>')
    if ex.summary:
        md(f'<div style="font-size:.92rem;margin-bottom:.4rem">{esc(ex.summary)}</div>')
    groups = [("positive", ex.positive), ("limiting", ex.limiting), ("risk", ex.risks), ("missing", ex.missing), ("neutral", ex.neutral)]
    body = "".join(factor_lines(fs, limit) for _, fs in groups if fs)
    if body:
        md(body)
    meta = []
    if ex.data_considered:
        meta.append("<b>Data considered:</b> " + ", ".join(esc(d) for d in ex.data_considered))
    if ex.sources:
        meta.append("<b>Sources:</b> " + ", ".join(esc(s) for s in ex.sources))
    if ex.kb_references:
        meta.append("<b>KB records:</b> " + ", ".join(f'<span class="an-chip">{esc(r)}</span>' for r in ex.kb_references[:8]))
    if meta:
        md('<div style="font-size:.78rem;color:#5B6B63;margin-top:.5rem">' + "<br>".join(meta) + "</div>")


def why_expander(ex: Explanation, label: str = "Why? — factors, method & sources", expanded: bool = False, key: Optional[str] = None) -> None:
    with st.expander(label, expanded=expanded):
        explanation_block(ex)


# -------------------------------------------------------------------- recommendation UI
def nba_hero(rec: Recommendation, is_demo: bool) -> None:
    ex = rec.explanation
    conf = f"confidence {rec.confidence:.0%}" if rec.confidence is not None else "confidence not estimated"
    meta = [HORIZON_LABEL.get(rec.horizon, rec.horizon), f"{CATEGORY_ICON.get(rec.category, '•')} {rec.category}",
            METHOD_STYLE.get(rec.method, (rec.method.value, ""))[0], conf]
    if ex.demo_data_used or is_demo:
        meta.append("uses DEMO data")
    md(f'<div class="an-hero"><div class="eyebrow">Next best action</div>'
       f'<div class="action">{esc(rec.action)}</div>'
       f'<div class="why"><b>Why:</b> {esc(ex.summary)}</div>'
       f'<div class="meta">{"".join(f"<span>{esc(m)}</span>" for m in meta)}</div></div>')


def action_card(rec: Recommendation, idx: Optional[int] = None, key: str = "") -> None:
    ex = rec.explanation
    conf = f"{rec.confidence:.0%}" if rec.confidence is not None else "n/a"
    rank = f'<div class="an-rank">{rec.priority if idx is None else idx}</div>'
    md(f'<div class="an-card tight"><div class="an-row">{rank}<div style="flex:1">'
       f'<div class="title">{CATEGORY_ICON.get(rec.category, "•")} {esc(rec.action)}</div>'
       f'<div class="sub">{esc(ex.summary)}</div>'
       f'<div style="margin-top:.35rem">{badge(HORIZON_LABEL.get(rec.horizon, rec.horizon), "blue")}{method_badge(rec.method)}'
       f'{badge("confidence " + conf, "grey")}{demo_badge(ex.demo_data_used)}</div></div></div></div>')
    why_expander(ex, key=f"why_{key}")


def risk_card(r: Risk) -> None:
    sev = r.severity.value
    md(f'<div class="an-card tight"><div style="display:flex;justify-content:space-between;align-items:center;gap:.6rem">'
       f'<div class="title">{esc(r.title)}</div>{badge(sev.upper() + f" · {r.score:.0f}", SEVERITY_STYLE.get(sev, "grey"))}</div>'
       f'<div class="sub">{esc(r.reason)}</div>'
       f'<div style="font-size:.86rem;margin-top:.35rem"><b>→</b> {esc(r.action)}</div>'
       f'<div style="margin-top:.35rem">{method_badge(r.explanation.method)}{demo_badge(r.explanation.demo_data_used)}</div></div>')


def opportunity_card(o: Opportunity, key: str = "") -> None:
    icon = OPP_ICON.get(o.opportunity_type, "✨")
    val = f'<span class="an-badge green">{esc(o.value_hint)}</span>' if o.value_hint else ""
    md(f'<div class="an-card tight"><div style="display:flex;justify-content:space-between;gap:.6rem;align-items:flex-start">'
       f'<div class="title">{icon} {esc(o.title.lstrip("🌱💳🏛️☂️💰🏪⚡🛡🎯✨ "))}</div>{val}</div>'
       f'<div class="sub">{esc(o.reason)}</div>'
       f'<div style="font-size:.86rem;margin-top:.35rem"><b>→</b> {esc(o.action)}</div>'
       f'<div style="margin-top:.35rem">{method_badge(o.explanation.method)}{badge(f"relevance {o.score:.0f}", "grey")}'
       f'{badge(o.kb_reference, "green") if o.kb_reference else ""}</div></div>')


# ------------------------------------------------------------------------ match cards
def doc_checklist(m: MatchResult) -> None:
    cl = m.payload.get("checklist")
    if cl is None:
        if m.documents:
            md("".join(f'<div class="an-doc">• {esc(d)}</div>' for d in m.documents))
        return
    ready = cl.readiness_pct
    md(f'<div style="font-size:.86rem;font-weight:600">Document readiness {ready:.0f}%</div>{bar(ready)}')
    cols = st.columns(2)
    with cols[0]:
        held = [i for i in cl.items if i.held]
        missing = [i for i in cl.items if not i.held and not i.obtainable_at_application and not i.not_applicable and not i.optional]
        if held:
            md('<div style="font-size:.8rem;font-weight:600;color:#5B6B63">In hand</div>' + "".join(f'<div class="an-doc ok">✓ {esc(i.name)}</div>' for i in held))
        if missing:
            md('<div style="font-size:.8rem;font-weight:600;color:#5B6B63;margin-top:.3rem">To arrange</div>' +
               "".join(f'<div class="an-doc miss">✗ {esc(i.name)}' + (f' <span style="color:#8A9891">· {esc(i.issuing_authority)}</span>' if i.issuing_authority else "") + "</div>" for i in missing))
    with cols[1]:
        forms = [i for i in cl.items if not i.held and i.obtainable_at_application and not i.not_applicable]
        opt = [i for i in cl.items if i.optional and not i.held]
        na = [i for i in cl.items if i.not_applicable]
        if forms:
            md('<div style="font-size:.8rem;font-weight:600;color:#5B6B63">Obtained at application</div>' + "".join(f'<div class="an-doc form">◦ {esc(i.name)}</div>' for i in forms))
        if opt:
            md('<div style="font-size:.8rem;font-weight:600;color:#5B6B63;margin-top:.3rem">May be requested</div>' + "".join(f'<div class="an-doc form">◦ {esc(i.name)}</div>' for i in opt))
        if na:
            md('<div style="font-size:.8rem;font-weight:600;color:#5B6B63;margin-top:.3rem">Not applicable to your profile</div>' +
               "".join(f'<div class="an-doc na">{esc(i.name)}</div>' for i in na))


def match_header(m: MatchResult, rank: int, subtitle: str, chips: Iterable[str] = ()) -> None:
    kind = "green" if m.score >= 75 else ("amber" if m.score >= 50 else "grey")
    chip_html = "".join(f'<span class="an-chip">{esc(c)}</span>' for c in chips if c)
    md(f'<div class="an-row" style="align-items:center"><div class="an-rank">{rank}</div>'
       f'<div style="flex:1"><div class="title" style="font-weight:700">{esc(m.title)}</div><div class="sub">{esc(subtitle)}</div>'
       f'<div style="margin-top:.25rem">{chip_html}</div></div>'
       f'<div style="text-align:right;min-width:120px"><div style="font-weight:800;font-size:1.25rem;color:{score_color(m.score)}">{m.score:.0f}%</div>'
       f'{badge(m.label, kind)}</div></div>{bar(m.score)}')


def positives_and_limits(m: MatchResult, limit: int = 3) -> None:
    ex = m.explanation
    left, right = st.columns(2)
    with left:
        if ex.positive:
            md('<div style="font-size:.8rem;font-weight:700;color:#0F5A35">Why it fits</div>' + factor_lines(ex.positive, limit))
    with right:
        lim = ex.limiting + ex.risks
        if lim:
            md('<div style="font-size:.8rem;font-weight:700;color:#C97A00">Watch-outs</div>' + factor_lines(lim, limit))


# ----------------------------------------------------------------------------- charts
def health_breakdown_chart(breakdown) -> go.Figure:
    names = [b.name for b in breakdown]
    scores = [b.score if b.score is not None else 0 for b in breakdown]
    colors = [health_color(b.score) if b.score is not None else "#D8DFDB" for b in breakdown]
    text = [f"{b.score:.0f} · w {b.weight:.0%}" if b.score is not None else f"not assessed · w {b.weight:.0%}" for b in breakdown]
    fig = go.Figure(go.Bar(x=scores, y=names, orientation="h", marker_color=colors, text=text, textposition="outside",
                           hovertext=[b.explanation.summary for b in breakdown], hoverinfo="text"))
    fig.update_layout(height=260, margin=dict(l=0, r=90, t=8, b=8), xaxis=dict(range=[0, 118], showgrid=True, gridcolor="#EEF2F0", zeroline=False, showticklabels=False),
                      yaxis=dict(autorange="reversed"), plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)", font=dict(size=12))
    return fig


def gauge(score: Optional[float], title: str, color: Optional[str] = None) -> go.Figure:
    c = color or health_color(score)
    fig = go.Figure(go.Indicator(mode="gauge+number", value=0 if score is None else score, number=dict(font=dict(size=40, color=theme.INK)),
                                 title=dict(text=title, font=dict(size=13, color=theme.GREY)),
                                 gauge=dict(axis=dict(range=[0, 100], tickwidth=0, tickcolor="#fff", tickfont=dict(size=9)), bar=dict(color=c, thickness=0.28),
                                            bgcolor="#EEF2F0", borderwidth=0,
                                            steps=[dict(range=[0, 50], color="#FCE8E6"), dict(range=[50, 65], color="#FFF3DF"), dict(range=[65, 80], color="#EEF6E8"), dict(range=[80, 100], color="#E6F4EC")])))
    fig.update_layout(height=210, margin=dict(l=18, r=18, t=40, b=0), paper_bgcolor="rgba(0,0,0,0)")
    return fig


def score_bars(items: List[MatchResult], title: str, height: int = 300) -> go.Figure:
    fig = go.Figure(go.Bar(x=[m.score for m in items], y=[m.title[:42] for m in items], orientation="h",
                           marker_color=[score_color(m.score) for m in items], text=[f"{m.score:.0f}%" for m in items], textposition="outside",
                           hovertext=[m.explanation.summary for m in items], hoverinfo="text"))
    fig.update_layout(title=dict(text=title, font=dict(size=13)), height=height, margin=dict(l=0, r=60, t=34, b=8),
                      xaxis=dict(range=[0, 112], showticklabels=False, showgrid=False), yaxis=dict(autorange="reversed"),
                      plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)", font=dict(size=11))
    return fig


def footer() -> None:
    md('<div class="an-foot">AgriNexus AI · decision support, not a substitute for local agronomic or financial advice. '
       'Scheme, loan and insurance information is drawn from the bundled knowledge base and is indicative — confirm with the issuing '
       'authority, bank or insurer. Rule-based, weather, remote-sensing, knowledge-base and LLM outputs are labelled separately.</div>')
