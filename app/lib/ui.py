"""Reusable UI components (build once, reuse on every page — DESIGN.md §5).

Cards are rendered a ROW at a time inside one flex container (`.card-row`,
align-items:stretch), so every card in a row is equal height regardless of how
much text it holds. The equal-height rule lives here + in theme.py, never as a
per-page patch.
"""
from __future__ import annotations

import streamlit as st

from lib import theme


# --- number formatting -------------------------------------------------------
# ONE helper for every integer column in every st.dataframe on the site. Before
# this, columns were declared ad hoc with format="%d", which renders 129556
# where the scorecard beside it said 129,556 (review item A4). "localized" is
# Streamlit's thousand-separator format and matches theme.fmt_int, which is what
# the KPI cards and the HTML tables use.
INT_FORMAT = "localized"


def int_col(label: str, **kw):
    """Integer dataframe column with thousand separators. Use for EVERY
    whole-number column so tables and the cards beside them agree."""
    return st.column_config.NumberColumn(label, format=INT_FORMAT, **kw)


def num_col(label: str, decimals: int = 1, **kw):
    """Fixed-decimal dataframe column. Counterpart to int_col for real numbers."""
    return st.column_config.NumberColumn(label, format=f"%.{decimals}f", **kw)


_INFERNO_CSS = "#000004,#420a68,#932667,#dd513a,#fca50a,#fcffa4"


def _no_demand_key(n: int | None) -> str:
    """Legend row for the off-ramp slate hexes. Returns '' when the caller did
    not pass a count, so pages that do not draw them are unchanged.

    The swatch is drawn at a higher alpha than the map layer (0.45 against
    0.16): on the map the fill sits over a dark basemap across thousands of
    contiguous hexes, where 0.16 is already a visible field, but a single 11 px
    chip on the card surface at that alpha is invisible. The outline colour is
    the map's exactly, which is what actually identifies the shape.
    """
    if n is None:
        return ""
    r, g, b, _ = theme.NO_DEMAND_FILL
    lr, lg, lb, _ = theme.NO_DEMAND_LINE
    return (
        "<div class='lyr-item' style='margin-top:8px'>"
        f"<span class='dot' style='border-radius:2px;background:rgba({r},{g},{b},.45);"
        f"border:1px solid rgba({lr},{lg},{lb},.85)'></span>"
        f"No measurable demand — {n:,} hexes, no population and no activity "
        "recorded (see Validation &amp; Data)</div>"
    )


def cdi_legend(max_cdi: float | None = None, width_px: int = 400,
               no_demand: int | None = None) -> None:
    """The CDI colour bar. 0-100 is a FIXED inferno ramp so a value keeps its
    colour at every lens and weight setting; when the view exceeds 100 an
    over-range segment is appended in proportion and the true range is stated.
    Pass max_cdi = the largest value currently on screen.

    no_demand: count of hexes drawn OFF the ramp in neutral slate because
    pop_est and activity_score are both 0. Pass it whenever the frame draws
    them, so the grey field has a key -- without one it reads as a third,
    unexplained colour rather than as "no measurement here"."""
    over = max_cdi is not None and max_cdi > 100.0
    if not over:
        st.markdown(
            f"<div class='leg-wrap' style='max-width:{width_px}px'>"
            "<div class='leg-label'>Charging Desert Index</div>"
            "<div class='leg-bar'></div>"
            "<div class='leg-scale'><span>0</span><span>50</span><span>100</span></div>"
            f"{_no_demand_key(no_demand)}</div>",
            unsafe_allow_html=True)
        return
    main_pct = 100.0 / max_cdi * 100.0          # share of the bar that is 0-100
    st.markdown(
        f"<div class='leg-wrap' style='max-width:{width_px}px'>"
        "<div class='leg-label'>Charging Desert Index</div>"
        "<div style='display:flex;height:10px;border:1px solid var(--border);"
        "border-radius:5px;overflow:hidden'>"
        f"<div style='flex:0 0 {main_pct:.2f}%;background:linear-gradient(90deg,{_INFERNO_CSS})'></div>"
        f"<div style='flex:1 1 auto;background:linear-gradient(90deg,#fcffa4,#ffffff)'></div>"
        "</div>"
        "<div class='leg-scale'><span>0</span>"
        f"<span style='margin-left:auto'>100 · baseline peak</span>"
        f"<span style='margin-left:8px'>{max_cdi:.1f}</span></div>"
        f"<div class='leg-scale'><span>0 – {max_cdi:.1f} at this setting. "
        "0–100 is fixed, so a value keeps its colour everywhere; the pale "
        "segment is above the baseline peak.</span></div>"
        f"{_no_demand_key(no_demand)}</div>",
        unsafe_allow_html=True)


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


def _esc(v) -> str:
    return (str(v).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


def html_table(df, num_cols: list[str] | None = None,
               link_cols: list[str] | None = None, link_text: str = "open ↗") -> str:
    """Static styled HTML table string with clearly-visible row dividers.

    st.dataframe renders on a canvas whose grid lines can't be themed via CSS, so
    display (non-interactive) tables use this for uniform, legible separators.
    `num_cols` are right-aligned (tabular); `link_cols` render their cell value as
    an external link. Values are HTML-escaped."""
    num_cols, link_cols = set(num_cols or []), set(link_cols or [])
    heads = "".join(f"<th>{_esc(c)}</th>" for c in df.columns)
    rows = []
    for _, r in df.iterrows():
        cells = []
        for c in df.columns:
            if c in link_cols:
                cells.append(f"<td><a href='{_esc(r[c])}' target='_blank'>{link_text}</a></td>")
            else:
                cls = " class='num'" if c in num_cols else ""
                cells.append(f"<td{cls}>{_esc(r[c])}</td>")
        rows.append("<tr>" + "".join(cells) + "</tr>")
    return (f"<div class='data-table-wrap'><table class='data-table'>"
            f"<thead><tr>{heads}</tr></thead><tbody>{''.join(rows)}</tbody></table></div>")


def panel(header: str, body_html: str, foot_html: str = "") -> str:
    """One equal-height panel: header, body, and an optional footer pinned to the
    bottom. Place two+ in a `.card-row` so their bottoms align (DESIGN.md §5)."""
    foot = f"<div class='panel-foot'>{foot_html}</div>" if foot_html else ""
    return (f"<div class='panel'><div class='panel-h'>{header}</div>"
            f"<div class='panel-body'>{body_html}</div>{foot}</div>")
