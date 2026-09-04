"""🤖 AI Copilot (farmer) — chat over the farm's own assessment + KB."""
from __future__ import annotations

from ui.pages import copilot
from ui.pages.farmer._common import guard_with_farm


def render() -> None:
    user, ctx, a = guard_with_farm("🤖 AI Copilot")
    copilot.render_body(ctx)
