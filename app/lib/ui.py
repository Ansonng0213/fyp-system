"""Reusable UI components (build once, reuse on every page — DESIGN.md §5).
These emit the card/typography markup styled by theme._CSS_BODY. Deltas/context
lines are typographic (muted text), never the reserved map greens/reds.
"""
from __future__ import annotations

import streamlit as st


def kpi_card(container, label: str, value: str, context: str) -> None:
    """KPI card = value + label + context line. No orphan numbers: caller must
    pass a value with unit and a context (comparison/delta)."""
    container.markdown(
        f"<div class='kpi-card'>"
        f"<div class='kpi-label'>{label}</div>"
        f"<div class='kpi-value'>{value}</div>"
        f"<div class='kpi-context'>{context}</div>"
        f"</div>",
        unsafe_allow_html=True,
    )


def nav_card(container, index: str, title: str, desc: str) -> None:
    """A page-navigation card: small index tag, title, one-line description."""
    container.markdown(
        f"<div class='nav-card'>"
        f"<div class='nav-idx'>{index}</div>"
        f"<div class='nav-title'>{title}</div>"
        f"<div class='nav-desc'>{desc}</div>"
        f"</div>",
        unsafe_allow_html=True,
    )


def section_header(text: str) -> None:
    st.markdown(f"<div class='section-h'>{text}</div>", unsafe_allow_html=True)
