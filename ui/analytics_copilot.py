"""Shared chat UI for the bank / government analytics Copilot (rule-based core + optional narrator)."""
from __future__ import annotations

from typing import Callable, List

import streamlit as st

from core.models.results import Method
from core.reasoning.narrator import narrate
from ui import state
from ui.analytics_components import basis_badge
from ui.components import badge, esc, explanation_block, footer, md, method_badge

_BADGE = {"Knowledge-base lookup": "green", "Rule-based": "grey", "Modelled (KB-derived)": "amber", "LLM-generated explanation": "purple"}


def _render_turn(adv) -> None:
    labels = "".join(badge(m, _BADGE.get(m, "grey")) for m in adv.method_labels)
    md(f'<div style="margin-bottom:.3rem">{badge("intent: " + adv.intent, "grey")}{labels}</div>')
    if adv.narrated:
        md(f'<div class="an-card" style="border-left:4px solid #6B3FA0">{method_badge(Method.LLM)}<div style="margin-top:.3rem">{esc(adv.narrated)}</div>'
           f'<div class="sub" style="margin-top:.3rem">Rephrased by the LLM narrator from the rule-based answer below; discarded automatically if it introduces numbers not in the source.</div></div>')
    st.markdown(adv.answer.replace("\n", "  \n"))
    with st.expander("Why? — factors, method & basis"):
        explanation_block(adv.explanation, limit=10)


def render_chat(role_key: str, intro: str, starters: List[str], answer_fn: Callable[[str], object], placeholder: str) -> None:
    top = st.columns([2.2, 1])
    with top[0]:
        md(f'<div class="an-note">{basis_badge()} {intro} The Copilot only reads the intelligence tables shown on the dashboards — it never invents figures, schemes or products. '
           'An optional LLM narrator can rephrase (requires an <code>LLM_API_KEY</code> secret) and never changes the numbers.</div>')
    with top[1]:
        avail = state.narrator_available()
        st.toggle("LLM narrator (rephrase only)", value=False, key=f"{role_key}_use_narrator", disabled=not avail,
                  help="Configure LLM_PROVIDER / LLM_API_KEY / LLM_MODEL in Streamlit secrets to enable." if not avail else "Rephrases the rule-based answer in plain language.")
        st.caption("Narrator ready." if avail else "Narrator off — no LLM secret set.")

    hkey = f"{role_key}_copilot_history"
    hist = st.session_state.setdefault(hkey, [])
    st.markdown("**Ask about the analytics**")
    cols = st.columns(4)
    for i, q in enumerate(starters):
        if cols[i % 4].button(q, key=f"{role_key}_starter{i}"):
            st.session_state[f"{role_key}_pending_q"] = q

    for turn in hist:
        with st.chat_message("user"):
            st.write(turn["q"])
        with st.chat_message("assistant", avatar="📊"):
            _render_turn(turn["adv"])

    q = st.chat_input(placeholder)
    q = q or st.session_state.pop(f"{role_key}_pending_q", None)
    if q:
        q = q.strip()
        if not q:
            st.warning("Please type a question.")
        else:
            with st.chat_message("user"):
                st.write(q)
            with st.chat_message("assistant", avatar="📊"):
                with st.spinner("Reading the intelligence tables…"):
                    adv = answer_fn(q)
                    if st.session_state.get(f"{role_key}_use_narrator") and state.narrator_available():
                        try:
                            adv.narrated = narrate(adv, state.secrets())
                        except Exception:
                            adv.narrated = None
                _render_turn(adv)
                if adv.follow_ups:
                    st.caption("Try next: " + " · ".join(adv.follow_ups))
            hist.append({"q": q, "adv": adv})
            st.session_state[hkey] = hist[-12:]
    if hist and st.button("Clear conversation", key=f"{role_key}_clear"):
        st.session_state[hkey] = []
        st.rerun()
    footer()
