from __future__ import annotations

import argparse
import json

from .public_data import load_public_fund


def main() -> None:
    parser = argparse.ArgumentParser(description="Download and fingerprint public A-share fund data")
    parser.add_argument("fund_code", help="six-digit fund code")
    parser.add_argument("--refresh", action="store_true", help="ignore cache and download again")
    args = parser.parse_args()
    returns, holdings, mandate = load_public_fund(args.fund_code, refresh=args.refresh)
    summary = {
        "fund_code": args.fund_code,
        "monthly_observations": len(returns),
        "period": [str(returns.index.min().date()), str(returns.index.max().date())],
        "holdings_rows": len(holdings),
        "scale_rows": len(mandate["scale_records"]),
        "factor_model": mandate["factor_model"],
        "source_meta": mandate["source_meta"],
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
