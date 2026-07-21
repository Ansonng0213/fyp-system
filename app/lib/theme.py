"""Design tokens + shared helpers — the single source of truth for DESIGN.md's
color system, base CSS, the inferno CDI ramp, and number formatting.

Never hardcode a hex or a number format in a page; import from here so every
page stays consistent. UI chrome is monochrome; the reserved *map* colors below
are used only for their meaning and nothing else (DESIGN.md §3).
"""
from __future__ import annotations

import streamlit as st

# --- UI chrome (monochrome) -------------------------------------------------
BG = "#0E1117"
SURFACE = "#1A1F2B"
SURFACE_2 = "#262B38"
BORDER = "#2A303C"
TEXT = "#E6E9EF"
TEXT_MUTED = "#9AA1AD"
TEXT_FAINT = "#6B7280"
ACCENT = "#3E7BFA"          # UI affordances only — deliberately outside the map palette

# --- Map data semantics (reserved; never reused) ----------------------------
MAP_CANVAS = "#1A1A2E"                 # matches cdi_map.png facecolor
PUBLIC_STATION = [0, 229, 255]         # #00E5FF cyan
PRIVATE_STATION = [122, 130, 142]      # #7A828E muted gray
RECOMMENDED = [0, 255, 136]            # #00FF88 green
DESERT_OUTLINE = [255, 59, 48]         # #FF3B30 red
DISTRICT_BORDER = [255, 255, 255]      # white, thin

# inferno anchors: (t in 0..1, r, g, b)
_INFERNO = [
    (0.0, 0, 0, 4),
    (0.2, 66, 10, 104),
    (0.4, 147, 38, 103),
    (0.6, 221, 81, 58),
    (0.8, 252, 165, 10),
    (1.0, 252, 255, 164),
]


def cdi_to_rgb(cdi: float, alpha: int = 180) -> list[int]:
    """CDI value (0-100) -> inferno [r, g, b, a]. Matches the pipeline cdi_map.
    CDI == 0 stays transparent by convention (caller should skip zero hexes)."""
    t = max(0.0, min(1.0, cdi / 100.0))
    for i in range(len(_INFERNO) - 1):
        t0, r0, g0, b0 = _INFERNO[i]
        t1, r1, g1, b1 = _INFERNO[i + 1]
        if t <= t1:
            f = 0.0 if t1 == t0 else (t - t0) / (t1 - t0)
            return [round(r0 + (r1 - r0) * f),
                    round(g0 + (g1 - g0) * f),
                    round(b0 + (b1 - b0) * f), alpha]
    return [252, 255, 164, alpha]


# --- number formatting (no orphan numbers; DESIGN.md §4) --------------------
def fmt_int(v: float) -> str:
    return f"{v:,.0f}"


def fmt_pct(v: float, d: int = 1) -> str:
    return f"{v:.{d}f}%"


def fmt_km(v: float, d: int = 1) -> str:
    return f"{v:.{d}f} km"


def fmt_mult(v: float, d: int = 1) -> str:
    return f"{v:.{d}f}×"          # e.g. 7.4×


# --- base CSS ---------------------------------------------------------------
# Colors are injected as CSS variables from the Python tokens above (single
# source of truth); the static body then references var(--...). Call once per page.
_ROOT_VARS = (
    ":root{"
    f"--bg:{BG};--surface:{SURFACE};--surface-2:{SURFACE_2};--border:{BORDER};"
    f"--text:{TEXT};--muted:{TEXT_MUTED};--faint:{TEXT_FAINT};--accent:{ACCENT};"
    "}"
)

_CSS_BODY = """
.block-container{padding-top:2.2rem;padding-bottom:3rem;max-width:1440px;}
.page-title{color:var(--text);font-size:1.7rem;font-weight:700;letter-spacing:-.01em;margin:0;}
.page-sub{color:var(--muted);font-size:.95rem;margin:.3rem 0 0;}
hr{border:none;border-top:1px solid var(--border);margin:1rem 0 1.4rem;}

/* KPI card: value + label + context (DESIGN.md §5) */
.kpi-card{background:var(--surface);border:1px solid var(--border);border-radius:12px;
  padding:18px 20px;min-height:140px;}
.kpi-label{color:var(--muted);font-size:.72rem;font-weight:600;letter-spacing:.08em;
  text-transform:uppercase;margin-bottom:10px;}
.kpi-value{color:var(--text);font-size:clamp(1.3rem,1.7vw,1.7rem);font-weight:700;line-height:1.15;}
.kpi-context{color:var(--muted);font-size:.82rem;margin-top:10px;line-height:1.45;}

/* navigation card */
.nav-card{background:var(--surface);border:1px solid var(--border);border-radius:12px;
  padding:15px 17px;min-height:118px;}
.nav-idx{color:var(--accent);font-size:.7rem;font-weight:700;letter-spacing:.09em;}
.nav-title{color:var(--text);font-size:1.0rem;font-weight:600;margin:3px 0 5px;}
.nav-desc{color:var(--muted);font-size:.83rem;line-height:1.45;}

/* section header + narrative */
.section-h{color:var(--text);font-size:1.15rem;font-weight:600;margin:6px 0 4px;}
.narrative{color:var(--text);font-size:1.02rem;line-height:1.75;max-width:1000px;}
.narrative b{color:var(--text);font-weight:600;}
"""


def inject_base_css() -> None:
    """Trim top padding (reclaim map height) and register card/typography styles.
    Call once at the top of every page, right after set_page_config."""
    st.markdown(f"<style>{_ROOT_VARS}{_CSS_BODY}</style>", unsafe_allow_html=True)
