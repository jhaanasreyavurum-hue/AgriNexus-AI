"""💼 Loan Products — view / add / update KB loan products (authorised roles; session-only storage)."""
from __future__ import annotations

import pandas as pd
import streamlit as st

from core.auth import Permission, PermissionDenied, Role
from core.store.registry import LOAN_EDITABLE
from ui import auth, state
from ui.analytics_components import kpi_row, ranking_table
from ui.components import badge, esc, footer, inr, md, table

LOAN_TYPES_FALLBACK = ["Kisan Credit Card (KCC)", "Crop Loan (Seasonal Agricultural Operations)", "Farm Mechanization / Tractor Loan", "Micro Irrigation / Drip & Sprinkler Loan",
                       "Dairy & Livestock Development Loan", "Warehouse Receipt / Post-Harvest Loan", "Horticulture & Plantation Loan", "Farmer Producer Organisation (FPO) Term Loan"]


def _storage_notice(reg) -> None:
    if reg.persistent:
        md(f'<div class="an-note">Storage: {esc(reg.storage_label)}.</div>')
    else:
        md(f'<div class="an-warn">⚠️ <b>No persistent database in this deployment.</b> Additions and updates are held {esc(reg.storage_label)}. '
           'They are applied on top of the read-only knowledge base for everyone using this server until it restarts, and are exported in the change log below. '
           'Wire a database backend (core/store/registry.py → RegistryBackend) to make changes permanent.</div>')


def _add_form(user, reg, banks, types) -> None:
    with st.form("add_loan", border=True):
        st.markdown("**Add a loan product**")
        c1, c2, c3 = st.columns(3)
        with c1:
            name = st.text_input("Product name *")
            bank = st.selectbox("Bank *", banks, index=banks.index(next((b for b in banks if user.bank_name and user.bank_name.split()[0] in b), banks[0])))
            ltype = st.selectbox("Loan type *", types)
            crop = st.text_input("Crop-specific (crop name or 'No')", value="No")
        with c2:
            mi = st.number_input("Min interest % *", 0.0, 40.0, 7.0, 0.1)
            ma = st.number_input("Max interest % *", 0.0, 40.0, 9.0, 0.1)
            amin = st.number_input("Min amount ₹ *", 0, 100_000_000, 10_000, 5_000)
            amax = st.number_input("Max amount ₹ *", 0, 100_000_000, 300_000, 10_000)
        with c3:
            years = st.number_input("Repayment (years) *", 1, 30, 1)
            fee = st.text_input("Processing fee", value="0.5%")
            coll = st.selectbox("Collateral required", ["No", "Yes"])
            govt = st.selectbox("Government linked", ["Yes", "No"])
            days = st.number_input("Approval days", 1, 365, 15)
        docs = st.text_input("Required documents (semicolon-separated)", value="Aadhaar Card; Land Ownership / Pattadar Passbook; Bank Statement (6 months); Passport Size Photograph")
        summary = st.text_area("Eligibility summary", value="", height=70)
        ok = st.form_submit_button("Add product", type="primary")
    if ok:
        fields = {"loan_name": name.strip(), "bank_name": bank, "loan_type": ltype, "interest_rate": f"{mi:.2f}% - {ma:.2f}%", "minimum_interest": float(mi), "maximum_interest": float(ma),
                  "loan_amount_min": int(amin), "loan_amount_max": int(amax), "repayment_years": int(years), "processing_fee": fee, "collateral_required": coll, "crop_specific": crop.strip() or "No",
                  "government_linked": govt, "approval_days": int(days), "required_documents": docs, "eligibility_summary": summary.strip(), "loan_score": 7.0}
        try:
            rec = reg.add(user, "loans", fields)
        except (PermissionDenied, ValueError) as exc:
            st.error(str(exc))
        else:
            st.session_state["lp_flash"] = f"Added {rec.key} — {fields['loan_name']} (session-only, not persisted). It is now included in farmer loan matching on this server; the pre-built bank/government analytics matrix is unaffected until rebuilt."
            state._assess_cached.clear()
            st.rerun()


def _update_form(user, reg, view: pd.DataFrame) -> None:
    ids = list(view["loan_id"].astype(str))
    labels = dict(zip(ids, (view["loan_id"].astype(str) + " · " + view["loan_name"].astype(str) + " · " + view["bank_name"].astype(str))))
    pick = st.selectbox("Product to update", ids, format_func=labels.get, key="upd_pick")
    row = view[view["loan_id"].astype(str) == pick].iloc[0]
    with st.form("upd_loan", border=True):
        c1, c2, c3 = st.columns(3)
        with c1:
            mi = st.number_input("Min interest %", 0.0, 40.0, float(row["minimum_interest"] or 0), 0.1)
            ma = st.number_input("Max interest %", 0.0, 40.0, float(row["maximum_interest"] or 0), 0.1)
        with c2:
            amin = st.number_input("Min amount ₹", 0, 100_000_000, int(row["loan_amount_min"] or 0), 5_000)
            amax = st.number_input("Max amount ₹", 0, 100_000_000, int(row["loan_amount_max"] or 0), 10_000)
        with c3:
            years = st.number_input("Repayment (years)", 1, 30, int(row["repayment_years"] or 1))
            days = st.number_input("Approval days", 1, 365, int(row["approval_days"] or 15))
        summary = st.text_area("Eligibility summary", value=str(row["eligibility_summary"] or ""), height=70)
        b1, b2 = st.columns([1, 1])
        ok = b1.form_submit_button("Save update", type="primary")
        deact = b2.form_submit_button("Deactivate product")
    if ok:
        fields = {"minimum_interest": float(mi), "maximum_interest": float(ma), "interest_rate": f"{mi:.2f}% - {ma:.2f}%", "loan_amount_min": int(amin), "loan_amount_max": int(amax),
                  "repayment_years": int(years), "approval_days": int(days), "eligibility_summary": summary.strip()}
        try:
            reg.update(user, "loans", pick, fields)
        except (PermissionDenied, ValueError, KeyError) as exc:
            st.error(str(exc))
        else:
            st.session_state["lp_flash"] = f"Updated {pick} (session-only, not persisted)."
            state._assess_cached.clear()
            st.rerun()
    if deact:
        try:
            reg.deactivate(user, "loans", pick)
        except PermissionDenied as exc:
            st.error(str(exc))
        else:
            st.session_state["lp_flash"] = f"Deactivated {pick} (session-only)."
            state._assess_cached.clear()
            st.rerun()


def render() -> None:
    user = auth.require(Role.BANK_MANAGER, Role.ADMINISTRATOR, perm=Permission.LOAN_PRODUCTS_VIEW)
    st.title("💼 Loan Products")
    kb = state.get_kb()
    reg = state.get_registry()
    can_manage = user.can(Permission.LOAN_PRODUCTS_MANAGE)
    _storage_notice(reg)
    if st.session_state.get("lp_flash"):
        st.success(st.session_state.pop("lp_flash"))
    view = reg.view("loans")
    active = view[view["status"] == "active"]
    banks = sorted(view["bank_name"].dropna().astype(str).unique())
    types = sorted(view["loan_type"].dropna().astype(str).unique()) or LOAN_TYPES_FALLBACK

    kpi_row([("Active products", str(len(active)), f"{int((view['status'] == 'inactive').sum())} deactivated this session"),
             ("Banks", str(len(banks)), ""), ("Loan types", str(len(types)), ""),
             ("Session changes", str(len(reg.change_log('loans'))), "not persisted" if not reg.persistent else "persisted"),
             ("Your access", "manage" if can_manage else "view only", user.role_label)], badge("KNOWLEDGE BASE + session overlay", "green"))

    c1, c2, c3 = st.columns(3)
    fb = c1.multiselect("Bank", banks, key="lp_bank", placeholder="All banks")
    ft = c2.multiselect("Loan type", types, key="lp_type", placeholder="All types")
    fs = c3.selectbox("Status", ["active", "all", "inactive"], key="lp_status")
    v = view.copy()
    if fb:
        v = v[v["bank_name"].isin(fb)]
    if ft:
        v = v[v["loan_type"].isin(ft)]
    if fs != "all":
        v = v[v["status"] == fs]
    st.caption(f"{len(v)} product(s). Products added or updated in this session are marked in 'Origin'.")
    ranking_table(v.sort_values(["bank_name", "loan_type"]), {"loan_id": ("ID", "str"), "loan_name": ("Product", "str"), "bank_name": ("Bank", "str"), "loan_type": ("Type", "str"),
                                                            "interest_rate": ("Interest", "str"), "loan_amount_min": ("Min ₹", "inr"), "loan_amount_max": ("Max ₹", "inr"), "repayment_years": ("Years", "int"),
                                                            "collateral_required": ("Collateral", "str"), "crop_specific": ("Crop-specific", "str"), "government_linked": ("Govt-linked", "str"),
                                                            "approval_days": ("Approval d", "int"), "status": ("Status", "str"), "origin": ("Origin", "str")}, height=420)

    if can_manage:
        tabs = st.tabs(["➕ Add product", "✏️ Update / deactivate", "🧾 Change log"])
        with tabs[0]:
            _add_form(user, reg, banks, types)
        with tabs[1]:
            _update_form(user, reg, view)
        with tabs[2]:
            log = reg.change_log("loans")
            if log:
                table(pd.DataFrame([{"#": r.change_id, "op": r.op, "key": r.key, "fields": ", ".join(f"{k}={v}" for k, v in r.fields.items())[:120], "by": r.by, "role": r.role, "at": r.at, "persisted": r.persisted} for r in log]))
                st.download_button("Export change log (JSON)", pd.DataFrame([r.to_dict() for r in log]).to_json(orient="records", indent=2), "loan_product_changes.json", "application/json")
            else:
                st.caption("No changes this session.")
    else:
        md('<div class="an-note">Your role can view products but not modify them. Modification rights (loan_products:manage) are held by Bank Managers and Administrators and are enforced in the data layer, not just hidden here.</div>')
    footer()
