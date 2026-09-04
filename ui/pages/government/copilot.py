"""🤖 AI Copilot (government) — questions over the modelled inclusion intelligence."""
from __future__ import annotations

from core.reasoning.analytics_advisor import gov_advice
from ui import state
from ui.analytics_copilot import render_chat
from ui.pages.government._common import guard, header

STARTERS = ["Which districts have low adoption?", "Which schemes have the widest reach?", "Which segments are excluded?", "Which crops are linked to which schemes?",
            "How is the inclusion index computed?", "Tell me about Adilabad", "Which districts perform best?", "How real are these numbers?"]


def render() -> None:
    user = guard()
    sc, tags, ii = header("🤖 AI Copilot — Inclusion Intelligence", user, with_segments=True)
    render_chat("gov", "Answers are composed from the modelled financial-inclusion intelligence for the selected scope.", STARTERS,
                lambda q: gov_advice(ii, q, state.get_kb()), "e.g. Why is Hyderabad flagged?")
