from __future__ import annotations

import numpy as np
import pandas as pd
import re


def make_demo_data(seed: int = 7, fund_id: str = "DEMO-TECH") -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    """Synthetic but economically plausible A-share technology-fund example.

    The data deliberately contains a persistent drift after 2024-01. Replace this
    function with licensed NAV/holdings/factor data for production research.
    """
    rng = np.random.default_rng(seed)
    dates = pd.date_range("2021-01-31", "2025-12-31", freq="ME")
    n = len(dates)
    fac = rng.normal(0, 0.035, (n, 5))
    fac[:, 0] += 0.006  # market
    fac[:, 1] += 0.002  # size
    fac[:, 2] += 0.001  # value
    fac[:, 3] += 0.002  # momentum
    fac[:, 4] += 0.001  # quality
    tech = rng.normal(0.004, 0.025, n)
    drift = dates >= pd.Timestamp("2024-01-31")
    beta_pre = np.array([0.95, -0.15, -0.20, 0.30, 0.35, 0.75])
    beta_post = np.array([0.80, 0.55, 0.05, 0.85, 0.05, 0.35])
    beta = np.where(drift[:, None], beta_post, beta_pre)
    noise = rng.normal(0, 0.018, n)
    fund = 0.002 + beta[:, 0] * fac[:, 0] + beta[:, 1] * fac[:, 1] + beta[:, 2] * fac[:, 2] + beta[:, 3] * fac[:, 3] + beta[:, 4] * fac[:, 4] + beta[:, 5] * tech + noise
    returns = pd.DataFrame({"fund": fund, "rf": 0.001, "market": fac[:, 0], "size_factor": fac[:, 1], "value_factor": fac[:, 2], "momentum_factor": fac[:, 3], "quality_factor": fac[:, 4], "tech_factor": tech}, index=dates)
    holdings = pd.DataFrame({"date": dates[::3], "large_cap": np.where(dates[::3] < "2024-01-31", 0.72, 0.38), "small_cap": np.where(dates[::3] < "2024-01-31", 0.12, 0.42), "growth": np.where(dates[::3] < "2024-01-31", 0.68, 0.35), "momentum": np.where(dates[::3] < "2024-01-31", 0.28, 0.70), "tech": np.where(dates[::3] < "2024-01-31", 0.62, 0.48)}).set_index("date")
    mandate = {"fund_id": fund_id, "declared_style": "large-cap growth technology", "target": pd.Series([0.95, -0.15, -0.20, 0.30, 0.35, 0.75], index=["market", "size", "value", "momentum", "quality", "tech"]), "benchmark": "CSI300-like market factor", "evidence": "demo_contract: technology fund prospectus, section 3", "data_source": "synthetic", "factor_model": "synthetic known factors"}
    return returns, holdings, mandate


def make_fund_data(fund_id: str) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    """Resolve a requested fund into a deterministic demo profile.

    Production replacement point: query licensed NAV/holdings/contract providers
    here and preserve the same return schema.
    """
    clean = (fund_id or "DEMO-TECH").strip().upper()
    if re.fullmatch(r"\d{6}", clean):
        from .public_data import load_public_fund
        return load_public_fund(clean)
    seed = sum((i + 1) * ord(ch) for i, ch in enumerate(clean)) % 997
    return make_demo_data(seed=seed, fund_id=clean)
