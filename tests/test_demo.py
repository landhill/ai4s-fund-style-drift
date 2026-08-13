import json
import unittest

from ai4s_style_drift.graph import run_demo
from ai4s_style_drift.server import analysis_payload
from ai4s_style_drift.public_data import load_public_fund
from ai4s_style_drift.research import run_autonomous_research
from ai4s_style_drift.data import make_demo_data
from ai4s_style_drift.methods import compare_methods


class StyleDriftDemoTest(unittest.TestCase):
    def test_pipeline_detects_synthetic_drift(self):
        result = run_demo()
        report = json.loads(result["report"])
        self.assertTrue(report["change_points"])
        self.assertTrue(report["robustness"]["positive_drift"])
        self.assertGreater(report["distance"]["post"], report["distance"]["pre"])
        self.assertGreater(report["mean_exposure_post"]["momentum"], report["mean_exposure_pre"]["momentum"])

    def test_dashboard_payload_is_json_ready(self):
        payload = analysis_payload()
        json.dumps(payload, ensure_ascii=False)
        self.assertEqual(payload["meta"]["engine"], "LangGraph")
        self.assertEqual(payload["meta"]["data_source"], "eastmoney_public")
        self.assertEqual(payload["meta"]["fund_id"], "159552")
        self.assertGreater(len(payload["exposure"]), 10)
        self.assertEqual(len(payload["nodes"]), 5)

    def test_requested_fund_is_preserved(self):
        payload = analysis_payload("588000")
        self.assertEqual(payload["meta"]["fund_id"], "588000")
        self.assertEqual(payload["meta"]["data_source"], "eastmoney_public")

    def test_real_data_audit_separates_observed_derived_and_missing(self):
        _, _, mandate = load_public_fund("159552")
        kinds = {item["kind"] for item in mandate["data_audit"]}
        self.assertTrue({"observed", "derived_from_observed", "assumption", "missing"} <= kinds)
        observed = [item for item in mandate["data_audit"] if item["kind"] == "observed"]
        self.assertTrue(all(item["sha256"] and item["observations"] > 0 for item in observed))

    def test_autonomous_research_runs_experiments(self):
        payload = run_autonomous_research("588000")
        report = payload["report"]
        self.assertEqual(len(report["gaps"]), 3)
        self.assertEqual(len(report["experiments"]), 4)
        self.assertEqual(len(report["experiments"][0]["result"]), 3)
        self.assertEqual(len(report["citation_audit"]), 3)
        self.assertTrue(all(x["doi_format_valid"] for x in report["citation_audit"]))
        self.assertEqual(len(report["evidence_bindings"]), 4)
        self.assertEqual(report["version"]["data"]["dataset_version"], "eastmoney-public-v1")
        self.assertIn("metrics", report["experiments"][2]["result"]["fixed_baseline"])
        self.assertTrue(any(h["status"] in {"failed", "not_tested"} for h in report["hypotheses"]))

    def test_knowledge_graph_is_complete_and_json_ready(self):
        report = run_autonomous_research("DEMO-TECH")["report"]
        graph = report["knowledge_graph"]
        node_ids = {node["id"] for node in graph["nodes"]}
        counts = {kind: sum(node["type"] == kind for node in graph["nodes"]) for kind in ("literature", "hypothesis", "experiment", "dataset", "conclusion")}
        self.assertGreaterEqual(counts["literature"], 3)
        self.assertGreaterEqual(counts["hypothesis"], 4)
        self.assertGreaterEqual(counts["experiment"], 4)
        self.assertGreaterEqual(counts["dataset"], 4)
        self.assertEqual(counts["conclusion"], 1)
        self.assertTrue(all(edge["source"] in node_ids and edge["target"] in node_ids for edge in graph["edges"]))
        evidence_ids = {evidence_id for hypothesis in report["hypotheses"] for evidence_id in hypothesis["evidence_ids"]}
        self.assertTrue(evidence_ids <= node_ids)
        self.assertEqual(graph["meta"]["data_version"], report["version"]["data"]["dataset_version"])
        json.dumps(graph, ensure_ascii=False)

    def test_harness_state_has_four_auditable_roles(self):
        report = run_autonomous_research("DEMO-TECH")["report"]
        harness = report["harness"]
        self.assertEqual(harness["status"], "completed")
        self.assertEqual(set(harness["roles"]), {"knowledge_graph", "researcher", "reviewer", "reporter"})
        self.assertEqual(len(harness["stages"]), 4)
        self.assertTrue(all(stage["evidence_ids"] for stage in harness["stages"]))

    def test_selected_graph_methods_are_compared(self):
        report = run_autonomous_research("DEMO-TECH", ["RBSA-6", "RBSA-18"])["report"]
        comparison = report["method_comparison"]
        self.assertEqual([item["id"] for item in comparison["methods"]], ["RBSA-6", "RBSA-18"])
        self.assertEqual(comparison["review"]["completed"], 2)
        graph_ids = {node["id"] for node in report["knowledge_graph"]["nodes"]}
        self.assertTrue({"RBSA-6", "RBSA-18"} <= graph_ids)

    def test_unknown_graph_method_is_rejected(self):
        returns, holdings, mandate = make_demo_data()
        with self.assertRaises(ValueError):
            compare_methods(returns, holdings, mandate["target"], ["UNKNOWN"])


if __name__ == "__main__":
    unittest.main()
