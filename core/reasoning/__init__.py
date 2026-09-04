"""Reasoning layer — builds the full FarmAssessment and answers questions.

    assessment = assess_farm(ctx, kb)          # analytics + health + risks + NBA
    advice     = generate_farm_advice(ctx, kb, "Should I irrigate today?")

No Streamlit. Optional LLM narration lives in ``narrator.py`` and only
rephrases results produced here.
"""
from core.reasoning.assessment import FarmAssessment, assess_farm, run_full_assessment
from core.reasoning.next_best_action import generate_next_best_actions
from core.reasoning.advisor import generate_farm_advice, Advice

__all__ = ["FarmAssessment", "assess_farm", "run_full_assessment", "generate_next_best_actions", "generate_farm_advice", "Advice"]
