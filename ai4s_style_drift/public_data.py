from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from hashlib import sha256
from io import BytesIO, StringIO
from pathlib import Path
import json
import re
import time

import numpy as np
import pandas as pd
import requests


CACHE_DIR = Path(__file__).resolve().parents[1] / ".cache" / "public_fund_data"
NAV_URL = "https://api.fund.eastmoney.com/f10/lsjz"
ARCHIVE_URL = "https://fundf10.eastmoney.com/FundArchivesDatas.aspx"
KLINE_URL = "https://push2his.eastmoney.com/api/qt/stock/kline/get"
NOTICE_URL = "https://api.fund.eastmoney.com/f10/JJGG"
HEADERS = {"User-Agent": "Mozilla/5.0", "Referer": "https://fundf10.eastmoney.com/"}
PROXIES = {"market": "510300", "size": "510500", "growth": "159915", "value_lowvol": "512890", "tech": "512760"}
INDUSTRY_PROXIES = {
    "semiconductor": "512480", "new_energy": "515030", "defense": "512660",
    "healthcare": "512170", "bank": "512800", "real_estate": "512200",
}


class PublicDataError(RuntimeError):
    pass


def _cache_get(url: str, params: dict, key: str, refresh: bool = False) -> tuple[bytes, dict]:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    raw_path, meta_path = CACHE_DIR / f"{key}.raw", CACHE_DIR / f"{key}.json"
    if raw_path.exists() and meta_path.exists() and not refresh:
        return raw_path.read_bytes(), json.loads(meta_path.read_text(encoding="utf-8"))
    error = None
    for attempt in range(3):
        try:
            response = requests.get(url, params=params, headers=HEADERS, timeout=30)
            response.raise_for_status(); break
        except requests.RequestException as exc:
            error = exc
            if attempt == 2:
                raise PublicDataError(f"Public endpoint unavailable after 3 attempts: {url}") from error
            time.sleep(0.8 * (attempt + 1))
    raw = response.content
    meta = {"url": response.url, "fetched_at": datetime.now(timezone.utc).isoformat(), "sha256": sha256(raw).hexdigest(), "bytes": len(raw)}
    raw_path.write_bytes(raw); meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    return raw, meta


def fetch_nav(code: str, refresh: bool = False) -> tuple[pd.DataFrame, dict]:
    page_size = 100
    params = {"fundCode": code, "pageIndex": 1, "pageSize": page_size, "startDate": "2024-01-01"}
    raw, first_meta = _cache_get(NAV_URL, params, f"nav24_{code}_p1", refresh)
    payload = json.loads(raw.decode("utf-8-sig"))
    if payload.get("ErrCode") != 0:
        raise PublicDataError(f"NAV endpoint error for {code}: {payload.get('ErrMsg')}")
    rows = list((payload.get("Data") or {}).get("LSJZList", []))
    actual_page_size = int(payload.get("PageSize") or len(rows) or page_size)
    page_count = int(np.ceil(payload.get("TotalCount", len(rows)) / actual_page_size))
    metas = [first_meta]
    for page in range(2, page_count + 1):
        page_raw, page_meta = _cache_get(NAV_URL, {**params, "pageIndex": page}, f"nav24_{code}_p{page}", refresh)
        page_payload = json.loads(page_raw.decode("utf-8-sig"))
        rows.extend((page_payload.get("Data") or {}).get("LSJZList", [])); metas.append(page_meta)
    if not rows:
        raise PublicDataError(f"No public NAV records for fund {code}")
    frame = pd.DataFrame(rows)
    frame["date"] = pd.to_datetime(frame["FSRQ"])
    frame["nav"] = pd.to_numeric(frame["DWJZ"], errors="coerce")
    frame["daily_return"] = pd.to_numeric(frame["JZZZL"], errors="coerce") / 100
    combined_meta = {"pages": len(metas), "bytes": sum(x["bytes"] for x in metas), "sha256": sha256("".join(x["sha256"] for x in metas).encode()).hexdigest(), "fetched_at": max(x["fetched_at"] for x in metas), "url": first_meta["url"]}
    return frame[["date", "nav", "daily_return"]].dropna(subset=["date", "nav"]).sort_values("date").set_index("date"), combined_meta


def fetch_exchange_monthly(code: str, refresh: bool = False) -> tuple[pd.Series, dict]:
    market = "1" if code.startswith("5") else "0"
    params = {"secid": f"{market}.{code}", "klt": 103, "fqt": 1, "lmt": 1000, "end": 20500101, "fields1": "f1,f2,f3,f4,f5,f6,f7,f8", "fields2": "f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61"}
    raw, meta = _cache_get(KLINE_URL, params, f"monthly_{code}", refresh)
    payload = json.loads(raw.decode("utf-8-sig"))
    data = payload.get("data") or {}
    klines = data.get("klines") or []
    if not klines:
        raise PublicDataError(f"No public exchange price records for {code}")
    frame = pd.DataFrame([row.split(",") for row in klines], columns=["date", "open", "close", "high", "low", "volume", "amount", "amplitude", "pct", "change", "turnover"])
    frame["date"] = pd.to_datetime(frame["date"]); frame["close"] = pd.to_numeric(frame["close"], errors="coerce")
    series = frame.dropna(subset=["close"]).set_index("date")["close"].pct_change().rename(code)
    series.index = series.index.to_period("M").to_timestamp("M")
    return series, {**meta, "instrument_name": data.get("name"), "source_type": "exchange_adjusted_monthly_price"}


def parse_manager_history(raw: bytes) -> pd.DataFrame:
    """Parse the public manager tenure table into a stable event schema."""
    for table in pd.read_html(StringIO(raw.decode("utf-8", errors="replace"))):
        columns = [str(column) for column in table.columns]
        if {"起始期", "截止期", "基金经理"} <= set(columns):
            frame = table.rename(columns={"起始期": "start_date", "截止期": "end_date", "基金经理": "manager"})
            frame["start_date"] = pd.to_datetime(frame["start_date"], errors="coerce")
            frame["end_date"] = pd.to_datetime(frame["end_date"].replace("至今", pd.NaT), errors="coerce")
            frame["manager"] = frame["manager"].astype(str).str.strip()
            return frame[["start_date", "end_date", "manager"]].dropna(subset=["start_date", "manager"])
    raise PublicDataError("Manager tenure table not found")


def fetch_manager_history(code: str, refresh: bool = False) -> tuple[pd.DataFrame, dict]:
    url = f"https://fundf10.eastmoney.com/jjjl_{code}.html"
    raw, meta = _cache_get(url, {}, f"manager_{code}", refresh)
    return parse_manager_history(raw), {**meta, "source_type": "manager_tenure_html"}


def fetch_report_metadata(code: str, refresh: bool = False) -> tuple[list[dict], dict]:
    params = {"fundcode": code, "pageIndex": 1, "pageSize": 20, "type": 3}
    raw, meta = _cache_get(NOTICE_URL, params, f"reports_{code}", refresh)
    payload = json.loads(raw.decode("utf-8-sig"))
    if payload.get("ErrCode") != 0:
        raise PublicDataError(f"Notice endpoint error for {code}: {payload.get('ErrMsg')}")
    records = []
    for item in payload.get("Data") or []:
        notice_id = str(item.get("ID") or "")
        if not notice_id:
            continue
        records.append({
            "id": notice_id,
            "title": item.get("TITLE"),
            "published_date": item.get("PUBLISHDATEDesc"),
            "source_url": f"https://fund.eastmoney.com/gonggao/{code},{notice_id}.html",
            "document_url": f"https://pdf.dfcfw.com/pdf/H2_{notice_id}_1.pdf",
            "text_status": "metadata_only",
            "source_sha256": meta["sha256"],
        })
    return records, {**meta, "source_type": "periodic_report_metadata", "total_count": payload.get("TotalCount", len(records))}


def extract_report_narratives(reports: list[dict], refresh: bool = False, limit: int = 4) -> tuple[list[dict], dict]:
    """Extract the manager-operation section from source PDFs; failures remain explicit."""
    try:
        from pypdf import PdfReader
    except ImportError:
        return reports, {"status": "not_testable", "reason": "pypdf is not installed", "documents": 0, "sha256": None}
    document_hashes = []
    extracted = 0
    for report in reports[:limit]:
        try:
            raw, meta = _cache_get(report["document_url"], {}, f"report_{report['id']}", refresh)
            text = "\n".join(page.extract_text() or "" for page in PdfReader(BytesIO(raw)).pages)
            text = re.sub(r"[ \t\r]+", " ", text)
            match = re.search(r"报告期内基金投资策略和运作分析\s*(.*?)(?:报告期内基金的业绩表现|基金投资组合报告|§\s*5)", text, re.S)
            report["document_sha256"] = meta["sha256"]
            document_hashes.append(meta["sha256"])
            if match:
                narrative = re.sub(r"\s+", " ", match.group(1)).strip()[:3000]
                report["narrative"] = narrative
                report["text_status"] = "extracted"
                report["source_sha256"] = meta["sha256"]
                extracted += 1
            else:
                report["text_status"] = "section_not_found"
        except (PublicDataError, OSError, ValueError) as exc:
            report["text_status"] = "extract_failed"
            report["text_error"] = type(exc).__name__
    return reports, {
        "status": "completed" if extracted else "not_testable",
        "documents": min(limit, len(reports)),
        "extracted": extracted,
        "sha256": sha256("".join(document_hashes).encode()).hexdigest() if document_hashes else None,
    }


def load_industry_benchmarks(refresh: bool = False) -> tuple[pd.DataFrame, dict]:
    def load_one(item: tuple[str, str]) -> tuple[pd.Series, dict]:
        _, code = item
        nav, meta = fetch_nav(code, refresh)
        return _monthly_return(nav).rename(code), {**meta, "source_type": "industry_etf_nav"}

    with ThreadPoolExecutor(max_workers=3) as pool:
        loaded = dict(zip(INDUSTRY_PROXIES, pool.map(load_one, INDUSTRY_PROXIES.items())))
    frame = pd.concat({name: value[0] for name, value in loaded.items()}, axis=1).sort_index()
    meta = {
        "source_type": "industry_etf_nav_monthly_returns",
        "instruments": INDUSTRY_PROXIES,
        "sha256": sha256("".join(value[1]["sha256"] for value in loaded.values()).encode()).hexdigest(),
        "sources": {name: value[1] for name, value in loaded.items()},
    }
    return frame, meta


def _embedded_html(raw: bytes) -> str:
    text = raw.decode("utf-8", errors="replace")
    match = re.search(r"content:\"(.*)\",(?:arryear|arryear|curyear|data)", text, re.S)
    if not match:
        match = re.search(r"content:\"(.*)\"\s*[,}]", text, re.S)
    if not match:
        raise PublicDataError("Unable to locate embedded archive HTML")
    return match.group(1).replace(r'\"', '"').replace(r"\/", "/")


def fetch_holdings(code: str, year: int | None = None, refresh: bool = False) -> tuple[pd.DataFrame, dict]:
    year = year or datetime.now().year
    params = {"type": "jjcc", "code": code, "topline": 10, "year": year, "month": "12,9,6,3"}
    raw, meta = _cache_get(ARCHIVE_URL, params, f"holdings_{code}_{year}", refresh)
    html = _embedded_html(raw)
    tables = pd.read_html(StringIO(html))
    normalized = []
    for quarter, table in enumerate(tables, 1):
        table.columns = ["_".join(str(x) for x in col if str(x) != "nan") if isinstance(col, tuple) else str(col) for col in table.columns]
        table["source_table"] = quarter
        normalized.append(table)
    return (pd.concat(normalized, ignore_index=True) if normalized else pd.DataFrame()), meta


def fetch_scale(code: str, refresh: bool = False) -> tuple[pd.DataFrame, dict]:
    raw, meta = _cache_get(ARCHIVE_URL, {"type": "gmbd", "code": code}, f"scale_{code}", refresh)
    tables = pd.read_html(StringIO(_embedded_html(raw)))
    frame = tables[0] if tables else pd.DataFrame()
    frame.columns = ["_".join(str(x) for x in col if str(x) != "nan") if isinstance(col, tuple) else str(col) for col in frame.columns]
    return frame, meta


def _monthly_return(nav: pd.DataFrame) -> pd.Series:
    return nav["nav"].resample("ME").last().pct_change()


def load_public_fund(code: str, refresh: bool = False) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    codes = {"fund": code, **PROXIES}
    def load_series(item):
        name, item_code = item
        nav, meta = fetch_nav(item_code, refresh)
        return _monthly_return(nav), {**meta, "source_type": "fund_nav", "raw_observations": len(nav), "actual_start": str(nav.index.min().date()), "actual_end": str(nav.index.max().date())}
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = dict(zip(codes, pool.map(load_series, codes.items())))
    monthly = {name: result[0] for name, result in results.items()}
    aligned = pd.concat(monthly, axis=1, sort=True).dropna()
    if len(aligned) < 24:
        raise PublicDataError(f"Only {len(aligned)} aligned monthly observations; at least 24 required")
    market = aligned["market"]
    returns = pd.DataFrame({
        "fund": aligned["fund"], "rf": 0.0, "market": market,
        "size_factor": aligned["size"] - market,
        "value_factor": aligned["value_lowvol"] - aligned["growth"],
        "momentum_factor": market.rolling(12, min_periods=6).sum().shift(1).fillna(0) * market,
        "quality_factor": aligned["value_lowvol"] - market,
        "tech_factor": aligned["tech"] - market,
    }).dropna()
    holdings, holdings_meta = fetch_holdings(code, refresh=refresh)
    scale, scale_meta = fetch_scale(code, refresh=refresh)
    try:
        managers, manager_meta = fetch_manager_history(code, refresh=refresh)
    except PublicDataError as exc:
        managers, manager_meta = pd.DataFrame(columns=["start_date", "end_date", "manager"]), {"status": "missing", "reason": str(exc), "sha256": None}
    try:
        reports, report_meta = fetch_report_metadata(code, refresh=refresh)
        reports, narrative_meta = extract_report_narratives(reports, refresh=refresh)
        report_meta = {**report_meta, "narrative_extraction": narrative_meta}
    except PublicDataError as exc:
        reports, narrative_meta = [], {"status": "missing", "reason": str(exc), "sha256": None}
        report_meta = {**narrative_meta, "narrative_extraction": narrative_meta}
    try:
        industry_returns, industry_meta = load_industry_benchmarks(refresh=refresh)
    except PublicDataError as exc:
        industry_returns, industry_meta = pd.DataFrame(), {"status": "missing", "reason": str(exc), "sha256": None, "instruments": INDUSTRY_PROXIES}
    raw_meta = {name: result[1] for name, result in results.items()}
    data_audit = [
        {"id": "FUND_NAV", "kind": "observed", "source": "东方财富基金历史净值", "instrument": code, "observations": raw_meta["fund"]["raw_observations"], "start": raw_meta["fund"]["actual_start"], "end": raw_meta["fund"]["actual_end"], "analysis_frequency": "monthly", "analysis_observations": int(aligned["fund"].notna().sum()), "sha256": raw_meta["fund"]["sha256"]},
        {"id": "HOLDINGS", "kind": "observed", "source": "东方财富基金季度持仓披露", "instrument": code, "observations": len(holdings), "sha256": holdings_meta["sha256"]},
        {"id": "SCALE", "kind": "observed", "source": "东方财富基金规模变动表", "instrument": code, "observations": len(scale), "sha256": scale_meta["sha256"]},
        {"id": "FACTOR_PROXIES", "kind": "derived_from_observed", "source": "真实 ETF 净值构造的市场/规模/价值/科技代理因子", "instrument": ",".join(PROXIES.values()), "observations": len(returns), "start": str(returns.index.min().to_period("M")), "end": str(returns.index.max().to_period("M")), "sha256": sha256("".join(raw_meta[name]["sha256"] for name in PROXIES).encode()).hexdigest()},
        {"id": "RISK_FREE", "kind": "assumption", "source": "月度无风险利率暂设为 0", "instrument": "N/A", "observations": len(returns), "sha256": None},
        {"id": "FLOW", "kind": "missing", "source": "尚未连接可复现的真实资金流序列", "instrument": code, "observations": 0, "sha256": None},
        {"id": "MANAGER", "kind": "observed" if len(managers) else "missing", "source": "东方财富基金经理任职履历", "instrument": code, "observations": len(managers), "sha256": manager_meta.get("sha256")},
        {"id": "REPORTS", "kind": "observed" if len(reports) else "missing", "source": "东方财富定期报告公告与 PDF 原文", "instrument": code, "observations": len(reports), "sha256": narrative_meta.get("sha256") or report_meta.get("sha256")},
        {"id": "COMMUNICATIONS", "kind": "missing", "source": "外部宣讲须提供发布日期、原文 URL 与原文指纹；当前未接入", "instrument": code, "observations": 0, "sha256": None},
        {"id": "INDUSTRY", "kind": "derived_from_observed" if not industry_returns.empty else "missing", "source": "公开行业 ETF 净值月收益代理", "instrument": ",".join(INDUSTRY_PROXIES.values()), "observations": int(industry_returns.notna().any(axis=1).sum()) if not industry_returns.empty else 0, "sha256": industry_meta.get("sha256")},
    ]
    mandate = {
        "fund_id": code, "declared_style": "public-data fund; contract parser pending",
        "target": pd.Series([1.0, 0.0, 0.0, 0.0, 0.0, 0.0], index=["market", "size", "value", "momentum", "quality", "tech"]),
        "benchmark": "510300 proxy; replace with prospectus benchmark",
        "evidence": "Eastmoney public NAV/archives; unofficial endpoint",
        "data_source": "eastmoney_public", "factor_model": "public ETF proxy factors v1",
        "fund_structure": ("exchange_traded_fund_candidate" if code.startswith(("1", "5")) else "open_end_fund"),
        "source_meta": {"nav": raw_meta, "holdings": holdings_meta, "scale": scale_meta, "manager": manager_meta, "reports": report_meta, "industry": industry_meta},
        "scale_records": scale.to_dict("records"),
        "manager_history": managers.to_dict("records"),
        "periodic_reports": reports,
        "manager_communications": [],
        "industry_returns": industry_returns,
        "data_audit": data_audit,
    }
    return returns, holdings, mandate
