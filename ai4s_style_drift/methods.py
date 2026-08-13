from __future__ import annotations

from typing import Any
import re

import numpy as np
import pandas as pd

from .tools import detect_change_points, rolling_factor_exposure, style_distance


METHOD_CATALOG = [
    {"id": "RBSA-6", "label": "短窗口收益风格", "window": 6, "source_id": "CIT-SHARPE-1992-MEASURE", "data": ["DATA-NAV", "DATA-FACTORS"], "limitation": "短窗口对噪声和因子共线性敏感"},
    {"id": "RBSA-12", "label": "标准收益风格", "window": 12, "source_id": "CIT-SHARPE-1992-MEASURE", "data": ["DATA-NAV", "DATA-FACTORS"], "limitation": "可能遗漏披露期内调仓"},
    {"id": "RBSA-18", "label": "长窗口收益风格", "window": 18, "source_id": "CIT-SHARPE-1992-MEASURE", "data": ["DATA-NAV", "DATA-FACTORS"], "limitation": "变化响应较慢且需要更长历史"},
    {"id": "HOLDINGS", "label": "季度持仓集中度", "window": None, "source_id": "CIT-CHAN-CHEN-LAKONISHOK-2002-MEASURE", "data": ["DATA-HOLDINGS"], "limitation": "季度快照无法还原披露期内交易"},
]


def _effect(values: pd.Series) -> tuple[float, float, float]:
    mid = len(values) // 2
    pre, post = float(values.iloc[:mid].mean()), float(values.iloc[mid:].mean())
    return pre, post, post - pre


def _rbsa(method: dict[str, Any], returns: pd.DataFrame, target: pd.Series) -> dict[str, Any]:
    exposure = rolling_factor_exposure(returns, window=method["window"])
    distance = style_distance(exposure, target)
    pre, post, delta = _effect(distance)
    points = detect_change_points(distance)
    return {"status": "completed", "n_observations": len(distance), "pre_distance": round(pre, 4), "post_distance": round(post, 4), "effect_delta": round(delta, 4), "drift_detected": bool(delta > 0 and points), "direction": "increase" if delta > 0 else "decrease", "change_points": points}


def _holding_weights(holdings: pd.DataFrame) -> pd.Series | None:
    if holdings.empty or "source_table" not in holdings:
        return None
    candidates = [c for c in holdings.columns if re.search(r"比例|占净值|weight", str(c), re.I)]
    if not candidates:
        return None
    values = holdings[candidates[0]].astype(str).str.replace("%", "", regex=False).str.replace("--", "", regex=False)
    numeric = pd.to_numeric(values, errors="coerce")
    grouped = numeric.groupby(holdings["source_table"]).sum(min_count=1).dropna().sort_index()
    return grouped / (100.0 if grouped.max() > 1.5 else 1.0)


def _holdings(method: dict[str, Any], holdings: pd.DataFrame) -> dict[str, Any]:
    values = _holding_weights(holdings)
    if values is None or len(values) < 2:
        return {"status": "not_testable", "reason": "公开持仓缺少至少两个可比较季度的权重字段", "n_observations": 0}
    pre, post, delta = _effect(values)
    return {"status": "completed", "n_observations": len(values), "pre_concentration": round(pre, 4), "post_concentration": round(post, 4), "effect_delta": round(delta, 4), "drift_detected": bool(abs(delta) >= 0.05), "direction": "increase" if delta > 0 else "decrease", "change_points": []}


def compare_methods(returns: pd.DataFrame, holdings: pd.DataFrame, target: pd.Series, selected: list[str] | None = None) -> dict[str, Any]:
    selected_ids = [method["id"] for method in METHOD_CATALOG] if selected is None else selected
    if not selected_ids:
        raise ValueError("Select at least one research method")
    unknown = sorted(set(selected_ids) - {method["id"] for method in METHOD_CATALOG})
    if unknown:
        raise ValueError(f"Unknown research methods: {', '.join(unknown)}")
    results = []
    for method in METHOD_CATALOG:
        if method["id"] not in selected_ids:
            continue
        result = _holdings(method, holdings) if method["id"] == "HOLDINGS" else _rbsa(method, returns, target)
        results.append({**method, "result": result})
    completed = [item for item in results if item["result"]["status"] == "completed"]
    signals = [item["result"]["drift_detected"] for item in completed]
    agreement = float(sum(signals) / len(signals)) if signals else 0.0
    return {"selected_ids": selected_ids, "methods": results, "review": {"completed": len(completed), "not_testable": len(results) - len(completed), "drift_vote_share": round(agreement, 3), "consensus": "drift" if agreement >= 0.67 else "no_drift" if agreement <= 0.33 else "mixed", "warning": "不同方法的效应量口径不同，只比较信号方向与可检验性，不直接比较数值大小。"}}
