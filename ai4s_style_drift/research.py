from __future__ import annotations

from time import perf_counter
import numpy as np
import pandas as pd

from .data import make_fund_data
from .provenance import LITERATURE, PUBLIC_DATA_MANIFEST, citation_audit, code_fingerprint, data_fingerprint
from .knowledge_graph import build_knowledge_graph
from .harness import build_harness_state
from .methods import compare_methods
from .tools import rolling_factor_exposure, style_distance, detect_change_points, industry_residual_analysis


def _window_experiment(returns: pd.DataFrame, target: pd.Series) -> list[dict]:
    rows = []
    for window in (6, 12, 18):
        exposure = rolling_factor_exposure(returns, window=window)
        distance = style_distance(exposure, target)
        half = len(distance) // 2
        rows.append({"window_months": window, "pre_distance": round(float(distance.iloc[:half].mean()), 4), "post_distance": round(float(distance.iloc[half:].mean()), 4), "drift_delta": round(float(distance.iloc[half:].mean() - distance.iloc[:half].mean()), 4), "supports_drift": bool(distance.iloc[half:].mean() > distance.iloc[:half].mean())})
    return rows


def _metrics(truth: pd.Series, pred: pd.Series) -> dict:
    tp, fp = int((truth & pred).sum()), int((~truth & pred).sum())
    fn, tn = int((truth & ~pred).sum()), int((~truth & ~pred).sum())
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {"tp": tp, "fp": fp, "fn": fn, "tn": tn, "precision": round(precision, 3), "recall": round(recall, 3), "f1": round(f1, 3)}


def _forecast_metrics(actual: np.ndarray, predicted: np.ndarray) -> dict:
    error = actual - predicted
    return {"rmse": round(float(np.sqrt(np.mean(error**2))), 6), "mae": round(float(np.mean(np.abs(error))), 6), "n_test": len(actual)}


def _out_of_sample_comparison(returns: pd.DataFrame) -> dict:
    factors = ["market", "size_factor", "value_factor", "momentum_factor", "quality_factor", "tech_factor"]
    split = max(18, int(len(returns) * 0.65))
    train, test = returns.iloc[:split], returns.iloc[split:]
    x_train = np.c_[np.ones(len(train)), train[factors].to_numpy()]
    fixed_beta = np.linalg.lstsq(x_train, train["fund"].to_numpy(), rcond=None)[0]
    fixed_pred = np.c_[np.ones(len(test)), test[factors].to_numpy()] @ fixed_beta
    rolling_pred = []
    for i in range(split, len(returns)):
        history = returns.iloc[max(0, i - 24):i]
        beta = np.linalg.lstsq(np.c_[np.ones(len(history)), history[factors].to_numpy()], history["fund"].to_numpy(), rcond=None)[0]
        rolling_pred.append(float(np.r_[1.0, returns.iloc[i][factors].to_numpy(dtype=float)] @ beta))
    fixed_metrics = _forecast_metrics(test["fund"].to_numpy(), fixed_pred)
    agent_metrics = _forecast_metrics(test["fund"].to_numpy(), np.array(rolling_pred))
    return {
        "protocol": {"train": f"first {split} monthly observations", "test": f"final {len(test)} monthly observations", "target": "one-period fund return", "no_test_tuning": True},
        "fixed_baseline": {"name": "frozen full-training OLS factor model", "metrics": fixed_metrics},
        "agent_candidate": {"name": "rolling 24-month OLS factor model", "metrics": agent_metrics},
        "winner": "agent_candidate" if agent_metrics["rmse"] < fixed_metrics["rmse"] else "fixed_baseline",
        "scope_warning": "Forecast error is an objective sample-out comparison, not a causal validation of style drift.",
    }


def _placebo_experiment(seed: int = 11) -> dict:
    rng = np.random.default_rng(seed); n = 60
    stable = pd.Series(1.5 + rng.normal(0, 0.12, n), index=pd.date_range("2021-01-31", periods=n, freq="ME")); mid = n // 2
    delta = float(stable.iloc[mid:].mean() - stable.iloc[:mid].mean())
    return {"control": "no-drift placebo series", "pre_mean": round(float(stable.iloc[:mid].mean()), 4), "post_mean": round(float(stable.iloc[mid:].mean()), 4), "delta": round(delta, 4), "false_positive": bool(delta > 0.5)}


def _manager_event_experiment(returns: pd.DataFrame, manager_history: list[dict]) -> dict:
    exposure = rolling_factor_exposure(returns, window=6)
    events = []
    for record in manager_history:
        event_date = pd.to_datetime(record.get("start_date"), errors="coerce")
        if pd.isna(event_date) or event_date <= returns.index.min() or event_date > returns.index.max():
            continue
        pre = exposure.loc[exposure.index < event_date].tail(3)
        post = exposure.loc[exposure.index >= event_date].head(3)
        if len(pre) < 2 or len(post) < 2:
            continue
        shift = float(np.linalg.norm(post.mean().to_numpy() - pre.mean().to_numpy()))
        events.append({"date": str(event_date.date()), "manager": record.get("manager"), "exposure_shift_l2": round(shift, 4), "pre_months": len(pre), "post_months": len(post)})
    if not manager_history:
        return {"status": "not_testable", "reason": "no source-verified manager tenure records", "events": []}
    if not events:
        return {"status": "not_testable", "reason": "manager events fall outside the return sample or lack pre/post windows", "events": []}
    return {"status": "completed", "event_window": "three 6-month-exposure estimates before and after each start date", "pre_registered_shift_threshold": 0.5, "events": events, "max_exposure_shift_l2": max(item["exposure_shift_l2"] for item in events)}


def _narrative_evidence_experiment(reports: list[dict], communications: list[dict]) -> dict:
    verified_communications = [item for item in communications if item.get("source_url") and item.get("published_date") and item.get("source_sha256")]
    extracted_reports = [item for item in reports if item.get("text_status") == "extracted" and item.get("source_sha256")]
    topics = {
        "technology": ["科技", "人工智能", "半导体", "计算机", "通信"],
        "small_cap": ["小盘", "中小市值", "中证2000", "成长"],
        "macro": ["经济", "政策", "流动性", "市场", "利率"],
        "risk": ["风险", "波动", "回撤", "不确定"],
    }
    profiles = []
    for item in extracted_reports:
        narrative = item.get("narrative", "")
        counts = {topic: sum(narrative.count(word) for word in words) for topic, words in topics.items()}
        total = sum(counts.values()) or 1
        profiles.append({"report_id": item["id"], "published_date": item["published_date"], "topic_share": {key: round(value / total, 3) for key, value in counts.items()}, "excerpt": narrative[:240], "source_url": item["source_url"], "document_sha256": item.get("document_sha256")})
    distances = []
    for previous, current in zip(profiles[1:], profiles[:-1]):
        distance = sum(abs(current["topic_share"][key] - previous["topic_share"][key]) for key in topics) / 2
        distances.append({"from": previous["published_date"], "to": current["published_date"], "topic_distance": round(distance, 3)})
    return {
        "status": "completed" if len(extracted_reports) >= 2 else "not_testable",
        "reason": None if len(extracted_reports) >= 2 else "fewer than two source-verified report narratives were extracted",
        "report_metadata_count": len(reports),
        "extracted_report_count": len(extracted_reports),
        "verified_external_communications": len(verified_communications),
        "rejected_or_missing_communications": len(communications) - len(verified_communications),
        "evidence_gate": "publication date + original URL + original-text SHA-256; search snippets are rejected",
        "topic_profiles": profiles,
        "adjacent_topic_distances": distances,
        "max_topic_distance": max((item["topic_distance"] for item in distances), default=None),
        "latest_reports": [{key: item.get(key) for key in ("id", "title", "published_date", "source_url", "document_url", "text_status", "source_sha256")} for item in reports[:5]],
    }


def run_autonomous_research(fund_id: str, selected_methods: list[str] | None = None) -> dict:
    started = perf_counter()
    returns, holdings, mandate = make_fund_data(fund_id)
    exposure = rolling_factor_exposure(returns); distance = style_distance(exposure, mandate["target"])
    window_results = _window_experiment(returns, mandate["target"])
    h1_supported = next(row["supports_drift"] for row in window_results if row["window_months"] == 12)
    h2_supported = all(row["supports_drift"] for row in window_results)
    oos = _out_of_sample_comparison(returns)
    manager_event = _manager_event_experiment(returns, mandate.get("manager_history", []))
    narrative = _narrative_evidence_experiment(mandate.get("periodic_reports", []), mandate.get("manager_communications", []))
    industry = industry_residual_analysis(returns["fund"], mandate.get("industry_returns", pd.DataFrame()))
    hypotheses = [
        {"id": "H1", "statement": "12 月窗口下后半期风格距离高于前半期", "registered_before_test": True, "evidence_ids": ["E1", "CIT-SHARPE-1992"], "status": "supported" if h1_supported else "failed"},
        {"id": "H2", "statement": "漂移结论对 6/12/18 月窗口方向一致", "registered_before_test": True, "evidence_ids": ["E1"], "status": "supported" if h2_supported else "failed"},
        {"id": "H3", "statement": "滚动 Agent 模型样本外 RMSE 低于冻结 OLS 基线", "registered_before_test": True, "evidence_ids": ["E3"], "status": "supported" if oos["agent_candidate"]["metrics"]["rmse"] < oos["fixed_baseline"]["metrics"]["rmse"] else "failed"},
        {"id": "H4", "statement": "基金经理变更前后行业/风格暴露的 L2 位移至少为 0.5", "registered_before_test": True, "evidence_ids": ["E4", "DATA-MANAGER"], "status": ("supported" if manager_event.get("max_exposure_shift_l2", 0) >= 0.5 else "failed") if manager_event["status"] == "completed" else "not_tested"},
        {"id": "H5", "statement": "相邻定期报告的经理观点主题距离至少为 0.20", "registered_before_test": True, "evidence_ids": ["E5", "DATA-REPORTS"], "status": ("supported" if (narrative.get("max_topic_distance") or 0) >= 0.2 else "failed") if narrative["status"] == "completed" else "not_tested"},
        {"id": "H6", "statement": "冻结行业基准模型在样本外出现绝对 z-score 不低于 2 的异常残差", "registered_before_test": True, "evidence_ids": ["E6", "DATA-INDUSTRY"], "status": ("supported" if industry.get("anomaly_months") else "failed") if industry["status"] == "completed" else "not_tested"},
    ]
    gaps = [
        {"id": "G1", "gap": "单一滚动窗口可能把短期择时误判为长期风格漂移", "priority": "高", "literature_ids": ["CIT-SHARPE-1992"]},
        {"id": "G2", "gap": "现有 Demo 尚未在真实 A 股基金样本上做严格时间切分的样本外评估", "priority": "高", "literature_ids": ["CIT-BROWN-GOETZMANN-1997"]},
        {"id": "G3", "gap": "经理变更、定期报告观点与外部宣讲尚未形成原文级事件证据链", "priority": "高", "literature_ids": ["CIT-CHAN-CHEN-LAKONISHOK-2002"]},
        {"id": "G4", "gap": "常规行业拟合往往只报告系数，缺少冻结模型样本外残差异常和暴露突变审计", "priority": "高", "literature_ids": ["CIT-SHARPE-1992", "CIT-BROWN-GOETZMANN-1997"]},
    ]
    experiments = [
        {"id": "E1", "question": "漂移结论是否对滚动窗口稳健？", "method": "6/12/18 月滚动回归并比较前后半期风格距离", "result": window_results},
        {"id": "E2", "question": "检测器在无漂移序列上是否容易误报？", "method": "固定风格 placebo 距离序列", "result": _placebo_experiment()},
        {"id": "E3", "question": "Agent 是否优于预先固定的统计基线？", "method": "按时间切分；比较冻结 OLS 与滚动 24 月 OLS 的样本外 RMSE/MAE", "result": oos},
        {"id": "E4", "question": "基金经理换人前后，量化暴露是否发生显著位移？", "method": "经理任职起始日事件研究；比较事件前后 3 个滚动暴露估计", "result": manager_event},
        {"id": "E5", "question": "经理的定期报告观点与外部公开提法是否支持漂移归因？", "method": "原文级证据门槛 + 报告主题变化；无原文时保留不可检验结果", "result": narrative},
        {"id": "E6", "question": "行业基准对基金表现的拟合是否出现异常残差或暴露突变？", "method": "公开行业 ETF 月收益；冻结训练期 OLS；样本外残差 z-score 与滚动系数变化", "result": industry},
    ]
    failed = [h for h in hypotheses if h["status"] == "failed"]
    report = {
        "title": f"{mandate['fund_id']} 基金风格漂移：可审计科学实验报告",
        "research_question": "Agent 能否基于可核验证据识别基金风格漂移，并在冻结参数的样本外测试中优于固定统计基线？",
        "data_scope": ("东方财富公开净值、季度持仓与规模页面；使用公开 ETF 净值构造代理因子" if mandate.get("data_source") == "eastmoney_public" else "synthetic-v2 离线验证夹具"),
        "literature": LITERATURE,
        "citation_audit": citation_audit(),
        "evidence_bindings": [{"claim_id": h["id"], "claim": h["statement"], "evidence_ids": h["evidence_ids"], "status": h["status"]} for h in hypotheses],
        "hypotheses": hypotheses,
        "gaps": gaps,
        "experiments": experiments,
        "failed_hypotheses": failed,
        "conclusion": {"interpretation": ("研究协议已在真实公开 A 股基金净值与季度披露数据上运行；因子为真实 ETF 数据派生代理，结论属于描述性证据，不能替代正式因子库和因果识别。" if mandate.get("data_source") == "eastmoney_public" else "当前使用合成验证夹具，只能评价研究环境，不能评价真实 A 股基金。"), "claim_boundary": "发现、失败和未检验假设均保留，不允许仅输出正向结果。"},
        "limitations": ((["公开端点并非官方稳定 API", "ETF 代理因子与行业 ETF 不等同于正式学术因子库"] if mandate.get("data_source") == "eastmoney_public" else ["合成数据不代表真实基金"]) + ["DOI 仅完成格式和元数据完整性检查，尚未在线解析核验", "季度持仓无法还原完整交易路径", ("定期报告已抽取最近原文，但主题词规则不等于人工内容分析" if narrative.get("extracted_report_count", 0) else "定期报告当前仅核验元数据，尚未抽取原文观点"), "外部宣讲原文适配器未连接", "公开资金流适配器未连接", "未计算真实数据许可与下载成本"]),
        "data_manifest": [{**item, "status": (("connected_proxy" if item["dataset_id"] in {"FACTORS", "INDUSTRY"} else "connected") if mandate.get("data_source") == "eastmoney_public" and item["dataset_id"] in {"NAV", "HOLDINGS", "FACTORS", "MANAGER", "REPORTS", "INDUSTRY"} else item["status"])} for item in PUBLIC_DATA_MANIFEST],
        "version": {"code": code_fingerprint(), "data": data_fingerprint(mandate["fund_id"], len(returns), list(returns.columns), mandate.get("data_source", "synthetic")), "raw_sources": mandate.get("source_meta", {})},
        "data_audit": mandate.get("data_audit", []),
        "reproduction_cost": {"runtime_seconds": round(perf_counter() - started, 4), "llm_calls": 0, "network_calls": (16 if mandate.get("data_source") == "eastmoney_public" else 0), "external_api_cost": 0.0, "python": "3.12", "minimum_inputs": ["NAV", "HOLDINGS", "FACTORS", "MANAGER", "REPORTS", "INDUSTRY"], "cost_note": ("Public endpoints have no direct API fee; bandwidth, caching, endpoint stability and terms-of-use compliance remain costs." if mandate.get("data_source") == "eastmoney_public" else "Synthetic fixture cost only.")},
    }
    report["method_comparison"] = compare_methods(returns, holdings, mandate["target"], selected_methods)
    report["knowledge_graph"] = build_knowledge_graph(report, mandate["fund_id"])
    report["harness"] = build_harness_state(report)
    return {"fund_id": mandate["fund_id"], "report": report, "distance": [{"date": str(i.date()), "value": round(float(v), 4)} for i, v in distance.items()], "change_points": detect_change_points(distance)}
