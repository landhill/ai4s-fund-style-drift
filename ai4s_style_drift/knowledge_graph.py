from __future__ import annotations

from typing import Any


def build_knowledge_graph(report: dict[str, Any], fund_id: str) -> dict[str, Any]:
    """Build an auditable graph from the canonical research report."""
    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, str]] = []

    def add_node(node_id: str, node_type: str, label: str, **details: Any) -> None:
        nodes.append({"id": node_id, "type": node_type, "label": label, "details": details})

    def add_edge(source: str, target: str, relation: str) -> None:
        edges.append({"source": source, "target": target, "relation": relation})

    for item in report["literature"]:
        citation_id = item["citation_id"]
        add_node(
            citation_id,
            "literature",
            item["title"],
            authors=item["authors"],
            year=item["year"],
            doi=item["doi"],
            evidence_id=citation_id,
        )
        for kind, label, relation in (
            ("measure", "测度", "defines"),
            ("mechanism", "机制", "proposes"),
            ("limitation", "局限", "limits"),
        ):
            node_id = f"{citation_id}-{kind.upper()}"
            add_node(node_id, kind, f"{label} · {item['extracted'][kind]}", citation_id=citation_id)
            add_edge(citation_id, node_id, relation)

    for gap in report["gaps"]:
        add_node(gap["id"], "gap", gap["gap"], priority=gap["priority"], evidence_ids=gap["literature_ids"])
        for citation_id in gap["literature_ids"]:
            add_edge(citation_id, gap["id"], "supports")

    for hypothesis in report["hypotheses"]:
        add_node(
            hypothesis["id"],
            "hypothesis",
            hypothesis["statement"],
            status=hypothesis["status"],
            evidence_ids=hypothesis["evidence_ids"],
            registered_before_test=hypothesis["registered_before_test"],
        )

    gap_hypothesis = {"G1": ["H1", "H2"], "G2": ["H3"], "G3": ["H4"]}
    for gap_id, hypothesis_ids in gap_hypothesis.items():
        for hypothesis_id in hypothesis_ids:
            add_edge(gap_id, hypothesis_id, "motivates")

    for experiment in report["experiments"]:
        add_node(
            experiment["id"],
            "experiment",
            experiment["question"],
            method=experiment["method"],
            result=experiment["result"],
            evidence_id=experiment["id"],
        )
    experiment_hypothesis = {"E1": ["H1", "H2"], "E3": ["H3"], "E4": ["H4"]}
    for experiment_id, hypothesis_ids in experiment_hypothesis.items():
        for hypothesis_id in hypothesis_ids:
            add_edge(experiment_id, hypothesis_id, "tests")

    for method in report.get("method_comparison", {}).get("methods", []):
        add_node(method["id"], "method", method["label"], source_id=method["source_id"], data_ids=method["data"], limitation=method["limitation"], result=method["result"])
        add_edge(method["source_id"], method["id"], "defines")
        for data_id in method["data"]:
            add_edge(data_id, method["id"], "depends_on")
        add_edge(method["id"], "CONCLUSION", "informs")

    for dataset in report["data_manifest"]:
        node_id = f"DATA-{dataset['dataset_id']}"
        add_node(
            node_id,
            "dataset",
            f"{dataset['dataset_id']} · {dataset['source']}",
            status=dataset["status"],
            frequency=dataset["frequency"],
            version_rule=dataset["version_rule"],
            evidence_id=node_id,
        )
    data_experiment = {
        "DATA-NAV": ["E1", "E2", "E3"],
        "DATA-HOLDINGS": ["E4"],
        "DATA-FLOW": ["E4"],
        "DATA-FACTORS": ["E1", "E3"],
    }
    for data_id, experiment_ids in data_experiment.items():
        for experiment_id in experiment_ids:
            add_edge(data_id, experiment_id, "depends_on")

    add_node(
        "CONCLUSION",
        "conclusion",
        report["conclusion"]["interpretation"],
        claim_boundary=report["conclusion"]["claim_boundary"],
    )
    for hypothesis in report["hypotheses"]:
        add_edge(hypothesis["id"], "CONCLUSION", "supports" if hypothesis["status"] == "supported" else "limits")

    for index, limitation in enumerate(report["limitations"], start=1):
        node_id = f"LIMIT-{index}"
        add_node(node_id, "limitation", limitation)
        add_edge(node_id, "CONCLUSION", "limits")

    node_ids = {node["id"] for node in nodes}
    if any(edge["source"] not in node_ids or edge["target"] not in node_ids for edge in edges):
        raise ValueError("Knowledge graph contains a dangling edge")

    version = report["version"]
    return {
        "nodes": nodes,
        "edges": edges,
        "meta": {
            "fund_id": fund_id,
            "code_version": version["code"]["environment_version"],
            "data_version": version["data"]["dataset_version"],
            "schema_sha256": version["data"]["schema_sha256"],
        },
    }
