"""Optional LLM narrator — rephrases rule-based results in plain language.

Guard-rails
-----------
* Enabled only when ``LLM_API_KEY`` (+ ``LLM_PROVIDER``) is present in the
  secrets mapping the UI passes in (``st.secrets``) or the environment.
* The prompt contains the *already computed* answer, factors and method
  labels. The system prompt forbids new recommendations, numbers or scheme
  names. If the model output introduces a number that is not in the source
  text, the narration is discarded and the rule-based text is shown.
* Output is always labelled "LLM-generated explanation" by the UI.
"""
from __future__ import annotations

import json
import os
import re
from typing import Any, Mapping, Optional

import requests

from core.reasoning.advisor import Advice

SYSTEM = (
    "You are the explanation layer of AgriNexus AI, an agricultural decision-support tool. "
    "You will receive a farmer's question, the system's rule-based answer, the evidence factors, "
    "and the analysis methods. Rewrite the answer as a short, clear, friendly explanation (max 150 words) "
    "for a farmer. RULES: do not add any recommendation, number, scheme, product, crop or fact that is not "
    "in the provided material; do not soften or reverse the recommendation; keep the action sentence first; "
    "mention that the data is demo data if the material says so."
)


def _get(secrets: Optional[Mapping[str, Any]], key: str) -> Optional[str]:
    try:
        if secrets is not None and key in secrets and secrets[key]:
            return str(secrets[key])
    except Exception:
        pass
    return os.environ.get(key) or None


def narrator_enabled(secrets: Optional[Mapping[str, Any]] = None) -> bool:
    return bool(_get(secrets, "LLM_API_KEY"))


def _numbers(text: str) -> set:
    return set(re.findall(r"\d+(?:\.\d+)?", text))


def narrate(advice: Advice, secrets: Optional[Mapping[str, Any]] = None, timeout: int = 20) -> Optional[str]:
    key = _get(secrets, "LLM_API_KEY")
    if not key:
        return None
    provider = (_get(secrets, "LLM_PROVIDER") or "openai").lower()
    model = _get(secrets, "LLM_MODEL")
    ex = advice.explanation
    material = {
        "question": advice.question, "rule_based_answer": advice.answer, "summary": ex.summary,
        "positive": [f.detail for f in ex.positive], "limiting": [f.detail for f in ex.limiting],
        "risks": [f.detail for f in ex.risks], "missing": [f.detail for f in ex.missing],
        "methods": advice.method_labels, "demo_data": ex.demo_data_used,
    }
    user = "MATERIAL:\n" + json.dumps(material, ensure_ascii=False, indent=1)
    try:
        if provider == "anthropic":
            r = requests.post("https://api.anthropic.com/v1/messages",
                              headers={"x-api-key": key, "anthropic-version": "2023-06-01", "content-type": "application/json"},
                              json={"model": model or "claude-3-5-haiku-latest", "max_tokens": 400, "system": SYSTEM,
                                    "messages": [{"role": "user", "content": user}]}, timeout=timeout)
            r.raise_for_status()
            text = r.json()["content"][0]["text"]
        elif provider == "gemini":
            m = model or "gemini-1.5-flash"
            r = requests.post(f"https://generativelanguage.googleapis.com/v1beta/models/{m}:generateContent?key={key}",
                              json={"systemInstruction": {"parts": [{"text": SYSTEM}]},
                                    "contents": [{"parts": [{"text": user}]}]}, timeout=timeout)
            r.raise_for_status()
            text = r.json()["candidates"][0]["content"]["parts"][0]["text"]
        else:  # openai-compatible
            base = _get(secrets, "LLM_BASE_URL") or "https://api.openai.com/v1"
            r = requests.post(f"{base}/chat/completions", headers={"Authorization": f"Bearer {key}"},
                              json={"model": model or "gpt-4o-mini", "temperature": 0.2, "max_tokens": 400,
                                    "messages": [{"role": "system", "content": SYSTEM}, {"role": "user", "content": user}]},
                              timeout=timeout)
            r.raise_for_status()
            text = r.json()["choices"][0]["message"]["content"]
    except Exception:
        return None
    text = text.strip()
    # guard: no new numbers may appear
    allowed = _numbers(user)
    if _numbers(text) - allowed:
        return None
    return text
