import json
import unittest
from unittest.mock import Mock, patch

from ai4s_style_drift.graph import run_demo
from ai4s_style_drift.server import analysis_payload
from ai4s_style_drift.public_data import load_public_fund, parse_manager_history
from ai4s_style_drift.research import run_autonomous_research, _narrative_evidence_experiment
from ai4s_style_drift.data import make_demo_data
from ai4s_style_drift.methods import compare_methods
from ai4s_style_drift.tools import industry_residual_analysis
from ai4s_style_drift.research_workflow import discover_research_directions, execute_confirmed_research
from ai4s_style_drift.deepseek_harness import (
    configure_deepseek,
    generate_deepseek_report,
    get_deepseek_config,
)


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
        self.assertEqual(len(report["gaps"]), 4)
        self.assertEqual(len(report["experiments"]), 6)
        self.assertEqual(len(report["experiments"][0]["result"]), 3)
        self.assertEqual(len(report["citation_audit"]), 3)
        self.assertTrue(all(x["doi_format_valid"] for x in report["citation_audit"]))
        self.assertEqual(len(report["evidence_bindings"]), 6)
        self.assertEqual(report["version"]["data"]["dataset_version"], "eastmoney-public-v1")
        self.assertIn("metrics", report["experiments"][2]["result"]["fixed_baseline"])
        self.assertTrue(any(h["status"] in {"failed", "not_tested"} for h in report["hypotheses"]))

    def test_knowledge_graph_is_complete_and_json_ready(self):
        report = run_autonomous_research("DEMO-TECH")["report"]
        graph = report["knowledge_graph"]
        node_ids = {node["id"] for node in graph["nodes"]}
        counts = {kind: sum(node["type"] == kind for node in graph["nodes"]) for kind in ("literature", "hypothesis", "experiment", "dataset", "conclusion")}
        self.assertGreaterEqual(counts["literature"], 3)
        self.assertGreaterEqual(counts["hypothesis"], 6)
        self.assertGreaterEqual(counts["experiment"], 6)
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

    def test_research_discovery_waits_for_confirmation(self):
        payload = discover_research_directions("DEMO-TECH", "寻找研究缺口")
        self.assertEqual(payload["phase"], "awaiting_confirmation")
        self.assertEqual(payload["harness"]["status"], "awaiting_confirmation")
        self.assertEqual(len(payload["directions"]), 4)
        self.assertNotIn("report", payload)
        self.assertTrue(any(stage["status"] == "waiting" for stage in payload["harness"]["stages"]))

    def test_confirmed_direction_generates_and_runs_scoped_program(self):
        payload = execute_confirmed_research("DEMO-TECH", "D2")
        report = payload["report"]
        self.assertEqual(payload["phase"], "completed")
        self.assertEqual(report["confirmed_direction"]["id"], "D2")
        self.assertEqual([item["id"] for item in report["experiments"]], ["E3"])
        self.assertEqual([item["id"] for item in report["hypotheses"]], ["H3"])
        self.assertEqual(len(report["generated_program"]["sha256"]), 64)
        self.assertIn("no arbitrary exec", report["generated_program"]["execution_policy"])
        self.assertEqual(len(report["execution_log"]), 5)

    def test_unknown_direction_is_rejected(self):
        with self.assertRaises(ValueError):
            execute_confirmed_research("DEMO-TECH", "UNKNOWN")

    def test_manager_history_parser_produces_event_dates(self):
        raw = """<table><tr><th>起始期</th><th>截止期</th><th>基金经理</th></tr>
        <tr><td>2025-04-23</td><td>至今</td><td>邓童</td></tr></table>""".encode()
        frame = parse_manager_history(raw)
        self.assertEqual(str(frame.iloc[0]["start_date"].date()), "2025-04-23")
        self.assertEqual(frame.iloc[0]["manager"], "邓童")

    def test_unsourced_manager_communication_is_rejected(self):
        result = _narrative_evidence_experiment([], [{"title": "search result snippet"}])
        self.assertEqual(result["status"], "not_testable")
        self.assertEqual(result["verified_external_communications"], 0)
        self.assertEqual(result["rejected_or_missing_communications"], 1)

    def test_industry_residual_experiment_reports_oos_anomalies(self):
        returns, _, mandate = make_demo_data()
        result = industry_residual_analysis(returns["fund"], mandate["industry_returns"], z_threshold=1.5)
        self.assertEqual(result["status"], "completed")
        self.assertIn("rmse", result["metrics"])
        self.assertIn("anomaly_months", result)
        self.assertTrue(result["rolling_exposure_changes"])

    def test_manager_and_industry_directions_are_scoped(self):
        manager = execute_confirmed_research("DEMO-TECH", "D3")["report"]
        industry = execute_confirmed_research("DEMO-TECH", "D4")["report"]
        self.assertEqual([item["id"] for item in manager["experiments"]], ["E4", "E5"])
        self.assertEqual([item["id"] for item in manager["hypotheses"]], ["H4", "H5"])
        self.assertEqual([item["id"] for item in industry["experiments"]], ["E6"])
        self.assertEqual([item["id"] for item in industry["hypotheses"]], ["H6"])

    def test_deepseek_reporter_is_disabled_without_key(self):
        report = run_autonomous_research("DEMO-TECH")["report"]
        with patch.dict("os.environ", {"DEEPSEEK_API_KEY": ""}, clear=False):
            result = generate_deepseek_report(report, "write report")
        self.assertEqual(result["status"], "disabled")
        self.assertTrue(result["canonical_report_immutable"])
        self.assertEqual(len(result["request_fingerprint"]), 64)

    def test_frontend_deepseek_config_never_returns_key(self):
        configure_deepseek(api_key="secret-session-key", model="deepseek-chat")
        public = get_deepseek_config()
        self.assertTrue(public["configured"])
        self.assertEqual(public["key_source"], "session")
        self.assertNotIn("secret-session-key", json.dumps(public))
        configure_deepseek(clear_api_key=True)

    def test_deepseek_config_rejects_non_deepseek_endpoint(self):
        with self.assertRaises(ValueError):
            configure_deepseek(base_url="http://127.0.0.1:8000")

    @patch("ai4s_style_drift.deepseek_harness.requests.post")
    def test_deepseek_reporter_uses_audited_packet(self, post):
        response = Mock()
        response.raise_for_status.return_value = None
        response.json.return_value = {"choices": [{"message": {"content": "# 审计报告\n保留失败假设。"}}], "usage": {"total_tokens": 42}}
        post.return_value = response
        report = run_autonomous_research("DEMO-TECH")["report"]
        original = json.dumps(report["conclusion"], ensure_ascii=False, sort_keys=True)
        with patch.dict("os.environ", {"DEEPSEEK_API_KEY": "test-key", "DEEPSEEK_MODEL": "deepseek-chat"}, clear=False):
            result = generate_deepseek_report(report, "write report")
        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["usage"]["total_tokens"], 42)
        self.assertEqual(json.dumps(report["conclusion"], ensure_ascii=False, sort_keys=True), original)
        self.assertNotIn("test-key", json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    unittest.main()
