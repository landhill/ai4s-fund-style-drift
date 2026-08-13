from __future__ import annotations

from typing import Any


ROLE_META = {
    "knowledge_graph": {"label": "知识图谱分析", "short": "KG", "color": "blue"},
    "researcher": {"label": "研究员", "short": "R", "color": "green"},
    "reviewer": {"label": "结果审核员", "short": "QA", "color": "amber"},
    "reporter": {"label": "报告输入员", "short": "REP", "color": "red"},
}


def build_harness_state(report: dict[str, Any], prompt: str = "") -> dict[str, Any]:
    graph = report["knowledge_graph"]
    supported = sum(h["status"] == "supported" for h in report["hypotheses"])
    failed = sum(h["status"] == "failed" for h in report["hypotheses"])
    comparison = report.get("method_comparison", {"methods": [], "review": {"consensus": "not_run", "not_testable": 0}})
    stages = [
        {"id": "knowledge_graph", "status": "completed", "title": "知识图谱分析", "summary": f"解析 {len(graph['nodes'])} 个节点与 {len(graph['edges'])} 条证据关系", "evidence_ids": [n["id"] for n in graph["nodes"] if n["type"] in {"literature", "dataset"}]},
        {"id": "researcher", "status": "completed", "title": "研究员", "summary": f"运行 {len(comparison['methods'])} 种图谱方法与 {len(report['experiments'])} 项实验", "evidence_ids": [m["id"] for m in comparison["methods"]]},
        {"id": "reviewer", "status": "completed", "title": "结果审核员", "summary": f"方法共识 {comparison['review']['consensus']}；不可检验 {comparison['review']['not_testable']} 项；失败假设 {failed} 项", "evidence_ids": [x["citation_id"] for x in report["citation_audit"]]},
        {"id": "reporter", "status": "completed", "title": "报告输入员", "summary": "写入结论、边界、局限与复现成本", "evidence_ids": ["CONCLUSION", *[f"LIMIT-{i}" for i, _ in enumerate(report["limitations"], 1)]]},
    ]
    return {"prompt": prompt, "roles": ROLE_META, "stages": stages, "status": "completed", "output": {"title": report["title"], "conclusion": report["conclusion"], "failed_hypotheses": report["failed_hypotheses"], "reproduction_cost": report["reproduction_cost"]}}
