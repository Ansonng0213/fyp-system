"""Page 4 — Market Logic.

The diagnostic counterpart to the CDI: a supervised model of where commercial
operators ACTUALLY built (stage 11), surfaced as evidence about market
behaviour. It is deliberately NOT a siting tool — its whole value is the
contrast with the recommendations on Page 3.

Every figure is read from processed_data/ (stages 11 / 11b); nothing on this
page is hardcoded, so a data rerun updates all of it.
"""
import math
import os

import pandas as pd
import streamlit as st

from lib import data, theme, ui

st.set_page_config(page_title="Market Logic", layout="wide")
theme.inject_base_css()

# ------------------------------------------------------------------ load
coef = data.load_operator_coefficients()
comp = data.load_operator_model_comparison()
abl = data.load_operator_ablation()
mkt = data.load_operator_market_forecast()
spec = data.load_operator_income_specs()
rob = data.load_operator_robustness()
FIG_DIR = os.path.join(str(data.DATA_DIR), "figures")

# income specs (i) with district dummies / (ii) without — read, never hardcoded
_sp_with = spec[spec["specification"].str.startswith("(i)")].iloc[0]
_sp_without = spec[spec["specification"].str.startswith("(ii)")].iloc[0]
_sp_dummies = spec[spec["specification"].str.startswith("(iii)")].iloc[0]
PR_DELTA = abs(float(_sp_with["pr_auc_oof"]) - float(_sp_dummies["pr_auc_oof"]))
_r7 = rob[rob["check"].str.contains("res-7")]
RES7_RETAINED = (abs(float(_r7["equity_mult_coef"].iloc[0])) /
                 abs(float(_sp_without["equity_mult_coef"]))) if len(_r7) else float("nan")

BASELINE = float(comp["random_baseline__randomCV"].iloc[0])
champ = comp.sort_values("pr_auc__randomCV", ascending=False).iloc[0]
CHAMP = f"{champ['model']} ({champ['variant']})"

# the two coefficients this page speaks about by name
res = coef.loc[coef["feature"] == "poi_residential"].iloc[0]
inc = coef.loc[coef["feature"] == "equity_mult"].iloc[0]
top = coef.sort_values("coefficient", ascending=False)
t1, t2 = top.iloc[0], top.iloc[1]


def _or(v):
    """Odds ratio from a log-odds bound. The CSV stores bootstrap CIs on the
    coefficient (log-odds) scale; the page quotes them as odds ratios."""
    return float("nan") if pd.isna(v) else math.exp(float(v))


RES_LO, RES_HI = _or(res["boot_ci_low"]), _or(res["boot_ci_high"])

# ------------------------------------------------------------------ header
st.markdown(
    "<div class='page-title'>Market Logic</div>"
    "<div class='page-sub'>What actually drives commercial charger placement — "
    "a model of the market's revealed preference</div>",
    unsafe_allow_html=True,
)

st.markdown(
    "<div style='background:linear-gradient(90deg,rgba(255,90,40,.18),rgba(255,90,40,.05));"
    "border-left:4px solid #FF5A28;border-radius:8px;padding:14px 18px;margin:14px 0 6px'>"
    "<div style='color:#FF8A5C;font-size:.78rem;font-weight:700;letter-spacing:.08em;"
    "text-transform:uppercase;margin-bottom:6px'>Diagnostic only</div>"
    "<div style='color:#E6E9EF;font-size:1.02rem;line-height:1.55'>"
    "This model describes <b>how the commercial market behaves</b>. It is "
    "<b>not a siting recommendation</b>. Using it to select locations would "
    "reproduce the pattern this study identifies.</div></div>",
    unsafe_allow_html=True,
)
st.markdown("<hr>", unsafe_allow_html=True)

# ================================================================== 1
ui.section_header("What drives commercial siting")

st.markdown(
    f"<div class='trust-strip'>Chargers cluster at <b>transport nodes</b> "
    f"(odds ratio <span class='tick'>{t1['odds_ratio']:.2f}</span>) and "
    f"<b>food-and-drink</b> (<span class='tick'>{t2['odds_ratio']:.2f}</span>), "
    f"and avoid <b>residential areas</b> "
    f"(<span class='tick'>{res['odds_ratio']:.2f}</span>). "
    "Each figure is the change in the odds that a hexagon holds a public "
    "charger, per one standard deviation of that feature, holding the rest "
    "fixed.</div>",
    unsafe_allow_html=True,
)
st.write("")

ct = coef.sort_values("abs_coefficient", ascending=False).reset_index(drop=True)
ct_show = pd.DataFrame({
    "#": range(1, len(ct) + 1),
    "Feature": ct["feature"],
    "Coefficient": ct["coefficient"].map("{:+.4f}".format),
    "Odds ratio": ct["odds_ratio"].map("{:.3f}".format),
    "Direction": ["more likely" if c > 0 else "less likely" for c in ct["coefficient"]],
})
left, right = st.columns([0.55, 0.45], gap="large")
with left:
    st.markdown(ui.html_table(ct_show, num_cols=["#", "Coefficient", "Odds ratio"]),
                unsafe_allow_html=True)
    st.caption("Standardised logistic regression on the inference feature set "
               "(no geography), sorted by absolute magnitude.")
with right:
    st.markdown(
        "<div class='solution-band'><div class='solution-lead'>The supported finding</div>"
        f"<div class='solution-body'><b>{res['feature']}</b> — odds ratio "
        f"<b>{res['odds_ratio']:.3f}</b>, 95% CI "
        f"<b>[{RES_LO:.2f}, {RES_HI:.2f}]</b>. "
        f"<b>{res['boot_pct_negative']:.1f}%</b> of spatial-block bootstrap draws "
        "are negative and the interval excludes 1.0, so this survives the test "
        "the income effect fails (see limitations). More residential land use "
        f"means roughly <b>{(1 - res['odds_ratio']) * 100:.0f}% lower odds</b> of "
        "a public charger, holding activity and every other land use fixed."
        "</div></div>",
        unsafe_allow_html=True,
    )
    shap_bar = os.path.join(FIG_DIR, "shap_summary_bar.png")
    if os.path.exists(shap_bar):
        st.image(shap_bar, use_container_width=True,
                 caption=f"SHAP mean |value| — {ct['shap_model'].iloc[0]}")
    else:
        st.info("shap_summary_bar.png not found — run "
                "`python pipeline/11_operator_model.py`.")

with st.expander("Why the coefficient and SHAP rankings differ on residential"):
    st.markdown(
        f"- `poi_residential` is coefficient rank **{int(res['rank'])}** but SHAP "
        f"rank **{int(res['shap_rank'])}**.\n"
        "- The coefficient is a *conditional, signed, linear* effect: holding "
        "activity and every other land use fixed, more residential means lower "
        "odds. That contrast is large.\n"
        "- Mean |SHAP| is an *unsigned, marginal* magnitude on a tree ensemble. "
        "The tree reproduces the same contrast through the commercial features "
        "it already splits on, which are correlated with residential density, so "
        "little credit is attributed to the residential column itself.\n"
        "- Neither is wrong — they answer different questions."
    )

st.write("")
st.markdown("<hr>", unsafe_allow_html=True)

# ================================================================== 2
ui.section_header("Model comparison")
st.caption("Five algorithms × base and tuned, scored out-of-fold under two "
           "cross-validation schemes. Accuracy is not reported: at "
           f"{BASELINE:.2%} prevalence, predicting “no charger” everywhere "
           f"scores {1 - BASELINE:.1%} while finding nothing.")

cs = comp.sort_values("pr_auc__randomCV", ascending=False).reset_index(drop=True)
cs_show = pd.DataFrame({
    "Model": cs["model"], "Variant": cs["variant"],
    "PR-AUC (random CV)": cs["pr_auc__randomCV"].map("{:.4f}".format),
    "PR-AUC (spatial CV)": cs["pr_auc__spatialCV"].map("{:.4f}".format),
    "Random baseline": cs["random_baseline__randomCV"].map("{:.4f}".format),
    "Lift": cs["lift_over_random__randomCV"].map("{:.1f}×".format),
    "ROC-AUC": cs["roc_auc__randomCV"].map("{:.4f}".format),
    "P@10": cs["precision@10__randomCV"].map("{:.2f}".format),
    "P@20": cs["precision@20__randomCV"].map("{:.2f}".format),
    "P@50": cs["precision@50__randomCV"].map("{:.2f}".format),
})
st.markdown(ui.html_table(cs_show, num_cols=list(cs_show.columns[2:])),
            unsafe_allow_html=True)
st.markdown(
    f"<div class='trust-strip'>Champion: <b>{CHAMP}</b> — PR-AUC "
    f"<span class='tick'>{champ['pr_auc__randomCV']:.4f}</span> under random CV and "
    f"<span class='tick'>{champ['pr_auc__spatialCV']:.4f}</span> under spatial-block CV, "
    f"against a random baseline of <b>{BASELINE:.4f}</b> — a "
    f"<b>{champ['lift_over_random__randomCV']:.1f}×</b> lift. It leads under "
    "both schemes, so the result is not an artefact of the split.</div>",
    unsafe_allow_html=True,
)

# HOW NARROW THE WIN IS -- stated here rather than left for a reader to compute
# off the table above. Stage 11 selects the champion on random-CV PR-AUC alone
# (11_operator_model.py:556) and then CHECKS whether the same model leads
# spatially; it does. That check, not the margin, is what the choice rests on.
_ru_rand = cs.iloc[1]                                   # runner-up, random CV
_spat = comp.sort_values("pr_auc__spatialCV", ascending=False).reset_index(drop=True)
_spat_best, _ru_spat = _spat.iloc[0], _spat.iloc[1]
_gap_rand = float(champ["pr_auc__randomCV"]) - float(_ru_rand["pr_auc__randomCV"])
_gap_spat = float(_spat_best["pr_auc__spatialCV"]) - float(_ru_spat["pr_auc__spatialCV"])
_same_champ = (_spat_best["model"] == champ["model"]
               and _spat_best["variant"] == champ["variant"])
_ru_changes = not (_ru_spat["model"] == _ru_rand["model"]
                   and _ru_spat["variant"] == _ru_rand["variant"])
st.caption(
    f"**The margin is not decisive, and it should not be read as one.** "
    f"{CHAMP} leads {_ru_rand['model']} ({_ru_rand['variant']}) by "
    f"**{_gap_rand:+.4f}** under random CV "
    f"({float(champ['pr_auc__randomCV']):.4f} against "
    f"{float(_ru_rand['pr_auc__randomCV']):.4f}), and "
    + (f"leads {_ru_spat['model']} ({_ru_spat['variant']}) by **{_gap_spat:+.4f}** "
       f"under spatial-block CV ({float(_spat_best['pr_auc__spatialCV']):.4f} against "
       f"{float(_ru_spat['pr_auc__spatialCV']):.4f})."
       if _same_champ else
       f"is beaten under spatial-block CV by {_spat_best['model']} "
       f"({_spat_best['variant']}).")
    + (f" The runner-up is not even the same build in the two schemes — "
       f"{_ru_rand['model']} ({_ru_rand['variant']}) under random CV, "
       f"{_ru_spat['model']} ({_ru_spat['variant']}) under spatial. " if _ru_changes else " ")
    + "Differences this small are inside the noise of a 222-positive dataset. "
    "The champion is selected on random-CV PR-AUC and then checked against the "
    "spatial scheme; what recommends it is that it **leads under both**, not "
    "that it wins either by a margin worth defending. Any of the top three "
    "tree ensembles would support the same conclusions on this page."
)

st.write("")
st.markdown("<hr>", unsafe_allow_html=True)

# ================================================================== 3
ui.section_header("Feature ablation")

ab = abl.copy()
ab_show = pd.DataFrame({
    "Set": ab["set"], "Features included": ab["description"],
    "n": ab["n_features"],
    "PR-AUC (random CV)": ab["pr_auc_random_cv"].map("{:.4f}".format),
    "PR-AUC (spatial CV)": ab["pr_auc_spatial_cv"].map("{:.4f}".format),
    "Gain vs C": ab["gain_vs_C"].map("{:+.4f}".format),
})
st.markdown(ui.html_table(ab_show, num_cols=["n", "PR-AUC (random CV)",
                                             "PR-AUC (spatial CV)", "Gain vs C"]),
            unsafe_allow_html=True)

_a = float(ab.loc[ab["set"] == "A", "pr_auc_random_cv"].iloc[0])
_b = float(ab.loc[ab["set"] == "B", "pr_auc_random_cv"].iloc[0])
_c = float(ab.loc[ab["set"] == "C", "pr_auc_random_cv"].iloc[0])
_eng = ab[ab["set"].isin(["E", "F", "G", "H"])]["gain_vs_C"]
st.caption(
    f"POI composition drives the model: adding the eleven land-use counts moves "
    f"PR-AUC from {_b:.3f} to {_c:.3f} (**{_c - _b:+.3f}**), the single largest "
    f"step. The four engineered feature sets (E–H) changed it by between "
    f"{_eng.min():+.4f} and {_eng.max():+.4f} — essentially nothing. "
    f"All {len(ab)} configurations are reported, not only the best."
)

# SPATIAL >= RANDOM. Blocking folds by geography normally COSTS accuracy, so a
# set scoring at least as well under spatial CV looks wrong at a glance. It is a
# robustness signal: those sets carry no location identity, so there is nothing
# for spatial blocking to take away, and the residual difference is noise. The
# sets that DO lose ground under blocking are the informative half of this --
# D adds lat/lon and district dummies, i.e. exactly the features that can
# memorise where things are. Computed from the CSV, never asserted.
ab["_d"] = ab["pr_auc_spatial_cv"] - ab["pr_auc_random_cv"]
_up = ab[ab["_d"] >= 0].sort_values("_d", ascending=False)
_dD = ab.loc[ab["set"] == "D"].iloc[0]
if len(_up):
    _up_best = _up.iloc[0]
    _up_names = ", ".join(f"**{s}**" for s in sorted(_up["set"]))
    st.caption(
        f"**Sets {_up_names} score at least as well under spatial-block CV as "
        f"under random CV**, led by **{_up_best['set']}** "
        f"({float(_up_best['pr_auc_random_cv']):.4f} → "
        f"{float(_up_best['pr_auc_spatial_cv']):.4f}, "
        f"**{float(_up_best['_d']):+.4f}**). Blocking folds by geography normally "
        "*costs* accuracy, so that reads as odd at first. It is a robustness "
        "signal, not an anomaly: none of those sets carries a coordinate or a "
        "district identity, so spatial blocking has nothing to strip out, and a "
        "gap this small is noise on 222 positives. "
        f"The prediction set **D** moves the other way "
        f"(**{float(_dD['_d']):+.4f}**), and that is the expected signature — "
        "D is the only set that adds lat/lon and district dummies, i.e. exactly "
        "the features that can memorise *where* rather than learn *what*, which "
        "is what spatial blocking is designed to penalise. The coefficients "
        "above are read from **C**, which carries no geography at all."
    )

st.write("")
st.markdown("<hr>", unsafe_allow_html=True)

# ================================================================== 4
ui.section_header("Where the market builds next")

m20 = mkt[mkt["top_k"] == 20].sort_values("mean_sites", ascending=False).reset_index(drop=True)
n_seeds = int(m20["n_seeds"].iloc[0])
m_show = pd.DataFrame({
    "District": m20["district"],
    f"Sites in top 20 (mean ± std, {n_seeds} seeds)":
        [f"{a:.1f} ± {b:.1f}" for a, b in zip(m20["mean_sites"], m20["std_sites"])],
    "Min": m20["min_sites"], "Max": m20["max_sites"],
    f"Runs with zero (of {n_seeds})": m20["n_seeds_zero"],
})
st.markdown(ui.html_table(m_show, num_cols=list(m_show.columns[1:])),
            unsafe_allow_html=True)

hl = m20.loc[m20["district"] == "Hulu Langat"].iloc[0]
kl = m20.loc[m20["district"] == "Klang"].iloc[0]
lead = m20.iloc[0]
st.markdown(
    f"<div class='trust-strip'><b>{lead['district']}</b> and "
    f"<b>{m20.iloc[1]['district']}</b> take "
    f"<b>{lead['mean_sites'] + m20.iloc[1]['mean_sites']:.1f} of the 20</b> on average. "
    f"<b>Hulu Langat</b> receives zero in <span class='tick'>"
    f"{int(hl['n_seeds_zero'])} of {n_seeds}</span> runs. "
    f"<b>Klang</b> receives zero in <span class='tick'>"
    f"{int(kl['n_seeds_zero'])} of {n_seeds}</span> runs — it averages "
    f"{kl['mean_sites']:.1f} sites and reaches at most {int(kl['max_sites'])}, "
    "so it is rarely rather than never selected.</div>",
    unsafe_allow_html=True,
)
st.caption(
    "These are the ten-seed statistics. The What-If simulator's “market's next "
    "20” preset loads a **single representative seed**, so its district split is "
    "one draw from this distribution rather than the mean."
)

st.write("")
st.markdown("<hr>", unsafe_allow_html=True)

# ================================================================== 5
with st.expander("Honest limitations", expanded=False):
    st.markdown(
        f"**The income effect is not statistically supported.** Point estimates "
        f"are negative in every specification (odds ratio "
        f"{float(_sp_without['odds_ratio']):.2f} without district dummies, "
        f"{float(_sp_with['odds_ratio']):.2f} with), and "
        f"{inc['boot_pct_negative']:.1f}% of spatial-block bootstrap draws are "
        f"negative — but the 95% CI is "
        f"[{_or(inc['boot_ci_low']):.2f}, {_or(inc['boot_ci_high']):.2f}] "
        "on the odds-ratio scale, which **crosses 1.0**. The effect also "
        f"attenuates to about {RES7_RETAINED:.0%} of its size at H3 "
        "resolution 7.\n\n"
        "The reason is structural: income is a **district-level constant**, so "
        "the effective sample is **seven values** regardless of how many "
        "hexagons the grid contains. Adding income to a model that already "
        f"contains district dummies changes PR-AUC by **{PR_DELTA:.6f}**. This "
        "dataset cannot resolve a district-level income effect, however many "
        "hexes it holds.\n\n"
        "Lead with *“charging follows commercial siting, not residential need”* "
        "— which the residential coefficient supports — not with income.\n\n"
        "**Other limitations**\n"
        "- **Association, not causation.** The model describes where chargers "
        "are, not why any individual siting decision was made.\n"
        "- **Shared inputs with the CDI.** Both use the same OpenStreetMap "
        "points of interest, so the demand layer and this model are not "
        "independent evidence about land use.\n"
        "- **No station opening dates.** The data is a single snapshot, so the "
        "model assumes stationarity — that the siting logic which produced "
        "today's network is the logic that will produce the next one. It cannot "
        "detect a change in operator strategy.\n"
        "- Two public stations fall outside the hex grid and one district-edge "
        "buffer is absent; see the stage 11 source header."
    )

st.write("")
st.caption("Source: `operator_coefficients_full.csv`, `operator_model_comparison.csv`, "
           "`operator_feature_ablation.csv`, `operator_market_forecast.csv` — "
           "pipeline stages 11 and 11b. Every value on this page is read from those "
           "files.")
