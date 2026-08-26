"""Live CDI recomputation from stored components — the one piece of arithmetic
the app is allowed to do (CLAUDE.md §2). Pure pandas over hex_cdi_v1 columns; no
pipeline calls. Shared by the CDI Explorer (Page 1) and the What-If simulator.
"""
from __future__ import annotations

import pandas as pd


def demand_pressure(df: pd.DataFrame, w_pop: float = 0.5, equity_on: bool = True) -> pd.Series:
    """The demand side only: (w_pop*pop_n + w_act*act_n) * equity. Supply-independent,
    so the What-If page can apply it to both the stored gap (before) and a new gap
    (after) and normalize both against the same peak — an honest before/after."""
    w_act = 1.0 - w_pop
    equity = df["equity_mult"] if equity_on else 1.0
    return (w_pop * df["pop_n"] + w_act * df["act_n"]) * equity


def cdi_scale() -> float:
    """The single frozen denominator every CDI computation divides by.

    Read from processed_data/cdi_scale.json (written by stage 06) through the
    cached loader in data.py, which is the only module allowed to touch the
    filesystem (CLAUDE.md #1).
    """
    from . import data                       # local import avoids a cycle
    return data.load_cdi_scale()


def recompute_cdi(df: pd.DataFrame, w_pop: float = 0.5, equity_on: bool = True,
                  denom: float | None = None) -> pd.Series:
    """Re-mix CDI (0-100) from the stored components, exactly like
    pipeline/06_build_cdi.py:

        demand = (w_pop*pop_n + w_act*act_n) * equity
        cdi    = 100 * (demand * supply_gap) / CDI_SCALE

    equity = equity_mult (Government view) or 1.0 (Operator view);
    w_act = 1 - w_pop.

    CDI_SCALE is the FROZEN baseline denominator (Government lens, equity ON,
    0.50/0.50) loaded from cdi_scale.json -- it is NOT this frame's own maximum.
    That distinction is the whole point: dividing by a per-configuration maximum
    made every score inflate whenever the settings lowered the maximum, so
    switching to the Operator lens appeared to DOUBLE the number of severe
    deserts (38 -> 75) without anyone's access changing. With a frozen scale the
    Operator lens correctly shows FEWER deserts than the Government lens, and a
    CDI of 60 means the same absolute severity under any setting.

    Consequence to be aware of: CDI = 100 marks the worst hex only under the
    baseline. Other settings can peak below 100, and a setting that raises
    demand (e.g. w_pop = 1.00) can legitimately push some hexes above 100.
    That is a real effect of the setting, not a scaling artefact.

    Pass the FULL hex frame and filter for display afterwards.
    """
    w_act = 1.0 - w_pop
    equity = df["equity_mult"] if equity_on else 1.0
    demand = (w_pop * df["pop_n"] + w_act * df["act_n"]) * equity
    raw = demand * df["supply_gap"]                       # supply_gap = 1 - supply_n
    peak = cdi_scale() if denom is None else float(denom)
    return (100.0 * raw / peak) if peak > 0 else raw * 0.0
