from __future__ import annotations

from typing import Any, TypedDict
import json
import pandas as pd
from .data import make_fund_data
from .tools import rolling_factor_exposure, style_distance, detect_change_points, robustness_check

try:
    from langgraph.graph import StateGraph, END
    HAS_LANGGRAPH = True
except ImportError:  # keeps the demo runnable before pip install
    HAS_LANGGRAPH = False


class ResearchState(TypedDict, total=False):
    returns: pd.DataFrame
    holdings: pd.DataFrame
    mandate: dict
    exposure: pd.DataFrame
    distance: pd.Series
    change_points: list[dict]
    attribution: dict
    robustness: dict
    report: str


def contract_agent(s: ResearchState) -> ResearchState:
    return {"mandate": s["mandate"]}


def style_agent(s: ResearchState) -> ResearchState:
    e = rolling_factor_exposure(s["returns"])
    return {"exposure": e, "distance": style_distance(e, s["mandate"]["target"])}


def change_point_agent(s: ResearchState) -> ResearchState:
    return {"change_points": detect_change_points(s["distance"])}


def attribution_agent(s: ResearchState) -> ResearchState:
    cp = s.get("change_points", [])
    exposure = s["exposure"]; split = max(1, len(exposure) // 2)
    delta = exposure.iloc[split:].mean() - exposure.iloc[:split].mean()
    top = delta.abs().sort_values(ascending=False).head(2).index.tolist()
    evidence = [f"{name}: {delta[name]:+.3f}" for name in top]
    is_etf = s["mandate"].get("fund_structure") == "exchange_traded_fund_candidate"
    hypothesis = ("主要暴露变化集中于 " + "、".join(top) + "；ETF 应优先检验指数成分调整、跟踪误差与申赎冲击" if is_etf else "主要暴露变化集中于 " + "、".join(top) + "；需结合持仓和资金流识别机制")
    return {"attribution": {"leading_hypothesis": hypothesis, "evidence": evidence, "causal_status": "descriptive exposure change; causal mechanism not identified", "change_point": cp[0]["date"] if cp else None}}


def robustness_agent(s: ResearchState) -> ResearchState:
    return {"robustness": robustness_check(s["exposure"], s["mandate"]["target"])}


def report_agent(s: ResearchState) -> ResearchState:
    e, d = s["exposure"], s["distance"]
    split = max(1, len(e) // 2)
    pre, post = e.iloc[:split].mean(), e.iloc[split:].mean()
    report = {"fund": s["mandate"]["fund_id"], "data_note": ("Public Eastmoney data with ETF proxy factors; unofficial endpoints and not an investment recommendation." if s["mandate"].get("data_source") == "eastmoney_public" else "Synthetic data for pipeline validation; not an investment recommendation."), "declared_style": s["mandate"]["declared_style"], "change_points": s.get("change_points", []), "comparison_split": str(e.index[split].date()) if split < len(e) else None, "mean_exposure_pre": pre.round(3).to_dict(), "mean_exposure_post": post.round(3).to_dict(), "distance": {"pre": round(float(d.iloc[:split].mean()), 3), "post": round(float(d.iloc[split:].mean()), 3)}, "attribution": s.get("attribution", {}), "robustness": s.get("robustness", {})}
    return {"report": json.dumps(report, ensure_ascii=False, indent=2)}


def build_research_graph():
    if not HAS_LANGGRAPH:
        return None
    g = StateGraph(ResearchState)
    for name, fn in [("contract", contract_agent), ("style", style_agent), ("change_point", change_point_agent), ("attribution", attribution_agent), ("robustness", robustness_agent), ("report", report_agent)]:
        g.add_node(name, fn)
    g.set_entry_point("contract")
    g.add_edge("contract", "style"); g.add_edge("style", "change_point"); g.add_edge("change_point", "attribution"); g.add_edge("attribution", "robustness"); g.add_edge("robustness", "report"); g.add_edge("report", END)
    return g.compile()


def run_demo(fund_id: str = "DEMO-TECH") -> ResearchState:
    returns, holdings, mandate = make_fund_data(fund_id)
    state: ResearchState = {"returns": returns, "holdings": holdings, "mandate": mandate}
    graph = build_research_graph()
    if graph:
        return graph.invoke(state)
    for fn in (contract_agent, style_agent, change_point_agent, attribution_agent, robustness_agent, report_agent):
        state.update(fn(state))
    return state


if __name__ == "__main__":
    result = run_demo()
    print(result["report"])
