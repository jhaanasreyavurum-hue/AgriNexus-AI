"""💳 Loan Schemes — administrator view of the loan-product catalogue (reuses the bank product manager)."""
from __future__ import annotations

import streamlit as st

from core.auth import Permission
from ui import state
from ui.analytics_components import bar_chart, donut
from ui.components import footer, md
from ui.pages.admin._common import guard
from ui.pages.bank import products


def render() -> None:
    user = guard(Permission.LOAN_PRODUCTS_MANAGE)
    reg = state.get_registry()
    view = reg.view("loans")
    active = view[view["status"] == "active"]
    # catalogue overview first, then the shared manager (add / update / deactivate / change log)
    st.title("💳 Loan Schemes — catalogue overview")
    md('<div class="an-note">Administrator view of every loan product across banks. Adds and updates go through the same authorised registry as the Bank Manager module; '
       'session changes are visible to farmer matching immediately and are labelled as not persisted.</div>')
    c1, c2 = st.columns(2)
    with c1:
        bar_chart(active.groupby("loan_type").size().rename("n").reset_index().sort_values("n"), "loan_type", "n", "Products by loan type", key="ls_type", height=380, text_fmt="%{text}")
    with c2:
        donut(active.groupby("bank_name").size().rename("n").reset_index(), "bank_name", "n", "Products by bank", key="ls_bank", height=380)
    st.divider()
    products.render()
