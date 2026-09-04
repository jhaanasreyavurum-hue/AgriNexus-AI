"""🤖 AI Farm Copilot — chat UI over ``generate_farm_advice`` (rule-based /
KB reasoning core; optional LLM narrator that only rephrases)."""
from __future__ import annotations

import streamlit as st

from core.reasoning import generate_farm_advice
from core.reasoning.narrator import narrate
from ui import state
from ui.components import badge, demo_banner, esc, explanation_block, footer, md, method_badge
from core.models.results import Method

STARTERS = ["What should I do today?", "Why is my farm health at this level?", "Should I irrigate today?",
            "What government schemes may apply to me?", "Which loan should I take?", "Which insurance covers my risks?",
            "What opportunities are available to me?", "What documents do I need?", "Which crop should I grow next season?",
            "What stage is my crop at?"]


def _answer(question: str):
    ctx = state.ensure_context()
    a = state.get_assessment()
    adv = generate_farm_advice(ctx, state.get_kb(), question, assessment=a)
    if st.session_state.get("use_narrator") and state.narrator_available():
        try:
            adv.narrated = narrate(adv, state.secrets())
        except Exception as exc:  # never let the narrator break the answer
            adv.narrated = None
            st.session_state["narrator_error"] = str(exc)
    return adv


def _render_turn(adv) -> None:
    labels = "".join(badge(m, {"Knowledge-base lookup": "green", "Rule-based": "grey", "Weather result": "blue", "Remote-sensing result": "blue",
                                "LLM-generated explanation": "purple"}.get(m, "grey")) for m in adv.method_labels)
    md(f'<div style="margin-bottom:.3rem">{badge("intent: " + adv.intent, "grey")}{labels}</div>')
    if adv.narrated:
        md(f'<div class="an-card" style="border-left:4px solid #6B3FA0">{method_badge(Method.LLM)}<div style="margin-top:.3rem">{esc(adv.narrated)}</div>'
           f'<div class="sub" style="margin-top:.3rem">Rephrased by the LLM narrator from the rule-based answer below; discarded automatically if it introduces numbers not in the source.</div></div>')
    st.markdown(adv.answer.replace("\n", "  \n"))
    with st.expander("Why? — factors, method & KB records"):
        explanation_block(adv.explanation, limit=10)
        if adv.kb_references:
            md("<b>KB records:</b> " + " ".join(f'<span class="an-chip">{esc(r)}</span>' for r in adv.kb_references))


def render() -> None:
    ctx = state.ensure_context()
    st.title("🤖 AI Farm Copilot")
    demo_banner(ctx)
    render_body(ctx)


def render_body(ctx) -> None:
    top = st.columns([2.2, 1])
    with top[0]:
        md('<div class="an-note">Answers come from the farm\'s own assessment and the knowledge base (rule-based / KB lookup, labelled). '
           'The Copilot never invents schemes, prices or measurements. An optional LLM narrator can rephrase — it is only available when an '
           '<code>LLM_API_KEY</code> secret is configured, and it never changes the recommendation.</div>')
    with top[1]:
        avail = state.narrator_available()
        st.toggle("LLM narrator (rephrase only)", value=False, key="use_narrator", disabled=not avail,
                  help="Configure LLM_PROVIDER / LLM_API_KEY / LLM_MODEL in Streamlit secrets to enable." if not avail else "Rephrases the rule-based answer in plain language.")
        st.caption(("Narrator ready." if avail else "Narrator off — no LLM secret set.") + (f" Last error: {st.session_state['narrator_error'][:80]}" if st.session_state.get("narrator_error") else ""))

    hist = st.session_state.setdefault("copilot_history", [])
    st.markdown("**Ask about your farm**")
    cols = st.columns(5)
    for i, q in enumerate(STARTERS):
        if cols[i % 5].button(q, key=f"starter{i}"):
            st.session_state["pending_q"] = q

    for turn in hist:
        with st.chat_message("user"):
            st.write(turn["q"])
        with st.chat_message("assistant", avatar="🌾"):
            _render_turn(turn["adv"])

    q = st.chat_input("e.g. Which subsidy helps with my water problem?")
    q = q or st.session_state.pop("pending_q", None)
    if q:
        q = q.strip()
        if not q:
            st.warning("Please type a question.")
        else:
            with st.chat_message("user"):
                st.write(q)
            with st.chat_message("assistant", avatar="🌾"):
                with st.spinner("Reasoning over farm data and knowledge base…"):
                    adv = _answer(q)
                _render_turn(adv)
                if adv.follow_ups:
                    st.caption("Try next: " + " · ".join(adv.follow_ups))
            hist.append({"q": q, "adv": adv})
            st.session_state["copilot_history"] = hist[-12:]
    if hist and st.button("Clear conversation"):
        st.session_state["copilot_history"] = []
        st.rerun()
    footer()
