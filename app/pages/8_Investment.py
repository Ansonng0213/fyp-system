"""Page 6 — Investment Scenario Calculator (Operator / commercial lens).

The commercial complement to the equity analysis. THIS IS AN INDICATIVE SCENARIO
TOOL, NOT A REVENUE PREDICTION: it computes the consequences of assumptions the
USER supplies. Real charging-utilization data is not publicly available (the
data-availability paradox at the heart of this project), so no honest tool can
forecast a site's earnings — this one compares scenarios and stress-tests a
candidate. Reads recommended_sites_v1.csv (+ hex_cdi_v1.csv via the loader) for
optional site context; changes nothing in processed_data/.
"""
import numpy as np
import plotly.graph_objects as go
import streamlit as st

from lib import data, theme, ui

st.set_page_config(page_title="Investment Scenario", layout="wide")
theme.inject_base_css()

DAYS = 30.0  # days per month


def fmt_payback(months: float | None) -> str:
    if months is None or not np.isfinite(months):
        return "Never"
    if months < 24:
        return f"{months:.0f} months"
    return f"{months / 12:.1f} years"


rec = data.load_recommended_sites().sort_values("rank").reset_index(drop=True)

# ------------------------------------------------------------------ sidebar
with st.sidebar:
    st.markdown("<div class='ctl-title'>Site context (optional)</div>", unsafe_allow_html=True)
    site_opts = ["Custom location (no site)"] + [
        f"#{int(r.rank)} · {r.district} · CDI {r.cdi:.0f}" for r in rec.itertuples()]
    pick = st.selectbox("Anchor the scenario to a candidate site", site_opts,
                        help="Pick one of the 20 recommended sites to see its catchment as context, "
                             "or keep Custom for a generic scenario.")
    site = None if pick.startswith("Custom") else rec.iloc[site_opts.index(pick) - 1]
    st.caption("Context only — it informs your assumptions, it does not change the maths below.")
    st.divider()

    st.markdown("<div class='ctl-title'>Your assumptions</div>", unsafe_allow_html=True)
    ports = st.slider("Charging ports at the site", 1, 20, 4)
    sessions = st.slider("Sessions per port per day", 0.5, 16.0, 4.0, 0.5,
                         help="How many charging sessions each port serves per day. Real-world "
                              "utilization is the single biggest driver of returns — and it is not "
                              "knowable from public data.")
    kwh = st.slider("kWh delivered per session", 5, 80, 20)

    st.markdown("<div class='ctl-sub'>Tariff & energy cost</div>", unsafe_allow_html=True)
    tariff = st.number_input("Charging tariff (RM/kWh)", 0.10, 5.00, 1.30, 0.05)
    elec = st.number_input("Electricity cost (RM/kWh)", 0.05, 5.00, 0.60, 0.05)

    st.markdown("<div class='ctl-sub'>Capital & operating cost</div>", unsafe_allow_html=True)
    capex_port = st.number_input("CapEx per port (RM)", 0, 1_000_000, 70_000, 5_000)
    opex = st.number_input("Fixed monthly opex (RM)", 0, 200_000, 3_000, 500)

# ------------------------------------------------------------------ maths (pure arithmetic on the inputs)
margin = tariff - elec                                   # RM per kWh
monthly_energy = ports * sessions * kwh * DAYS           # kWh / month
monthly_gross = monthly_energy * margin                  # RM / month (before opex)
monthly_net = monthly_gross - opex                       # RM / month (after opex)
total_capex = ports * capex_port
payback_months = total_capex / monthly_net if monthly_net > 0 else None
be_sessions_port = (opex / (margin * kwh * DAYS * ports)) if margin > 0 else None

# ------------------------------------------------------------------ header + critical framing banner
st.markdown(
    "<div class='page-title'>Investment Scenario Calculator</div>"
    "<div class='page-sub'>Operator lens · stress-test the commercial case for a candidate site</div>",
    unsafe_allow_html=True,
)
st.markdown("<hr>", unsafe_allow_html=True)

st.markdown(
    "<div class='indic-band'><div class='indic-lead'>Indicative scenario — not a revenue prediction</div>"
    "<div class='indic-body'>This tool computes the <b>consequences of the assumptions you set</b> in the "
    "sidebar — it does <b>not</b> predict revenue. Real charging <b>utilization data is not publicly "
    "available</b> (the data-availability paradox at the heart of this project), so no honest tool can "
    "forecast a site's earnings. Use it to <b>compare scenarios</b> and see how sensitive returns are to "
    "utilization — <b>never</b> as a guarantee of returns.</div></div>",
    unsafe_allow_html=True,
)
st.write("")

if site is not None:
    st.markdown(
        f"<div class='trust-strip'>Anchored to <b>Site #{int(site['rank'])} · {site['district']}</b> — "
        f"host-hex CDI <b>{site['cdi']:.0f}</b>, would bring <b>{theme.fmt_int(site['pop_newly_covered'])} "
        f"people</b> within 2 km of charging, nearest existing station "
        f"<b>{site['nearest_existing_km']:.1f} km</b> away. "
        "<i>Context for your assumptions — it does not change the calculation.</i></div>",
        unsafe_allow_html=True,
    )
    st.write("")

# ------------------------------------------------------------------ indicative outputs
ui.section_header("Indicative outcome — based on your assumptions")
ui.kpi_row([
    {"label": "Monthly energy delivered", "value": f"{theme.fmt_int(monthly_energy)} kWh",
     "context": f"indicative · {ports} ports × {sessions:g} sessions/day × {kwh} kWh × 30 days"},
    {"label": "Monthly gross margin", "value": f"RM {theme.fmt_int(monthly_gross)}",
     "context": f"indicative · margin RM {margin:.2f}/kWh (tariff − energy cost)"},
    {"label": "Monthly net (after opex)", "value": f"RM {theme.fmt_int(monthly_net)}",
     "context": f"indicative · less RM {theme.fmt_int(opex)} fixed opex"},
    {"label": "Simple payback", "value": fmt_payback(payback_months),
     "context": f"indicative · RM {theme.fmt_int(total_capex)} CapEx ÷ monthly net"},
])
st.write("")

# breakeven readout
if be_sessions_port is None:
    be_html = ("At these prices the <b>margin is zero or negative</b> (tariff ≤ energy cost), so the site "
               "cannot break even at any utilization — raise the tariff or lower the energy cost.")
elif monthly_net <= 0:
    be_html = (f"At <b>{sessions:g} sessions/port/day</b> the site is <b>cash-negative</b>. Each port needs "
               f"about <span class='tick'>{be_sessions_port:.1f} sessions/day</span> just to cover the "
               f"RM {theme.fmt_int(opex)} monthly opex (before recovering any CapEx).")
else:
    be_html = (f"Break-even utilization: each port needs about "
               f"<span class='tick'>{be_sessions_port:.1f} sessions/day</span> to cover the "
               f"RM {theme.fmt_int(opex)} monthly opex. You are running at "
               f"<b>{sessions:g}</b> — above that line, so the site is cash-positive before CapEx.")
st.markdown(f"<div class='trust-strip'>{be_html}</div>", unsafe_allow_html=True)

st.write("")
st.markdown("<hr>", unsafe_allow_html=True)

# ------------------------------------------------------------------ utilization sensitivity
ui.section_header("How sensitive is payback to utilization?")

low_s, base_s, high_s = round(sessions * 0.5, 1), float(sessions), round(sessions * 1.75, 1)


def payback_years_at(s: float) -> float:
    net = ports * s * kwh * DAYS * margin - opex
    return total_capex / net / 12 if net > 0 else np.nan


if margin <= 0:
    st.markdown("<div class='trust-strip'>Margin is zero or negative at these prices — payback is "
                "undefined. Adjust the tariff / energy cost to explore sensitivity.</div>",
                unsafe_allow_html=True)
else:
    xs = list(np.linspace(0.5, 16, 80))
    ys = [payback_years_at(s) for s in xs]
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=xs, y=ys, mode="lines", line=dict(color=theme.ACCENT, width=2.5),
        hovertemplate="%{x:.1f} sessions/port/day → payback %{y:.1f} years<extra></extra>"))
    for label, s, color in [("Low", low_s, theme.TEXT_FAINT), ("Base (yours)", base_s, "#00FF88"),
                            ("High", high_s, "#E8833A")]:
        py = payback_years_at(s)
        if np.isfinite(py):
            fig.add_trace(go.Scatter(
                x=[s], y=[py], mode="markers+text", text=[label], textposition="top center",
                marker=dict(color=color, size=11, line=dict(color="#0E1117", width=2)),
                textfont=dict(color=theme.TEXT, size=11), showlegend=False,
                hovertemplate=f"{label}: %{{x:.1f}}/day → %{{y:.1f}} yr<extra></extra>"))
    fig.update_layout(
        height=340, margin=dict(l=6, r=16, t=16, b=6), showlegend=False,
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        font=dict(color=theme.TEXT_MUTED, size=12),
        xaxis=dict(title="Sessions per port per day", showgrid=False, zeroline=False),
        yaxis=dict(title="Simple payback (years)", showgrid=True, gridcolor="rgba(255,255,255,0.06)",
                   zeroline=False, range=[0, 12]),
    )
    st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})

    def _yr(s):
        v = payback_years_at(s)
        return f"{v:.1f} yr" if np.isfinite(v) else "never"
    st.caption(f"Payback swings hard with utilization: **Low {low_s:g}/day → {_yr(low_s)}** · "
               f"**Base {base_s:g}/day → {_yr(base_s)}** · **High {high_s:g}/day → {_yr(high_s)}**. "
               "This is the real-world utilization cliff — a site that looks viable at 35 % utilization can "
               "be badly under water at 15 %. The exact numbers are only as good as your assumptions.")

st.write("")
st.markdown("<hr>", unsafe_allow_html=True)

# ------------------------------------------------------------------ honest caveats
ui.section_header("Read this before trusting any number above")
st.markdown(
    "<div class='trust-strip'>"
    "<b>These are planning assumptions, not forecasts.</b> Every figure above is arithmetic on the sliders "
    "you set — change a slider and the &quot;answer&quot; changes.<br><br>"
    "<b>Actual revenue depends on real utilization, which is unknowable from public data.</b> Charge-point "
    "operators treat session data as a proprietary moat; there is no open dataset of who charges where and "
    "how often. That is precisely why this project forecasts <i>adoption</i> and maps <i>need</i> rather "
    "than predicting revenue.<br><br>"
    "<b>Use this to compare scenarios, not to guarantee returns.</b> It is most useful for relative "
    "questions — &quot;how many more sessions/day would make this pay back in 3 years?&quot; — and for "
    "stress-testing a candidate against optimistic vs pessimistic utilization.</div>",
    unsafe_allow_html=True,
)

st.write("")

st.markdown(
    "<div class='trust-strip'>How this fits the project: the <b>Charging Desert Index</b> finds "
    "<b>where</b> people are underserved — the equity case; this calculator lets an operator sanity-check "
    "the <b>commercial case</b> for a candidate site. Two lenses, one system: place chargers where they "
    "serve the most underserved people <i>and</i> can be made to stack up.</div>",
    unsafe_allow_html=True,
)

st.markdown(
    "<div class='site-footer'>Ng Cheng Xin · TP071136 · Asia Pacific University · FYP 2026 · "
    "Investment Scenario Calculator — indicative, user-assumption-driven; not a revenue forecast.</div>",
    unsafe_allow_html=True,
)
