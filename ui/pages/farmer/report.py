"""📄 My Report — bank-ready PDF + data exports."""
from __future__ import annotations

from ui.pages import reports
from ui.pages.farmer._common import guard_with_farm


def render() -> None:
    user, ctx, a = guard_with_farm("📄 My Report")
    reports.render_body(ctx, a)
