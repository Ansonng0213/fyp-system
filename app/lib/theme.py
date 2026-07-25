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
ACCENT_RGB = [62, 123, 250]  # same, for pydeck get_*_color

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
    """CDI value (0-100) -> inferno [r, g, b, a]. CDI == 0 is transparent
    (undrawn); faint low values render faint, which is honest and preserves real
    intensity differences. Matches the pipeline inferno palette. Shared by all
    live maps (Pages 1/2/4)."""
    if cdi <= 0:
        return [0, 0, 0, 0]
    t = min(1.0, cdi / 100.0)
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

/* equal-height card rows (DESIGN.md §5): one flex container per row, cards
   stretch to the tallest, context/badge pinned to the bottom */
.card-row{display:flex;gap:16px;align-items:stretch;flex-wrap:wrap;margin:2px 0;}
.card-row > *{flex:1 1 0;min-width:190px;align-self:stretch;}

/* KPI card: value + label + context */
.kpi-card{background:var(--surface);border:1px solid var(--border);border-radius:12px;
  padding:18px 20px;min-height:140px;display:flex;flex-direction:column;
  box-sizing:border-box;}
.kpi-label{color:var(--muted);font-size:.72rem;font-weight:600;letter-spacing:.08em;
  text-transform:uppercase;margin-bottom:10px;}
.kpi-value{color:var(--text);font-size:clamp(1.3rem,1.7vw,1.7rem);font-weight:700;line-height:1.15;}
.kpi-context{color:var(--muted);font-size:.82rem;margin-top:auto;padding-top:10px;line-height:1.45;}

/* navigation card (whole card clickable when a page is built) */
.nav-card{background:var(--surface);border:1px solid var(--border);border-radius:12px;
  padding:15px 17px;min-height:118px;display:flex;flex-direction:column;
  box-sizing:border-box;text-decoration:none;}
a.nav-card.nav-link,a.nav-card.nav-link:hover,a.nav-card.nav-link:visited{
  text-decoration:none!important;color:inherit;}
a.nav-card.nav-link{cursor:pointer;
  transition:transform .12s ease, border-color .12s ease, background .12s ease;}
a.nav-card.nav-link:hover{border-color:var(--accent);background:var(--surface-2);
  transform:translateY(-2px);}
.nav-card.nav-disabled{opacity:.45;}
.nav-idx{color:var(--accent);font-size:.7rem;font-weight:700;letter-spacing:.09em;}
.nav-title{color:var(--text);font-size:1.0rem;font-weight:600;margin:3px 0 5px;}
.nav-desc{color:var(--muted);font-size:.83rem;line-height:1.45;}
.nav-badge{margin-top:auto;padding-top:8px;font-size:.66rem;font-weight:600;
  letter-spacing:.07em;text-transform:uppercase;color:var(--faint);}

/* solution callout band */
.solution-band{background:linear-gradient(90deg,rgba(62,123,250,.12),rgba(62,123,250,.02));
  border:1px solid var(--border);border-left:3px solid var(--accent);border-radius:12px;
  padding:20px 24px;margin:4px 0;}
.solution-lead{color:var(--accent);font-size:.78rem;font-weight:700;letter-spacing:.08em;
  text-transform:uppercase;margin-bottom:7px;}
.solution-body{color:var(--text);font-size:1.15rem;line-height:1.5;}
.solution-body b{font-weight:700;}

/* how-it-works step card */
.step-card{background:var(--surface);border:1px solid var(--border);border-radius:12px;
  padding:14px 16px;display:flex;flex-direction:column;box-sizing:border-box;}
.step-n{color:var(--accent);font-size:.82rem;font-weight:700;margin-bottom:6px;}
.step-t{color:var(--text);font-size:.92rem;font-weight:600;margin-bottom:3px;}
.step-d{color:var(--muted);font-size:.8rem;line-height:1.4;}

/* validation trust strip */
.trust-strip{background:var(--surface);border:1px solid var(--border);border-radius:10px;
  padding:12px 16px;color:var(--muted);font-size:.86rem;line-height:1.5;}
.trust-strip b{color:var(--text);font-weight:600;}
.trust-strip .tick{color:var(--accent);font-weight:700;}

/* footer */
.site-footer{color:var(--faint);font-size:.78rem;line-height:1.5;
  border-top:1px solid var(--border);padding-top:14px;margin-top:10px;}

/* section header + narrative */
.section-h{color:var(--text);font-size:1.15rem;font-weight:600;margin:6px 0 4px;}
.narrative{color:var(--text);font-size:1.02rem;line-height:1.75;max-width:1000px;}
.narrative b{color:var(--text);font-weight:600;}

/* ---- explorer: sidebar controls, legends, inspector ---- */
.ctl-title{color:var(--text);font-size:.9rem;font-weight:600;margin:0 0 6px;}

.leg-wrap{margin:10px 0 2px;}
.leg-label{color:var(--muted);font-size:.72rem;font-weight:600;letter-spacing:.05em;
  text-transform:uppercase;margin-bottom:4px;}
.leg-bar{height:10px;border-radius:5px;border:1px solid var(--border);
  background:linear-gradient(90deg,#000004,#420a68,#932667,#dd513a,#fca50a,#fcffa4);}
.leg-scale{display:flex;justify-content:space-between;color:var(--faint);
  font-size:.7rem;margin-top:2px;}

.lyr-legend{margin:6px 0 2px;}
.lyr-item{display:flex;align-items:center;gap:8px;color:var(--muted);font-size:.8rem;margin:3px 0;}
.dot{width:10px;height:10px;border-radius:50%;display:inline-block;flex:0 0 auto;}
.line-swatch{width:13px;border-top:2px solid #fff;display:inline-block;flex:0 0 auto;}

.insp-panel{background:var(--surface);border:1px solid var(--border);border-radius:12px;
  padding:16px 18px;}
.insp-h{color:var(--muted);font-size:.72rem;font-weight:600;letter-spacing:.08em;
  text-transform:uppercase;margin-bottom:8px;}
.insp-cdi{color:var(--text);font-size:1.9rem;font-weight:700;line-height:1;}
.insp-sub{color:var(--muted);font-size:.95rem;margin-top:3px;}
.insp-reason{color:var(--text);font-size:.86rem;line-height:1.5;margin:12px 0;
  padding:9px 11px;background:var(--surface-2);border-radius:8px;}
.insp-row{display:flex;justify-content:space-between;gap:10px;padding:5px 0;
  border-bottom:1px solid var(--border);font-size:.85rem;}
.insp-row span{color:var(--muted);}
.insp-row b{color:var(--text);font-weight:600;}
.insp-link{display:inline-block;margin-top:12px;color:var(--accent);
  font-size:.85rem;text-decoration:none;}
.insp-warn{color:var(--muted);font-size:.78rem;line-height:1.45;margin-top:12px;
  padding:8px 10px;background:var(--surface-2);border-radius:6px;}
"""


def inject_base_css() -> None:
    """Trim top padding (reclaim map height) and register card/typography styles.
    Call once at the top of every page, right after set_page_config."""
    st.markdown(f"<style>{_ROOT_VARS}{_CSS_BODY}</style>", unsafe_allow_html=True)
