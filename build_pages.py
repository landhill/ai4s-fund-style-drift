from __future__ import annotations

import json
import shutil
from pathlib import Path

from ai4s_style_drift.research import run_autonomous_research
from ai4s_style_drift.server import analysis_payload


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
    (OUTPUT / ".nojekyll").touch()
    print(f"Built GitHub Pages snapshot in {OUTPUT}")


if __name__ == "__main__":
    main()
