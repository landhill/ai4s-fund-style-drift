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


def industry_residual_analysis(fund_returns: pd.Series, industry_returns: pd.DataFrame, z_threshold: float = 2.0) -> dict:
    """Fit frozen industry proxies and audit out-of-sample residual anomalies."""
    aligned = pd.concat([fund_returns.rename("fund"), industry_returns], axis=1, sort=True).dropna()
    if len(aligned) < 18 or aligned.shape[1] < 3:
        return {"status": "not_testable", "reason": "at least 18 aligned months and two industry proxies are required", "n_observations": len(aligned)}
    factor_names = list(aligned.columns[1:])
    split = max(12, int(len(aligned) * 0.65))
    if len(aligned) - split < 4:
        split = len(aligned) - 4
    train, test = aligned.iloc[:split], aligned.iloc[split:]
    x_train = np.c_[np.ones(len(train)), train[factor_names].to_numpy()]
    beta = np.linalg.lstsq(x_train, train["fund"].to_numpy(), rcond=None)[0]
    train_residual = train["fund"].to_numpy() - x_train @ beta
    predicted = np.c_[np.ones(len(test)), test[factor_names].to_numpy()] @ beta
    residual = pd.Series(test["fund"].to_numpy() - predicted, index=test.index)
    scale = float(np.std(train_residual, ddof=1)) or 1.0
    z_score = residual / scale
    anomalies = [
        {"date": str(date.date()), "residual": round(float(residual.loc[date]), 6), "z_score": round(float(value), 3)}
        for date, value in z_score.items() if abs(value) >= z_threshold
    ]
    window = min(12, max(6, len(aligned) // 3))
    rolling_betas = []
    for end in range(window, len(aligned) + 1):
        sample = aligned.iloc[end - window:end]
        coef = np.linalg.lstsq(np.c_[np.ones(len(sample)), sample[factor_names].to_numpy()], sample["fund"].to_numpy(), rcond=None)[0][1:]
        rolling_betas.append(coef)
    beta_shift = np.asarray(rolling_betas[-1]) - np.asarray(rolling_betas[0])
    shifts = sorted(
        ({"industry": name, "change": round(float(change), 4)} for name, change in zip(factor_names, beta_shift)),
        key=lambda item: abs(item["change"]), reverse=True,
    )
    return {
        "status": "completed",
        "protocol": {"train_months": len(train), "test_months": len(test), "frozen_parameters": True, "z_threshold": z_threshold},
        "metrics": {"rmse": round(float(np.sqrt(np.mean(residual.to_numpy() ** 2))), 6), "mae": round(float(np.mean(np.abs(residual.to_numpy()))), 6)},
        "anomaly_months": anomalies,
        "anomaly_share": round(len(anomalies) / len(test), 3),
        "max_abs_z": round(float(z_score.abs().max()), 3),
        "rolling_exposure_changes": shifts,
        "proxy_warning": "Industry ETFs are observable investable proxies, not an exhaustive or orthogonal industry factor model.",
    }
