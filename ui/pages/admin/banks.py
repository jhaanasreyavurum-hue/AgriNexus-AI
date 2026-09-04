"""🏦 Banks — bank registry (KB branch directory + loan products), add / update via registry overlay."""
from __future__ import annotations

import pandas as pd
import streamlit as st

from core.auth import Permission, PermissionDenied
from ui import state
from ui.analytics_components import bar_chart, district_map, download_df, kpi_row, ranking_table
from ui.components import badge, esc, footer, md
from ui.pages.admin._common import change_log_panel, flash, guard, rerun_after, storage_notice


def render() -> None:
    user = guard(Permission.REGISTRY_MANAGE)
    st.title("🏦 Banks")
    kb = state.get_kb()
    reg = state.get_registry()
    storage_notice(reg)
    flash("bank_flash")
    view = reg.view("banks")
    active = view[view["status"] == "active"]
    br = kb.branches
    kpi_row([("Banks", str(len(active)), f"{int((view['status'] == 'inactive').sum())} deactivated this session"),
             ("KB branches", str(len(br)), f"{br['district'].nunique()} districts · {br['state'].nunique()} state(s)"),
             ("Agri-loan desks", str(int(br["loan_available_bool"].sum())), f"{int(br['insurance_available_bool'].sum())} insurance desks"),
             ("Banks with products, no branch", str(int(((active['branches'] == 0) & (active['loan_products'] > 0)).sum())), "product listed, no KB branch"),
             ("Session changes", str(len(reg.change_log("banks"))), "not persisted" if not reg.persistent else "persisted")], badge("KNOWLEDGE BASE + session overlay", "green"))
    md('<div class="an-note">The bank table is derived from the KB branch directory (Telangana, 200 branches) joined with the loan-product catalogue. Adding a bank here registers it for product '
       'management; branch records themselves are KB reference data and are not edited.</div>')

    c1, c2 = st.columns([1.3, 1])
    with c1:
        ranking_table(active.sort_values("branches", ascending=False),
                      {"bank_name": ("Bank", "str"), "branches": ("KB branches", "int"), "districts": ("Districts", "int"), "loan_desks": ("Loan desks", "int"), "insurance_desks": ("Insurance desks", "int"),
                       "government_linked": ("Govt-linked %", "pct"), "loan_products": ("Loan products", "int"), "origin": ("Origin", "str")}, height=420)
        download_df(active, "Download bank registry (CSV)", "banks.csv", "dl_banks")
    with c2:
        bar_chart(active[active["branches"] > 0].sort_values("branches"), "bank_name", "branches", "KB branches per bank", key="bank_bar", height=420, text_fmt="%{text}")

    st.subheader("Branch footprint")
    pick = st.selectbox("Bank", ["All banks"] + sorted(active["bank_name"].astype(str)), key="bank_pick")
    b = br if pick == "All banks" else br[br["bank_name"] == pick]
    if len(b):
        g = b.groupby(["state", "district"], as_index=False).agg(branches=("branch_name", "count"), loan_desks=("loan_available_bool", "sum"))
        g["level"] = pd.cut(g["branches"], [0, 1, 3, 1000], labels=["Low", "Medium", "High"]).astype(str)
        district_map(kb, g, "branches", "district", "level", title=f"{pick} — branches by district", tooltip_cols=["loan_desks"], height=400)
    else:
        st.caption("No KB branches recorded for this bank.")

    tabs = st.tabs(["➕ Add bank", "✏️ Deactivate", "🧾 Change log"])
    with tabs[0]:
        with st.form("add_bank", border=True):
            name = st.text_input("Bank name *")
            gl = st.selectbox("Government linked", ["Yes", "No"])
            ok = st.form_submit_button("Add bank", type="primary")
        if ok:
            try:
                rec = reg.add(user, "banks", {"bank_name": name.strip(), "branches": 0, "districts": 0, "loan_desks": 0, "insurance_desks": 0, "government_linked": 100.0 if gl == "Yes" else 0.0, "loan_products": 0})
            except (PermissionDenied, ValueError) as exc:
                st.error(str(exc))
            else:
                rerun_after("bank_flash", f"Added bank '{rec.key}' (session-only, not persisted). It can now be selected when adding loan products.")
    with tabs[1]:
        names = sorted(active["bank_name"].astype(str))
        d = st.selectbox("Bank to deactivate", names, key="bank_deact")
        if st.button("Deactivate bank", key="bank_deact_btn"):
            try:
                reg.deactivate(user, "banks", d)
            except PermissionDenied as exc:
                st.error(str(exc))
            else:
                rerun_after("bank_flash", f"Deactivated '{d}' in the registry (session-only). KB branch records are unchanged.")
    with tabs[2]:
        change_log_panel(reg, "banks", "bank_changes.json")
    footer()
