from __future__ import annotations

import json
import shutil
from pathlib import Path

from ai4s_style_drift.research import run_autonomous_research
from ai4s_style_drift.server import analysis_payload
from ai4s_style_drift.research_workflow import discover_research_directions, execute_confirmed_research


ROOT = Path(__file__).parent
OUTPUT = ROOT / "docs"
STATIC = ROOT / "ai4s_style_drift" / "static"


def main() -> None:
    OUTPUT.mkdir(exist_ok=True)
    for name in ("index.html", "styles.css", "app.js"):
        shutil.copy2(STATIC / name, OUTPUT / name)
    data_dir = OUTPUT / "data"
    data_dir.mkdir(exist_ok=True)
    (data_dir / "analysis-159552.json").write_text(json.dumps(analysis_payload("159552"), ensure_ascii=False), encoding="utf-8")
    (data_dir / "research-159552.json").write_text(json.dumps(run_autonomous_research("159552"), ensure_ascii=False), encoding="utf-8")
    (data_dir / "discovery-159552.json").write_text(json.dumps(discover_research_directions("159552"), ensure_ascii=False), encoding="utf-8")
    for direction_id in ("D1", "D2", "D3", "D4"):
        payload = execute_confirmed_research("159552", direction_id)
        (data_dir / f"research-159552-{direction_id.lower()}.json").write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    (OUTPUT / ".nojekyll").touch()
    print(f"Built GitHub Pages snapshot in {OUTPUT}")


if __name__ == "__main__":
    main()
