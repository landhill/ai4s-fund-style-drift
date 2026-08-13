from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable
import numpy as np
import pandas as pd


STYLE_COLS = ["market", "size", "value", "momentum", "quality", "tech"]


def rolling_factor_exposure(returns: pd.DataFrame, window: int = 12) -> pd.DataFrame:
    """OLS rolling factor exposures; rows are dates and columns are factors."""
    y = returns["fund"] - returns["rf"]
    X = returns[["market", "size_factor", "value_factor", "momentum_factor", "quality_factor", "tech_factor"]]
    names = STYLE_COLS
    out = []
    for i in range(window - 1, len(returns)):
        xx, yy = X.iloc[i - window + 1 : i + 1].to_numpy(), y.iloc[i - window + 1 : i + 1].to_numpy()
        beta = np.linalg.lstsq(np.c_[np.ones(len(xx)), xx], yy, rcond=None)[0][1:]
        out.append([returns.index[i], *beta])
    return pd.DataFrame(out, columns=["date", *names]).set_index("date")


def style_distance(exposure: pd.DataFrame, target: pd.Series) -> pd.Series:
    z = (exposure - target) / (exposure.std(ddof=0).replace(0, 1.0))
    return np.sqrt((z**2).sum(axis=1)).rename("style_distance")


def detect_change_points(series: pd.Series, z_threshold: float = 0.75, persistence: int = 3) -> list[dict]:
    """Detect a sustained *increase* in distance with a dependency-free level-shift scan."""
    w = max(4, min(6, len(series) // 5))
    sd = series.iloc[: max(6, len(series) // 3)].std(ddof=0) or 1.0
    candidates = []
    for i in range(w, len(series) - w + 1):
        before, after = series.iloc[i - w : i], series.iloc[i : i + w]
        score = float(after.mean() - before.mean()) / sd
        if score >= z_threshold and bool((after.iloc[:persistence] > before.mean()).all()):
            candidates.append((score, i))
    if not candidates:
        return []
    score, i = max(candidates)
    return [{"date": str(series.index[i].date()), "z": round(score, 2), "method": "sustained_level_shift"}]


def robustness_check(exposure: pd.DataFrame, target: pd.Series) -> dict:
    d = style_distance(exposure, target)
    mid = len(d) // 2
    return {
        "full_mean_distance": round(float(d.mean()), 4),
        "first_half_mean_distance": round(float(d.iloc[:mid].mean()), 4),
        "second_half_mean_distance": round(float(d.iloc[mid:].mean()), 4),
        "positive_drift": bool(d.iloc[mid:].mean() > d.iloc[:mid].mean()),
        "alternative_window_note": "OLS window sensitivity should be rerun with 6/18 months on real data",
    }
