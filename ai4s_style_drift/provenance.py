from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
import json
import re


LITERATURE = [
    {
        "citation_id": "CIT-SHARPE-1992",
        "title": "Asset Allocation: Management Style and Performance Measurement",
        "authors": "William F. Sharpe",
        "year": 1992,
        "journal": "Journal of Portfolio Management",
        "doi": "10.3905/jpm.1992.409394",
        "extracted": {
            "measure": "Return-based style analysis using constrained combinations of asset-class returns.",
            "mechanism": "Observed fund returns can be decomposed into broad style exposures.",
            "limitation": "Return-based estimates may not identify intra-period trading or holdings-level mechanisms.",
        },
    },
    {
        "citation_id": "CIT-BROWN-GOETZMANN-1997",
        "title": "Mutual Fund Styles",
        "authors": "Stephen J. Brown; William N. Goetzmann",
        "year": 1997,
        "journal": "Journal of Financial Economics",
        "doi": "10.1016/S0304-405X(96)00898-7",
        "extracted": {
            "measure": "Return-pattern classification of mutual fund styles.",
            "mechanism": "Funds form empirically distinguishable style groups whose membership can vary.",
            "limitation": "Style classification is model- and sample-dependent.",
        },
    },
    {
        "citation_id": "CIT-CHAN-CHEN-LAKONISHOK-2002",
        "title": "On Mutual Fund Investment Styles",
        "authors": "Louis K. C. Chan; Hsiu-Lang Chen; Josef Lakonishok",
        "year": 2002,
        "journal": "Review of Financial Studies",
        "doi": "10.1093/rfs/15.5.1407",
        "extracted": {
            "measure": "Holdings characteristics and return-based evidence for investment style.",
            "mechanism": "Portfolio characteristics reveal economically meaningful style choices.",
            "limitation": "Holdings snapshots are incomplete representations of trading between disclosure dates.",
        },
    },
]


PUBLIC_DATA_MANIFEST = [
    {"dataset_id": "NAV", "required": True, "source": "Eastmoney public fund NAV JSON", "frequency": "daily", "status": "adapter_not_connected", "version_rule": "access timestamp + raw response SHA-256"},
    {"dataset_id": "HOLDINGS", "required": True, "source": "Eastmoney fund archive holdings HTML", "frequency": "quarterly", "status": "adapter_not_connected", "version_rule": "report year + raw response SHA-256"},
    {"dataset_id": "FLOW", "required": True, "source": "Eastmoney scale table; return-adjusted flow derivation pending", "frequency": "quarterly or lower", "status": "data_gap", "version_rule": "formula version + input fingerprints"},
    {"dataset_id": "FACTORS", "required": True, "source": "ETF proxy factors from public NAV: 510300/510500/159915/512890/512760", "frequency": "monthly", "status": "adapter_not_connected", "version_rule": "proxy list + formula version + raw fingerprints"},
]


def citation_audit() -> list[dict]:
    doi_pattern = re.compile(r"^10\.\d{4,9}/\S+$", re.I)
    return [
        {
            "citation_id": item["citation_id"],
            "doi": item["doi"],
            "doi_format_valid": bool(doi_pattern.match(item["doi"])),
            "metadata_complete": all(item.get(k) for k in ("title", "authors", "year", "journal")),
            "verification_status": "seed metadata; online DOI resolution pending",
        }
        for item in LITERATURE
    ]


def code_fingerprint() -> dict:
    root = Path(__file__).parent
    files = sorted(p for p in root.glob("*.py") if p.is_file())
    combined = sha256()
    per_file = {}
    for path in files:
        digest = sha256(path.read_bytes()).hexdigest()
        per_file[path.name] = digest[:12]
        combined.update(path.name.encode("utf-8")); combined.update(digest.encode("ascii"))
    return {"algorithm": "SHA-256", "environment_version": combined.hexdigest()[:16], "files": per_file}


def data_fingerprint(fund_id: str, rows: int, columns: list[str], source: str = "synthetic") -> dict:
    version = "eastmoney-public-v1" if source == "eastmoney_public" else "synthetic-v2"
    descriptor = json.dumps({"fund_id": fund_id, "rows": rows, "columns": columns, "version": version}, sort_keys=True)
    return {"dataset_version": version, "rows": rows, "columns": columns, "schema_sha256": sha256(descriptor.encode()).hexdigest()[:16], "generated_at": datetime.now(timezone.utc).isoformat(), "public_data_connected": source == "eastmoney_public"}
