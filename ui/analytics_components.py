"""Rendering helpers shared by the bank / government / admin modules.

Everything drawn here is a modelled or KB-derived aggregate; the basis badge
is always rendered next to the figure it qualifies.
"""
from __future__ import annotations

from typing import Iterable, List, Optional, Sequence

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import pydeck as pdk
import streamlit as st

from core.auth import User
from core.intelligence import SEGMENTS, Scenario, DEFAULT_SCENARIO
from ui import state, theme
from ui.components import badge, esc, inr, kpi, md, plot, table

PALETTE = [theme.GREEN, theme.BLUE, theme.AMBER, "#7B61FF", theme.RED, "#0E9F8A", "#B8860B", "#5B6B63", "#2E7D52", "#7A5300"]
LEVEL_COLOR = {"High": theme.GREEN, "Medium": theme.AMBER, "Low": theme.RED, "Upper third": theme.GREEN, "Middle third": theme.AMBER, "Lower third": theme.RED}


def basis_badge(text: str = "MODELLED · KB-derived") -> str:
    return badge(text, "blue")


def modelled_banner(kind: str, notes: Sequence[str], stale: bool = False) -> None:
    head = {"credit": "Modelled agricultural credit intelligence",
            "inclusion": "Modelled scheme-reach & financial-inclusion intelligence"}.get(kind, "Modelled analytics")
    md(f'<div class="an-demo">📐 <b>{esc(head)}.</b> The knowledge base contains <b>no observed</b> loan-demand, enrolment or inclusion statistics. '
       f'Figures below come from running the platform’s real eligibility and matching engines over explicit farmer-segment archetypes for every KB district, '
       f'weighted by a stated household scenario. They are <b>MODELLED / KB-derived</b> indicators for prioritisation — not measured statistics.</div>')
    with st.expander("Method, scenario & caveats"):
        for n in notes:
            st.caption("• " + n)
        st.caption("• Segment archetypes: " + "; ".join(f"{s.label} ({s.acres:g} ac, ₹{s.annual_income_inr:,.0f}/yr, share {s.default_share:.0%})" for s in SEGMENTS))
        if stale:
            st.warning("The segment matrix was built with an earlier KB / override version. Ask an administrator to rebuild it (System Monitoring).")


def not_available(title: str) -> None:
    st.title(title)
    st.error("The modelled segment matrix has not been built on this server. Administrator: run `python3 scripts/build_segment_matrix.py` (≈4 min) or use System Monitoring → Rebuild.")


def scope_selector(user: User, kb, key: str = "scope_state", allow_all: bool = True) -> Optional[str]:
    """State scope shared across a role's pages (session)."""
    states = sorted(kb.geo.state_name.unique())
    opts = (["All India (KB districts)"] if allow_all else []) + states
    default = st.session_state.get(key) or user.home_state or "Telangana"
    if default not in opts:
        default = opts[0]
    pick = st.selectbox("Scope", opts, index=opts.index(default), key=f"{key}_sel", help="KB coverage: deep for Telangana (33 districts, branches, state schemes); moderate for Maharashtra; one representative district for other states.")
    st.session_state[key] = pick
    return None if pick.startswith("All India") else pick


def segment_filter(key: str) -> List[str]:
    tags = {"small_marginal": "Small & marginal", "women": "Women farmers", "irrigated": "Irrigated", "rainfed": "Rainfed", "tenant": "Tenant / sharecropper",
            "fpo": "FPO members", "livestock": "Livestock / allied", "youth": "Young farmers", "medium": "Medium", "large": "Large"}
    picked = st.multiselect("Farmer segments", list(tags), format_func=tags.get, key=key, placeholder="All segments")
    return picked


def kpi_row(items: Sequence[tuple], badge_html: str = "") -> None:
    cols = st.columns(len(items))
    for col, it in zip(cols, items):
        label, value, sub = it[0], it[1], (it[2] if len(it) > 2 else "")
        with col:
            kpi(label, value, sub, badge_html)


def bar_chart(df: pd.DataFrame, x: str, y: str, title: str, color: Optional[str] = None, orientation: str = "h", height: int = 360,
              text_fmt: Optional[str] = None, key: Optional[str] = None, color_map: Optional[dict] = None) -> None:
    if df is None or df.empty:
        st.caption(f"{title}: no data in scope.")
        return
    d = df.copy()
    if orientation == "h":
        d = d.sort_values(y, ascending=True)
        fig = px.bar(d, x=y, y=x, orientation="h", color=color, color_discrete_map=color_map, color_discrete_sequence=PALETTE, text=y if text_fmt else None)
    else:
        fig = px.bar(d, x=x, y=y, color=color, color_discrete_map=color_map, color_discrete_sequence=PALETTE, text=y if text_fmt else None)
    if text_fmt:
        fig.update_traces(texttemplate=text_fmt, textposition="outside", cliponaxis=False)
    fig.update_layout(title=dict(text=title, font=dict(size=14, color=theme.INK)), height=height, margin=dict(l=10, r=10, t=44, b=10),
                      paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", xaxis_title=None, yaxis_title=None, legend_title=None,
                      font=dict(size=11), showlegend=bool(color))
    fig.update_xaxes(gridcolor="#EEF2F0")
    fig.update_yaxes(gridcolor="#EEF2F0")
    plot(fig, key=key)


def donut(df: pd.DataFrame, names: str, values: str, title: str, height: int = 320, key: Optional[str] = None) -> None:
    if df is None or df.empty:
        st.caption(f"{title}: no data.")
        return
    fig = px.pie(df, names=names, values=values, hole=0.55, color_discrete_sequence=PALETTE)
    fig.update_traces(textinfo="percent", textfont_size=10)
    fig.update_layout(title=dict(text=title, font=dict(size=14, color=theme.INK)), height=height, margin=dict(l=10, r=10, t=44, b=10),
                      paper_bgcolor="rgba(0,0,0,0)", legend=dict(font=dict(size=10)))
    plot(fig, key=key)


def district_map(kb, df: pd.DataFrame, value_col: str, label_col: str, level_col: Optional[str] = None, title: str = "", height: int = 430,
                 tooltip_cols: Optional[List[str]] = None) -> None:
    """Bubble map of KB district centroids sized by ``value_col`` and coloured by ``level_col``."""
    geo = kb.geo[["state_name", "district_name", "latitude", "longitude"]].rename(columns={"state_name": "state", "district_name": "district"})
    d = df.merge(geo, on=["state", "district"], how="left").dropna(subset=["latitude", "longitude"]).copy()
    if d.empty:
        st.caption("No mappable districts in scope.")
        return
    vmax = float(d[value_col].max() or 1.0)
    d["radius"] = 6000 + 22000 * (d[value_col] / vmax)
    hexes = {"High": [46, 125, 82], "Medium": [217, 164, 0], "Low": [198, 40, 40], "Upper third": [46, 125, 82], "Middle third": [217, 164, 0], "Lower third": [198, 40, 40]}
    d["color"] = d[level_col].map(lambda v: hexes.get(str(v), [91, 107, 99])) if level_col else [[46, 125, 82]] * len(d)
    d["val_txt"] = d[value_col].map(lambda v: f"{v:,.1f}")
    d["lbl"] = d[label_col].astype(str)
    cols = tooltip_cols or []
    for c in cols:
        d[c] = d[c].astype(str)
    tip = "<b>{lbl}</b><br/>" + f"{value_col}: " + "{val_txt}" + ("<br/>" + "<br/>".join(f"{c}: {{{c}}}" for c in cols) if cols else "")
    layer = pdk.Layer("ScatterplotLayer", data=d[["longitude", "latitude", "radius", "color", "lbl", "val_txt"] + cols], get_position="[longitude, latitude]",
                      get_radius="radius", get_fill_color="color", pickable=True, opacity=0.55, stroked=True, get_line_color=[255, 255, 255], line_width_min_pixels=1)
    span = max(float(d["latitude"].max() - d["latitude"].min()), float(d["longitude"].max() - d["longitude"].min()), 0.5)
    zoom = 6.3 if span < 5 else (4.8 if span < 12 else 3.6)
    view = pdk.ViewState(latitude=float(d["latitude"].mean()), longitude=float(d["longitude"].mean()), zoom=zoom)
    if title:
        md(f'<div style="font-weight:700;font-size:.95rem;margin:.2rem 0">{esc(title)}</div>')
    st.pydeck_chart(pdk.Deck(layers=[layer], initial_view_state=view, map_style=None, tooltip={"html": tip, "style": {"fontSize": "12px"}}), height=height)
    st.caption("Bubble size = " + value_col.replace("_", " ") + (f"; colour = {level_col.replace('_', ' ')}" if level_col else "") + ". District centroids from the KB district master.")


def ranking_table(df: pd.DataFrame, cols: dict, level_col: Optional[str] = None, height: Optional[int] = None) -> None:
    """Show a ranking with friendly column names and INR / % formatting. ``cols``: {source_col: (label, fmt)}; fmt in inr|pct|num|int|str."""
    if df is None or df.empty:
        st.caption("No rows.")
        return
    out = pd.DataFrame(index=df.index)
    for src, (label, fmt) in cols.items():
        if src not in df.columns:
            continue
        s = df[src]
        if fmt == "inr":
            out[label] = s.map(lambda v: inr(v) if pd.notna(v) else "—")
        elif fmt == "pct":
            out[label] = s.map(lambda v: f"{v:.0f}%" if pd.notna(v) else "—")
        elif fmt == "num":
            out[label] = s.map(lambda v: f"{v:,.1f}" if pd.notna(v) else "—")
        elif fmt == "int":
            out[label] = s.map(lambda v: f"{int(v):,}" if pd.notna(v) else "—")
        else:
            out[label] = s.astype(str).replace({"None": "—", "nan": "—"})
    out.insert(0, "#", range(1, len(out) + 1))
    table(out, hide_index=True, height=height)


def download_df(df: pd.DataFrame, label: str, fname: str, key: str) -> None:
    st.download_button(label, df.to_csv(index=False).encode(), file_name=fname, mime="text/csv", key=key)
