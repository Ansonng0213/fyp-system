"""Reusable UI components (build once, reuse on every page — DESIGN.md §5).

Cards are rendered a ROW at a time inside one flex container (`.card-row`,
align-items:stretch), so every card in a row is equal height regardless of how
much text it holds. The equal-height rule lives here + in theme.py, never as a
per-page patch.
"""
from __future__ import annotations

import streamlit as st


def _kpi_card_html(label: str, value: str, context: str) -> str:
    return (f"<div class='kpi-card'>"
            f"<div class='kpi-label'>{label}</div>"
            f"<div class='kpi-value'>{value}</div>"
            f"<div class='kpi-context'>{context}</div>"
            f"</div>")


def kpi_row(cards: list[dict]) -> None:
    """One equal-height row of KPI cards. cards: list of {label, value, context}.
    No orphan numbers: each value carries a unit and each context a comparison."""
    html = "".join(_kpi_card_html(c["label"], c["value"], c["context"]) for c in cards)
    st.markdown(f"<div class='card-row'>{html}</div>", unsafe_allow_html=True)


def _nav_card_html(index: str, title: str, desc: str, href: str | None) -> str:
    inner = (f"<div class='nav-idx'>{index}</div>"
             f"<div class='nav-title'>{title}</div>"
             f"<div class='nav-desc'>{desc}</div>")
    if href:  # built page → whole card is a link
        return f"<a class='nav-card nav-link' href='{href}' target='_self'>{inner}</a>"
    return (f"<div class='nav-card nav-disabled'>{inner}"
            f"<div class='nav-badge'>Coming soon</div></div>")


def nav_row(cards: list[dict]) -> None:
    """One equal-height row of navigation cards. cards: list of
    {index, title, desc, href}. A card with href is fully clickable and lifts on
    hover; href None renders muted/disabled (page not built yet)."""
    html = "".join(_nav_card_html(c["index"], c["title"], c["desc"], c.get("href")) for c in cards)
    st.markdown(f"<div class='card-row'>{html}</div>", unsafe_allow_html=True)


def steps_row(steps: list[tuple]) -> None:
    """One equal-height row of numbered how-it-works steps. steps: list of
    (n, title, desc)."""
    html = "".join(
        f"<div class='step-card'><div class='step-n'>{n}</div>"
        f"<div class='step-t'>{t}</div><div class='step-d'>{d}</div></div>"
        for n, t, d in steps
    )
    st.markdown(f"<div class='card-row'>{html}</div>", unsafe_allow_html=True)


def section_header(text: str) -> None:
    st.markdown(f"<div class='section-h'>{text}</div>", unsafe_allow_html=True)
