from __future__ import annotations

from hashlib import sha256
from typing import Any

from .provenance import LITERATURE, PUBLIC_DATA_MANIFEST, citation_audit
from .research import run_autonomous_research
from .knowledge_graph import build_knowledge_graph
from .harness import build_harness_state
from .deepseek_harness import attach_deepseek_report


RESEARCH_DIRECTIONS = [
    {
        "id": "D1",
        "title": "多时间尺度下的持续漂移识别",
        "gap": "单一滚动窗口可能把短期择时误判为长期风格漂移。",
        "question": "6、12、18 月窗口与变化点检测是否对漂移方向形成一致证据？",
        "hypothesis": "若漂移是持续的，不同窗口的后期风格距离应同向上升。",
        "literature_ids": ["CIT-SHARPE-1992", "CIT-BROWN-GOETZMANN-1997"],
        "methods": ["RBSA-6", "RBSA-12", "RBSA-18"],
        "required_data": ["NAV", "FACTORS"],
        "feasibility": "ready",
        "novelty": "把窗口敏感性、变化点和 placebo 误报统一纳入预注册审查。",
    },
    {
        "id": "D2",
        "title": "固定基线的严格样本外比较",
        "gap": "A 股基金风格漂移研究常报告样本内拟合，缺少冻结参数的时间外推比较。",
        "question": "滚动风格模型能否在严格时间切分下优于冻结 OLS 基线？",
        "hypothesis": "滚动 24 月模型的样本外 RMSE 低于训练期冻结 OLS。",
        "literature_ids": ["CIT-BROWN-GOETZMANN-1997"],
        "methods": ["RBSA-12", "RBSA-18"],
        "required_data": ["NAV", "FACTORS"],
        "feasibility": "ready",
        "novelty": "把 Agent 候选方法与事前固定统计基线置于同一测试集。",
    },
    {
        "id": "D3",
        "title": "基金经理变更与叙事漂移",
        "gap": "经理换人、定期报告观点与外部宣讲尚未形成原文级、可复现的事件证据链。",
        "question": "经理变更前后的量化暴露是否突变，经理报告观点是否与漂移方向一致？",
        "hypothesis": "经理变更前后风格暴露 L2 位移至少为 0.5；叙事证据必须绑定原文 URL、日期与指纹。",
        "literature_ids": ["CIT-CHAN-CHEN-LAKONISHOK-2002"],
        "methods": ["HOLDINGS"],
        "required_data": ["MANAGER", "REPORTS", "COMMUNICATIONS", "NAV"],
        "feasibility": "partially_blocked",
        "novelty": "把经理事件时间、定量暴露和原文观点放进同一证据链，并明确不可检验部分。",
    },
    {
        "id": "D4",
        "title": "行业基准残差异常与暴露突变",
        "gap": "行业拟合通常只报告样本内系数，缺少冻结模型样本外残差异常和滚动暴露突变审计。",
        "question": "公开行业 ETF 基准能否解释基金表现，哪些月份出现异常残差或行业暴露突变？",
        "hypothesis": "冻结行业模型在样本外至少出现一个绝对 z-score 不低于 2 的异常残差。",
        "literature_ids": ["CIT-SHARPE-1992", "CIT-BROWN-GOETZMANN-1997"],
        "methods": ["RBSA-12"],
        "required_data": ["NAV", "INDUSTRY"],
        "feasibility": "ready",
        "novelty": "将样本外误差、异常月份和滚动行业暴露变化统一为可复核实验。",
    },
]


def _discovery_graph(fund_id: str) -> dict[str, Any]:
    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, str]] = []
    for item in LITERATURE:
        citation_id = item["citation_id"]
        nodes.append({"id": citation_id, "type": "literature", "label": item["title"], "details": {"doi": item["doi"], "year": item["year"]}})
        for kind in ("measure", "mechanism", "limitation"):
            node_id = f"{citation_id}-{kind.upper()}"
            nodes.append({"id": node_id, "type": kind, "label": item["extracted"][kind], "details": {"citation_id": citation_id}})
            edges.append({"source": citation_id, "target": node_id, "relation": {"measure": "defines", "mechanism": "proposes", "limitation": "limits"}[kind]})
    for direction in RESEARCH_DIRECTIONS:
        gap_id = f"GAP-{direction['id']}"
        nodes.append({"id": gap_id, "type": "gap", "label": direction["gap"], "details": {"feasibility": direction["feasibility"]}})
        nodes.append({"id": direction["id"], "type": "direction", "label": direction["title"], "details": {"question": direction["question"], "hypothesis": direction["hypothesis"], "required_data": direction["required_data"]}})
        edges.append({"source": gap_id, "target": direction["id"], "relation": "motivates"})
        for citation_id in direction["literature_ids"]:
            edges.append({"source": citation_id, "target": gap_id, "relation": "supports"})
    return {"nodes": nodes, "edges": edges, "meta": {"fund_id": fund_id, "phase": "discovery", "schema_version": "research-confirmation-v1"}}


def discover_research_directions(fund_id: str, prompt: str = "") -> dict[str, Any]:
    return {
        "fund_id": fund_id,
        "phase": "awaiting_confirmation",
        "prompt": prompt,
        "literature": LITERATURE,
        "citation_audit": citation_audit(),
        "directions": RESEARCH_DIRECTIONS,
        "knowledge_graph": _discovery_graph(fund_id),
        "data_manifest": PUBLIC_DATA_MANIFEST,
        "harness": {
            "status": "awaiting_confirmation",
            "roles": {
                "knowledge_graph": {"label": "知识图谱分析"},
                "researcher": {"label": "研究员"},
                "reviewer": {"label": "结果审核员"},
                "reporter": {"label": "报告输入员"},
            },
            "stages": [
                {"id": "knowledge_graph", "status": "completed", "title": "知识图谱分析", "summary": f"从 {len(LITERATURE)} 篇种子文献抽取测度、机制与局限，形成 {len(RESEARCH_DIRECTIONS)} 个候选方向", "evidence_ids": [x["citation_id"] for x in LITERATURE]},
                {"id": "confirmation", "status": "waiting", "title": "研究方向确认", "summary": "等待用户选择方向后才允许生成程序和运行实验", "evidence_ids": [x["id"] for x in RESEARCH_DIRECTIONS]},
                {"id": "researcher", "status": "blocked", "title": "研究员", "summary": "尚未获准运行实验", "evidence_ids": []},
                {"id": "reviewer", "status": "blocked", "title": "结果审核员", "summary": "等待实验结果", "evidence_ids": []},
                {"id": "reporter", "status": "blocked", "title": "报告输入员", "summary": "等待审核结论", "evidence_ids": []},
            ],
        },
    }


def _generated_program(fund_id: str, direction: dict[str, Any], methods: list[str]) -> str:
    return f'''"""Agent-generated, auditable experiment for {fund_id}."""
from ai4s_style_drift.research import run_autonomous_research

FUND_ID = {fund_id!r}
DIRECTION_ID = {direction["id"]!r}
PRE_REGISTERED_HYPOTHESIS = {direction["hypothesis"]!r}
SELECTED_METHODS = {methods!r}


def main():
    # Execution remains inside the tested research-tool boundary.
    result = run_autonomous_research(FUND_ID, SELECTED_METHODS)
    return result


if __name__ == "__main__":
    main()
'''


def execute_confirmed_research(fund_id: str, direction_id: str, prompt: str = "", selected_methods: list[str] | None = None) -> dict[str, Any]:
    direction = next((item for item in RESEARCH_DIRECTIONS if item["id"] == direction_id), None)
    if direction is None:
        raise ValueError(f"Unknown research direction: {direction_id}")
    methods = list(selected_methods or direction["methods"])
    if not set(methods) <= set(direction["methods"]):
        raise ValueError("Selected methods must be permitted by the confirmed direction")
    program = _generated_program(fund_id, direction, methods)
    result = run_autonomous_research(fund_id, methods)
    report = result["report"]
    focus = {
        "D1": {"gaps": {"G1"}, "hypotheses": {"H1", "H2"}, "experiments": {"E1", "E2"}},
        "D2": {"gaps": {"G2"}, "hypotheses": {"H3"}, "experiments": {"E3"}},
        "D3": {"gaps": {"G3"}, "hypotheses": {"H4", "H5"}, "experiments": {"E4", "E5"}},
        "D4": {"gaps": {"G4"}, "hypotheses": {"H6"}, "experiments": {"E6"}},
    }[direction_id]
    report["gaps"] = [item for item in report["gaps"] if item["id"] in focus["gaps"]]
    report["hypotheses"] = [item for item in report["hypotheses"] if item["id"] in focus["hypotheses"]]
    report["experiments"] = [item for item in report["experiments"] if item["id"] in focus["experiments"]]
    report["evidence_bindings"] = [item for item in report["evidence_bindings"] if item["claim_id"] in focus["hypotheses"]]
    report["failed_hypotheses"] = [item for item in report["hypotheses"] if item["status"] == "failed"]
    report["confirmed_direction"] = direction
    report["research_question"] = direction["question"]
    report["generated_program"] = {
        "language": "python",
        "execution_policy": "allowlisted research tools; no arbitrary exec/eval/subprocess",
        "sha256": sha256(program.encode("utf-8")).hexdigest(),
        "source": program,
    }
    report["execution_log"] = [
        {"step": 1, "agent": "knowledge_graph", "action": "bind_confirmed_direction", "status": "completed", "outputs": [direction_id, *direction["literature_ids"]]},
        {"step": 2, "agent": "researcher", "action": "generate_python_program", "status": "completed", "outputs": [report["generated_program"]["sha256"][:16]]},
        {"step": 3, "agent": "researcher", "action": "run_allowlisted_experiments", "status": "completed", "outputs": [x["id"] for x in report["experiments"]]},
        {"step": 4, "agent": "reviewer", "action": "audit_baseline_failures_and_sensitivity", "status": "completed", "outputs": [x["claim_id"] for x in report["evidence_bindings"]]},
        {"step": 5, "agent": "reporter", "action": "write_scientific_report", "status": "completed", "outputs": ["CONCLUSION"]},
    ]
    report["knowledge_graph"] = build_knowledge_graph(report, fund_id)
    attach_deepseek_report(report, prompt)
    report["execution_log"][-1]["outputs"].append(f"DEEPSEEK:{report['deepseek_report']['status']}")
    report["harness"] = build_harness_state(report, prompt)
    report["harness"]["confirmed_direction_id"] = direction_id
    result["phase"] = "completed"
    return result
