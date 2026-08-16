"""Optional DeepSeek reporter for the audited research harness.

The model receives an evidence-bounded report and can only produce prose. It
does not execute code and its response never overwrites canonical findings.
"""
from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
import json
import os
import re
from threading import RLock
from typing import Any
from urllib.parse import urlparse

import requests


DEFAULT_BASE_URL = "https://api.deepseek.com"
DEFAULT_MODEL = "deepseek-chat"
ALLOWED_BASE_HOSTS = {"api.deepseek.com"}
_CONFIG_LOCK = RLock()
_RUNTIME_CONFIG: dict[str, str | None] = {
    "api_key": None,
    "model": None,
    "base_url": None,
}


def _resolved_config() -> dict[str, str]:
    with _CONFIG_LOCK:
        api_key = _RUNTIME_CONFIG["api_key"]
        model = _RUNTIME_CONFIG["model"]
        base_url = _RUNTIME_CONFIG["base_url"]
    return {
        "api_key": api_key if api_key is not None else os.getenv("DEEPSEEK_API_KEY", "").strip(),
        "model": model or os.getenv("DEEPSEEK_MODEL", DEFAULT_MODEL).strip() or DEFAULT_MODEL,
        "base_url": (base_url or os.getenv("DEEPSEEK_BASE_URL", DEFAULT_BASE_URL)).rstrip("/"),
    }


def get_deepseek_config() -> dict[str, Any]:
    """Return public configuration metadata without exposing the API key."""
    config = _resolved_config()
    with _CONFIG_LOCK:
        runtime_key = _RUNTIME_CONFIG["api_key"]
    return {
        "provider": "deepseek",
        "configured": bool(config["api_key"]),
        "model": config["model"],
        "base_url": config["base_url"],
        "key_source": "session" if runtime_key else ("environment" if runtime_key is None and config["api_key"] else "none"),
        "storage": "process_memory",
        "canonical_report_immutable": True,
    }


def configure_deepseek(
    *,
    api_key: str | None = None,
    model: str | None = None,
    base_url: str | None = None,
    clear_api_key: bool = False,
) -> dict[str, Any]:
    """Update process-local settings. Secrets are never returned or persisted."""
    if model is not None and not re.fullmatch(r"[A-Za-z0-9._-]{1,80}", model.strip()):
        raise ValueError("Invalid DeepSeek model name")
    if base_url is not None:
        normalized_url = base_url.strip().rstrip("/")
        parsed = urlparse(normalized_url)
        if parsed.scheme != "https" or parsed.hostname not in ALLOWED_BASE_HOSTS or parsed.path not in {"", "/"}:
            raise ValueError("DeepSeek base URL must be https://api.deepseek.com")
    else:
        normalized_url = None
    with _CONFIG_LOCK:
        if clear_api_key:
            _RUNTIME_CONFIG["api_key"] = ""
        elif api_key is not None and api_key.strip():
            _RUNTIME_CONFIG["api_key"] = api_key.strip()
        if model is not None:
            _RUNTIME_CONFIG["model"] = model.strip()
        if normalized_url is not None:
            _RUNTIME_CONFIG["base_url"] = normalized_url
    return get_deepseek_config()


def test_deepseek_connection() -> dict[str, Any]:
    """Run a minimal authenticated completion to validate the active settings."""
    config = _resolved_config()
    public = get_deepseek_config()
    if not config["api_key"]:
        return {"status": "disabled", "reason": "API Key 尚未配置", **public}
    try:
        response = requests.post(
            f"{config['base_url']}/chat/completions",
            headers={
                "Authorization": f"Bearer {config['api_key']}",
                "Content-Type": "application/json",
            },
            json={
                "model": config["model"],
                "temperature": 0,
                "max_tokens": 4,
                "messages": [{"role": "user", "content": "Reply OK"}],
            },
            timeout=30,
        )
        response.raise_for_status()
        payload = response.json()
        if not payload.get("choices"):
            raise ValueError("missing choices")
        return {"status": "connected", **public}
    except (requests.RequestException, ValueError) as exc:
        return {
            "status": "error",
            "reason": f"连接失败：{type(exc).__name__}",
            **public,
        }


def _evidence_packet(report: dict[str, Any]) -> dict[str, Any]:
    return {
        "title": report.get("title"),
        "research_question": report.get("research_question"),
        "hypotheses": report.get("hypotheses", []),
        "gaps": report.get("gaps", []),
        "experiments": report.get("experiments", []),
        "evidence_bindings": report.get("evidence_bindings", []),
        "conclusion": report.get("conclusion"),
        "limitations": report.get("limitations", []),
        "data_audit": report.get("data_audit", []),
        "citation_audit": report.get("citation_audit", []),
    }


def generate_deepseek_report(report: dict[str, Any], prompt: str = "") -> dict[str, Any]:
    """Generate an optional narrative report, or return an explicit disabled state."""
    config = _resolved_config()
    api_key = config["api_key"]
    model = config["model"]
    base_url = config["base_url"]
    packet = _evidence_packet(report)
    packet_json = json.dumps(packet, ensure_ascii=False, separators=(",", ":"))
    request_fingerprint = sha256(packet_json.encode("utf-8")).hexdigest()
    metadata = {
        "provider": "deepseek",
        "model": model,
        "request_fingerprint": request_fingerprint,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "canonical_report_immutable": True,
    }
    if not api_key:
        return {
            "status": "disabled",
            "reason": "DEEPSEEK_API_KEY is not configured",
            **metadata,
        }

    system = (
        "你是基金风格漂移研究报告员。只能依据用户提供的证据包写作，"
        "不能新增数据、引用或因果结论。必须保留 supported、failed、not_tested "
        "状态和所有局限。输出 Markdown，包含：摘要、证据与发现、失败或未检验假设、"
        "基金经理与行业信号、稳健性、复现成本、研究边界。明确区分描述性证据和因果结论。"
    )
    user = (
        f"研究任务：{prompt or '生成审计版基金风格漂移实验报告'}\n"
        f"证据包（不可修改）：\n{packet_json}"
    )
    try:
        response = requests.post(
            f"{base_url}/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": model,
                "temperature": 0.1,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
            },
            timeout=60,
        )
        response.raise_for_status()
        payload = response.json()
        content = (((payload.get("choices") or [{}])[0]).get("message") or {}).get("content")
        if not isinstance(content, str) or not content.strip():
            return {"status": "error", "reason": "DeepSeek returned no text", **metadata}
        usage = payload.get("usage") or {}
        return {
            "status": "completed",
            "content": content.strip(),
            "usage": {
                key: usage.get(key)
                for key in ("prompt_tokens", "completion_tokens", "total_tokens")
                if key in usage
            },
            "response_sha256": sha256(content.encode("utf-8")).hexdigest(),
            **metadata,
        }
    except (requests.RequestException, ValueError) as exc:
        return {
            "status": "error",
            "reason": f"DeepSeek request failed: {type(exc).__name__}",
            **metadata,
        }


def attach_deepseek_report(report: dict[str, Any], prompt: str = "") -> dict[str, Any]:
    report["deepseek_report"] = generate_deepseek_report(report, prompt)
    return report
