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


def recompute_cdi(df: pd.DataFrame, w_pop: float = 0.5, equity_on: bool = True) -> pd.Series:
    """Re-mix CDI (0-100) from the stored components, exactly like
    pipeline/06_build_cdi.py:

        demand = (w_pop*pop_n + w_act*act_n) * equity
        cdi    = 100 * norm(demand * supply_gap)          # norm = divide by max

    equity = equity_mult (Government view) or 1.0 (Operator view);
    w_act = 1 - w_pop. Normalization is global over the rows passed in, so
    CDI = 100 always marks the single worst hex. Pass the FULL hex frame so the
    max is the KV-wide max, then filter for display afterwards.
    """
    w_act = 1.0 - w_pop
    equity = df["equity_mult"] if equity_on else 1.0
    demand = (w_pop * df["pop_n"] + w_act * df["act_n"]) * equity
    raw = demand * df["supply_gap"]                       # supply_gap = 1 - supply_n
    peak = raw.max()
    return (100.0 * raw / peak) if peak > 0 else raw * 0.0
