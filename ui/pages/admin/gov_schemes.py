"""🎯 Government Schemes — scheme registry: view, add, update, deactivate (authorised; session overlay)."""
from __future__ import annotations

import pandas as pd
import streamlit as st

from core.auth import Permission, PermissionDenied
from ui import state
from ui.analytics_components import bar_chart, donut, download_df, kpi_row, ranking_table
from ui.components import badge, esc, footer, md
from ui.pages.admin._common import change_log_panel, flash, guard, rerun_after, storage_notice

_STATES = ["All India", "Telangana", "Maharashtra", "Andhra Pradesh", "Karnataka", "Tamil Nadu", "Gujarat", "Madhya Pradesh", "Rajasthan", "Uttar Pradesh", "Punjab", "Haryana", "Bihar", "Odisha", "West Bengal", "Chhattisgarh", "Kerala"]


def _add_form(user, reg, types, farmers, crops) -> None:
    with st.form("add_scheme", border=True):
        st.markdown("**Add a government scheme**")
        c1, c2, c3 = st.columns(3)
        with c1:
            name = st.text_input("Scheme name *")
            stype = st.selectbox("Scheme type *", types)
            level = st.selectbox("Government level *", ["Central", "State"])
            state_ = st.selectbox("Applies in", _STATES)
        with c2:
            crop = st.selectbox("Eligible crop", ["All Crops"] + crops)
            farmer = st.selectbox("Eligible farmer", farmers)
            min_land = st.number_input("Minimum land (acres, 0 = none)", 0.0, 100.0, 0.0, 0.5)
            max_land = st.number_input("Maximum land (acres, 0 = none)", 0.0, 500.0, 0.0, 0.5)
        with c3:
            income = st.number_input("Income limit ₹ (0 = none)", 0, 10_000_000, 0, 50_000)
            max_sub = st.number_input("Maximum benefit ₹ (0 = n/a)", 0, 100_000_000, 0, 1_000)
            pct = st.number_input("Subsidy % (0 = n/a)", 0, 100, 0, 5)
            mode = st.selectbox("Application mode", ["Online", "Offline", "Online and Offline (CSC)"])
        docs = st.text_input("Documents required (semicolon-separated)", value="Aadhaar Card; Bank Passbook; Land Ownership / Pattadar Passbook")
        objective = st.text_area("Objective / benefit summary", value="", height=70)
        portal = st.text_input("Official portal (URL)", value="")
        ok = st.form_submit_button("Add scheme", type="primary")
    if ok:
        fields = {"scheme_name": name.strip(), "scheme_type": stype, "government_level": level if level == "Central" else (state_ if state_ != "All India" else "State"),
                  "state": state_, "eligible_crop": crop, "eligible_farmer": farmer, "beneficiary_type": farmer,
                  "minimum_land": float(min_land) if min_land > 0 else None, "maximum_land": float(max_land) if max_land > 0 else None,
                  "income_limit": int(income) if income > 0 else None, "maximum_subsidy": int(max_sub) if max_sub > 0 else None, "subsidy_percentage": int(pct) if pct > 0 else None,
                  "application_mode": mode, "documents_required": docs, "objective": objective.strip(), "official_portal": portal.strip() or None,
                  "active_status": "Active", "aadhaar_required": "Yes" if "aadhaar" in docs.lower() else "No", "bank_account_required": "Yes" if "bank" in docs.lower() else "No",
                  "priority_score": 5.0}
        if max_land > 0 and min_land > max_land:
            st.error("Minimum land cannot exceed maximum land.")
            return
        try:
            rec = reg.add(user, "schemes", fields)
        except (PermissionDenied, ValueError) as exc:
            st.error(str(exc))
        else:
            rerun_after("gs_flash", f"Added {rec.key} — {fields['scheme_name']} (session-only, not persisted). Farmer scheme matching on this server now includes it; the pre-built analytics matrix is unaffected until rebuilt.")


def _num(v, default=0) -> int:
    x = pd.to_numeric(v, errors="coerce")
    return default if pd.isna(x) else int(x)


def _update_form(user, reg, view: pd.DataFrame) -> None:
    ids = list(view["scheme_id"].astype(str))
    labels = dict(zip(ids, view["scheme_id"].astype(str) + " · " + view["scheme_name"].astype(str)))
    pick = st.selectbox("Scheme to update", ids, format_func=labels.get, key="gs_pick")
    row = view[view["scheme_id"].astype(str) == pick].iloc[0]
    with st.form("upd_scheme", border=True):
        c1, c2 = st.columns(2)
        with c1:
            max_sub = st.number_input("Maximum benefit ₹", 0, 100_000_000, _num(row["maximum_subsidy"]), 1_000)
            pct = st.number_input("Subsidy %", 0, 100, min(100, _num(row["subsidy_percentage"])), 5)
            income = st.number_input("Income limit ₹ (0 = none)", 0, 10_000_000, _num(row["income_limit"]), 50_000)
        with c2:
            mode = st.selectbox("Application mode", ["Online", "Offline", "Online and Offline (CSC)"], index=["Online", "Offline", "Online and Offline (CSC)"].index(row["application_mode"]) if row["application_mode"] in ("Online", "Offline", "Online and Offline (CSC)") else 0)
            portal = st.text_input("Official portal", value="" if pd.isna(row["official_portal"]) else str(row["official_portal"]))
            status = st.selectbox("Status", ["Active", "Inactive"], index=0 if str(row["active_status"]).lower() == "active" else 1)
        objective = st.text_area("Objective", value="" if pd.isna(row["objective"]) else str(row["objective"]), height=70)
        b1, b2 = st.columns(2)
        ok = b1.form_submit_button("Save update", type="primary")
        deact = b2.form_submit_button("Remove from registry")
    if ok:
        fields = {"maximum_subsidy": int(max_sub) if max_sub > 0 else None, "subsidy_percentage": int(pct) if pct > 0 else None, "income_limit": int(income) if income > 0 else None,
                  "application_mode": mode, "official_portal": portal.strip() or None, "active_status": status, "objective": objective.strip()}
        try:
            reg.update(user, "schemes", pick, fields)
        except (PermissionDenied, ValueError, KeyError) as exc:
            st.error(str(exc))
        else:
            rerun_after("gs_flash", f"Updated {pick} (session-only, not persisted).")
    if deact:
        try:
            reg.deactivate(user, "schemes", pick)
        except PermissionDenied as exc:
            st.error(str(exc))
        else:
            rerun_after("gs_flash", f"Removed {pick} from the active registry (session-only).")


def render() -> None:
    user = guard(Permission.REGISTRY_MANAGE)
    st.title("🎯 Government Schemes")
    kb = state.get_kb()
    reg = state.get_registry()
    storage_notice(reg)
    flash("gs_flash")
    view = reg.view("schemes")
    active = view[(view["status"] == "active") & (view["active_status"].astype(str).str.lower() == "active")]
    types = sorted(view["scheme_type"].dropna().astype(str).unique())
    farmers = sorted(view["eligible_farmer"].dropna().astype(str).unique())
    crops = sorted(kb.crops["crop_name"].dropna().astype(str).unique())
    ov = [o for o in kb.override_log if o.table == "schemes"]
    kpi_row([("Active schemes", str(len(active)), f"{int((view['status'] == 'inactive').sum())} removed this session"),
             ("Central / state", f"{int((active['government_level'] == 'Central').sum())} / {int((active['government_level'] != 'Central').sum())}", "government level"),
             ("Scheme types", str(active["scheme_type"].nunique()), ""),
             ("KB overrides on schemes", str(len(ov)), "documented corrections (kb_overrides.yaml)"),
             ("Session changes", str(len(reg.change_log("schemes"))), "not persisted" if not reg.persistent else "persisted")], badge("KNOWLEDGE BASE + session overlay", "green"))

    c1, c2, c3 = st.columns(3)
    ft = c1.multiselect("Scheme type", types, key="gs_type", placeholder="All types")
    fl = c2.multiselect("Level", sorted(view["government_level"].dropna().astype(str).unique()), key="gs_level", placeholder="All levels")
    fs = c3.selectbox("Status", ["active", "all", "inactive"], key="gs_status")
    v = view.copy()
    if ft:
        v = v[v["scheme_type"].isin(ft)]
    if fl:
        v = v[v["government_level"].isin(fl)]
    if fs == "active":
        v = v[(v["status"] == "active") & (v["active_status"].astype(str).str.lower() == "active")]
    elif fs == "inactive":
        v = v[(v["status"] == "inactive") | (v["active_status"].astype(str).str.lower() != "active")]
    st.caption(f"{len(v)} scheme(s). Session additions/updates are marked in 'Origin'.")
    ranking_table(v.sort_values(["government_level", "scheme_type"]),
                  {"scheme_id": ("ID", "str"), "scheme_name": ("Scheme", "str"), "scheme_type": ("Type", "str"), "government_level": ("Level", "str"), "state": ("State", "str"),
                   "eligible_crop": ("Crop", "str"), "eligible_farmer": ("Farmer", "str"), "maximum_subsidy": ("Max benefit ₹", "inr"), "subsidy_percentage": ("Subsidy %", "pct"),
                   "income_limit": ("Income limit ₹", "inr"), "application_mode": ("Apply via", "str"), "active_status": ("KB status", "str"), "status": ("Registry", "str"), "origin": ("Origin", "str")}, height=420)
    download_df(v, "Download scheme registry (CSV)", "government_schemes.csv", "dl_gs")

    c4, c5 = st.columns(2)
    with c4:
        bar_chart(active.groupby("scheme_type").size().rename("n").reset_index().sort_values("n"), "scheme_type", "n", "Active schemes by type", key="gs_bar", height=380, text_fmt="%{text}")
    with c5:
        donut(active.groupby("eligible_farmer").size().rename("n").reset_index(), "eligible_farmer", "n", "Target farmer groups", key="gs_donut", height=380)

    tabs = st.tabs(["➕ Add scheme", "✏️ Update / remove", "🧾 Change log", "📝 KB overrides on schemes"])
    with tabs[0]:
        _add_form(user, reg, types, farmers, crops)
    with tabs[1]:
        _update_form(user, reg, view[view["status"] == "active"])
    with tabs[2]:
        change_log_panel(reg, "schemes", "scheme_changes.json")
    with tabs[3]:
        if ov:
            for o in ov:
                md(f'<div class="an-card tight"><div class="title">{esc(o.override_id)} · {esc(o.key.get("scheme_id", ""))} · <code>{esc(o.column)}</code>: '
                   f'<s>{esc(str(o.original)[:50])}</s> → <b>{esc(str(o.new)[:60])}</b></div><div class="sub">{esc(o.reason[:260])}{"…" if len(o.reason) > 260 else ""}'
                   f'{(" · <a href=" + chr(34) + esc(o.reference) + chr(34) + ">reference</a>") if o.reference else ""}</div></div>')
        else:
            st.caption("No overrides on the schemes table.")
    footer()
