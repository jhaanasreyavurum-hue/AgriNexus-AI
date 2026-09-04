"""Sign-in / farmer self-registration screen (shown when no user is in session)."""
from __future__ import annotations

import streamlit as st

from core.auth import Role, ROLE_LABELS, authenticate, list_users, register_farmer
from ui import auth
from ui.components import md, esc, badge, footer

ROLE_BLURB = {
    Role.FARMER: ("My farm, my finance", "Analyze your farm, see which loans, schemes, insurance and subsidies you may be eligible for, compare EMIs and download a bank-ready report."),
    Role.BANK_MANAGER: ("Agricultural Credit Intelligence", "Modelled loan demand by crop, district and farmer segment; high-potential areas; product management."),
    Role.GOVERNMENT_OFFICER: ("Financial Inclusion & Scheme Monitoring", "Scheme reach, district performance, inclusion indicators and low-adoption areas needing intervention."),
    Role.ADMINISTRATOR: ("Platform administration", "Users, banks, loan products, government schemes, knowledge-base health and system monitoring."),
}


def _demo_accounts() -> None:
    md('<div class="an-card tight"><div class="title">Demo accounts</div><div class="sub">All demo accounts use the password <code>agrinexus</code>. Accounts are a demo directory (no database).</div></div>')
    users = list_users()
    cols = st.columns(2)
    for i, u in enumerate(users):
        with cols[i % 2]:
            if st.button(f"{auth.ROLE_ICON[u.role]} {u.display_name}", key=f"demo_{u.username}", help=f"{u.role_label} · {u.organisation or '—'}"):
                auth.login(u)
                st.rerun()


def render() -> None:
    left, right = st.columns([1.25, 1], gap="large")
    with left:
        md('<div class="an-brand" style="margin-top:.4rem"><div class="logo" style="width:52px;height:52px;font-size:1.8rem">🌾</div>'
           '<div><div class="name" style="font-size:1.7rem">AgriNexus AI</div>'
           '<div class="tag">Agricultural Financial Intelligence Platform</div></div></div>')
        md('<p style="font-size:1.02rem;max-width:640px">One platform connecting farmer, farm, crop and financial data with a curated knowledge base of '
           'loan products, government schemes, insurance covers, subsidies and bank branches — producing <b>explainable</b> eligibility, '
           'matching, credit-demand and inclusion intelligence for four roles.</p>')
        for r in Role:
            title, blurb = ROLE_BLURB[r]
            md(f'<div class="an-card tight" style="display:flex;gap:.8rem;align-items:flex-start"><div style="font-size:1.5rem">{auth.ROLE_ICON[r]}</div>'
               f'<div><div class="title">{esc(ROLE_LABELS[r])} — {esc(title)}</div><div class="sub">{esc(blurb)}</div></div></div>')
        md(f'<div style="margin-top:.4rem">{badge("KNOWLEDGE BASE · 10 tables", "green")}{badge("RULE-BASED", "grey")}{badge("MODELLED analytics", "blue")}'
           f'{badge("WEATHER API optional", "blue")}{badge("DEMO accounts", "demo")}</div>')
        st.caption("Outputs are decision support, not sanctions or approvals. Modelled analytics are derived from the knowledge base — the platform never presents them as observed statistics.")

    with right:
        tab_in, tab_up = st.tabs(["Sign in", "Register as farmer"])
        with tab_in:
            with st.form("login_form", border=False):
                username = st.text_input("Username", autocomplete="username")
                password = st.text_input("Password", type="password", autocomplete="current-password")
                ok = st.form_submit_button("Sign in", type="primary")
            if ok:
                u = authenticate(username, password)
                if u is None:
                    st.error("Invalid username or password.")
                else:
                    auth.login(u)
                    st.rerun()
            st.divider()
            _demo_accounts()
        with tab_up:
            st.caption("Farmers can self-register. Bank, government and administrator accounts are provisioned by an administrator.")
            with st.form("register_form", border=False):
                name = st.text_input("Your name")
                uname = st.text_input("Choose a username", help="3–32 characters: lowercase letters, digits, '.', '_' or '-'")
                pw = st.text_input("Password (min 6 characters)", type="password")
                pw2 = st.text_input("Confirm password", type="password")
                ok2 = st.form_submit_button("Create account & continue", type="primary")
            if ok2:
                if pw != pw2:
                    st.error("Passwords do not match.")
                else:
                    try:
                        u = register_farmer(uname, name, pw)
                    except ValueError as exc:
                        st.error(str(exc))
                    else:
                        st.info("Account created for this server session (no database in this deployment — it will not survive a restart).")
                        auth.login(u)
                        st.rerun()
    footer()
