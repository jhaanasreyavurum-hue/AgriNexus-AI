"""🤖 AI Copilot (bank) — questions over the modelled credit intelligence."""
from __future__ import annotations

from core.reasoning.analytics_advisor import bank_advice
from ui import state
from ui.analytics_copilot import render_chat
from ui.pages.bank._common import guard, header

STARTERS = ["Where is loan demand highest?", "Which product has the widest eligibility?", "Which segments are under-served?", "Which crops drive demand?",
            "Which banks have branches where demand is highest?", "What documents block conversion?", "Tell me about Warangal", "How real are these numbers?"]


def render() -> None:
    user = guard()
    sc, tags, crop, ci = header("🤖 AI Copilot — Credit Intelligence", user, with_segments=True)
    render_chat("bank", "Answers are composed from the modelled credit intelligence for the selected scope.", STARTERS,
                lambda q: bank_advice(ci, q, state.get_kb()), "e.g. Which districts have high potential but no branch presence?")
