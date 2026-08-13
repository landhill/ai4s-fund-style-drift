from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from hashlib import sha256
from io import StringIO
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
HEADERS = {"User-Agent": "Mozilla/5.0", "Referer": "https://fundf10.eastmoney.com/"}
PROXIES = {"market": "510300", "size": "510500", "growth": "159915", "value_lowvol": "512890", "tech": "512760"}


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
    return frame.dropna(subset=["close"]).set_index("date")["close"].pct_change().rename(code), {**meta, "instrument_name": data.get("name"), "source_type": "exchange_adjusted_monthly_price"}


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
    raw_meta = {name: result[1] for name, result in results.items()}
    data_audit = [
        {"id": "FUND_NAV", "kind": "observed", "source": "东方财富基金历史净值", "instrument": code, "observations": raw_meta["fund"]["raw_observations"], "start": raw_meta["fund"]["actual_start"], "end": raw_meta["fund"]["actual_end"], "analysis_frequency": "monthly", "analysis_observations": int(aligned["fund"].notna().sum()), "sha256": raw_meta["fund"]["sha256"]},
        {"id": "HOLDINGS", "kind": "observed", "source": "东方财富基金季度持仓披露", "instrument": code, "observations": len(holdings), "sha256": holdings_meta["sha256"]},
        {"id": "SCALE", "kind": "observed", "source": "东方财富基金规模变动表", "instrument": code, "observations": len(scale), "sha256": scale_meta["sha256"]},
        {"id": "FACTOR_PROXIES", "kind": "derived_from_observed", "source": "真实 ETF 净值构造的市场/规模/价值/科技代理因子", "instrument": ",".join(PROXIES.values()), "observations": len(returns), "start": str(returns.index.min().to_period("M")), "end": str(returns.index.max().to_period("M")), "sha256": sha256("".join(raw_meta[name]["sha256"] for name in PROXIES).encode()).hexdigest()},
        {"id": "RISK_FREE", "kind": "assumption", "source": "月度无风险利率暂设为 0", "instrument": "N/A", "observations": len(returns), "sha256": None},
        {"id": "FLOW", "kind": "missing", "source": "尚未连接可复现的真实资金流序列", "instrument": code, "observations": 0, "sha256": None},
    ]
    mandate = {
        "fund_id": code, "declared_style": "public-data fund; contract parser pending",
        "target": pd.Series([1.0, 0.0, 0.0, 0.0, 0.0, 0.0], index=["market", "size", "value", "momentum", "quality", "tech"]),
        "benchmark": "510300 proxy; replace with prospectus benchmark",
        "evidence": "Eastmoney public NAV/archives; unofficial endpoint",
        "data_source": "eastmoney_public", "factor_model": "public ETF proxy factors v1",
        "fund_structure": ("exchange_traded_fund_candidate" if code.startswith(("1", "5")) else "open_end_fund"),
        "source_meta": {"nav": raw_meta, "holdings": holdings_meta, "scale": scale_meta},
        "scale_records": scale.to_dict("records"),
        "data_audit": data_audit,
    }
    return returns, holdings, mandate
