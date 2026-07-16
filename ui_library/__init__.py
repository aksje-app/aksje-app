"""Shared UI component library for AI Aksje Analyzer.

The package is intentionally thin: it standardizes presentation without owning
business logic or Streamlit session state.
"""

from .components import (
    action_row,
    compact_status_grid,
    empty_state,
    info_banner,
    kpi_row,
    page_header,
    section_header,
    status_badge,
)
from .tables import render_table
from .theme import UI_TOKENS, inject_design_system

__all__ = [
    "UI_TOKENS",
    "action_row",
    "compact_status_grid",
    "empty_state",
    "info_banner",
    "inject_design_system",
    "kpi_row",
    "page_header",
    "render_table",
    "section_header",
    "status_badge",
]
