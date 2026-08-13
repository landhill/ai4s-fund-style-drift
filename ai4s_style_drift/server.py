from __future__ import annotations

import argparse
import json
import mimetypes
import re
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from .graph import HAS_LANGGRAPH, run_demo
from .research import run_autonomous_research
from .research_workflow import discover_research_directions, execute_confirmed_research


STATIC_DIR = Path(__file__).with_name("static")


def analysis_payload(fund_id: str = "159552") -> dict:
    state = run_demo(fund_id)
    exposure = state["exposure"].reset_index()
    distance = state["distance"]
    holdings = state["holdings"].reset_index()
    report = json.loads(state["report"])
    start_date, end_date = state["returns"].index.min(), state["returns"].index.max()
    return {
        "meta": {
            "engine": "LangGraph" if HAS_LANGGRAPH else "Local fallback",
            "graph": "contract → style → change point → attribution → robustness → report",
            "dataset": (f"{state['mandate']['fund_id']} · Eastmoney public data" if state["mandate"].get("data_source") == "eastmoney_public" else f"{state['mandate']['fund_id']} · synthetic A-share fund profile"),
            "fund_id": state["mandate"]["fund_id"],
            "data_source": state["mandate"].get("data_source", "synthetic"),
            "factor_model": state["mandate"].get("factor_model", "unknown"),
            "period": f"{start_date:%Y-%m} to {end_date:%Y-%m}",
            "generated_at": (state["mandate"].get("source_meta", {}).get("nav", {}).get("fund", {}).get("fetched_at", str(exposure["date"].max().date()))),
        },
        "report": report,
        "exposure": [
            {"date": str(row.pop("date").date()), **{key: round(float(value), 4) for key, value in row.items()}}
            for row in exposure.to_dict("records")
        ],
        "distance": [{"date": str(date.date()), "value": round(float(value), 4)} for date, value in distance.items()],
        "holdings": json.loads(holdings.to_json(orient="records", date_format="iso", force_ascii=False)),
        "nodes": [
            {"id": "contract", "label": "契约解析", "detail": "提取目标风格与基准"},
            {"id": "style", "label": "风格测量", "detail": "12 月滚动因子回归"},
            {"id": "change", "label": "变化点检测", "detail": "持续性水平变化扫描"},
            {"id": "attribution", "label": "漂移归因", "detail": "持仓与因子证据交叉验证"},
            {"id": "robustness", "label": "稳健性审查", "detail": "前后期距离与方向复核"},
        ],
    }


class Handler(BaseHTTPRequestHandler):
    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path not in {"/api/harness", "/api/research/discover", "/api/research/execute"}:
            self._send(404, "text/plain; charset=utf-8", b"Not found")
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            payload = json.loads(self.rfile.read(length) or b"{}")
            fund_id = str(payload.get("fund_id") or "159552").strip()
            if not re.fullmatch(r"\d{6}", fund_id):
                raise ValueError("请输入六位真实 A 股基金代码；自主研究不再使用合成数据回退")
            prompt = str(payload.get("prompt") or "")
            methods = payload.get("methods")
            if methods is not None and not isinstance(methods, list):
                raise ValueError("methods must be a list")
            if parsed.path == "/api/research/discover":
                result = discover_research_directions(fund_id, prompt)
            elif parsed.path == "/api/research/execute":
                direction_id = str(payload.get("direction_id") or "").strip()
                if not direction_id:
                    raise ValueError("请先确认一个研究方向")
                result = execute_confirmed_research(fund_id, direction_id, prompt, methods)
            else:
                result = run_autonomous_research(fund_id, methods)
                result["report"]["harness"] = __import__("ai4s_style_drift.harness", fromlist=["build_harness_state"]).build_harness_state(result["report"], prompt)
            self._send(200, "application/json; charset=utf-8", json.dumps(result, ensure_ascii=False).encode("utf-8"))
        except Exception as exc:
            self._send(500, "application/json; charset=utf-8", json.dumps({"error": str(exc)}, ensure_ascii=False).encode("utf-8"))

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path
        query = parse_qs(parsed.query)
        fund_id = query.get("fund_id", ["159552"])[0].strip()
        if path == "/api/analysis":
            try:
                if not re.fullmatch(r"\d{6}", fund_id):
                    raise ValueError("请输入六位真实 A 股基金代码；页面接口不再使用合成数据回退")
                body = json.dumps(analysis_payload(fund_id), ensure_ascii=False).encode("utf-8")
                self._send(200, "application/json; charset=utf-8", body)
            except Exception as exc:
                body = json.dumps({"error": str(exc)}, ensure_ascii=False).encode("utf-8")
                self._send(500, "application/json; charset=utf-8", body)
            return
        if path == "/api/research":
            try:
                if not re.fullmatch(r"\d{6}", fund_id):
                    raise ValueError("请输入六位真实 A 股基金代码；自主研究不再使用合成数据回退")
                body = json.dumps(run_autonomous_research(fund_id), ensure_ascii=False).encode("utf-8")
                self._send(200, "application/json; charset=utf-8", body)
            except Exception as exc:
                body = json.dumps({"error": str(exc)}, ensure_ascii=False).encode("utf-8")
                self._send(500, "application/json; charset=utf-8", body)
            return
        requested = "index.html" if path == "/" else path.lstrip("/")
        file_path = (STATIC_DIR / requested).resolve()
        if STATIC_DIR.resolve() not in file_path.parents or not file_path.is_file():
            self._send(404, "text/plain; charset=utf-8", "Not found".encode())
            return
        content_type = mimetypes.guess_type(file_path.name)[0] or "application/octet-stream"
        self._send(200, content_type, file_path.read_bytes())

    def _send(self, status: int, content_type: str, body: bytes) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt: str, *args) -> None:
        print(f"[web] {self.address_string()} {fmt % args}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Style-drift research dashboard")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    server = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"Dashboard: http://{args.host}:{args.port}")
    server.serve_forever()


if __name__ == "__main__":
    main()
