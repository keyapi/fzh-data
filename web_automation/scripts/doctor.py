"""Read-only environment doctor for the web_automation capability pod.

Reports uv/Python/dependency/Chromium/profile state without writing anything.
Runs from the repo root environment:

    uv run python web_automation/scripts/doctor.py
    uv run python web_automation/scripts/doctor.py --json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def format_report(facts: dict[str, object]) -> str:
    lines = ["=== web_automation 能力舱体检 ==="]
    for key in ("uv_present", "child_env_ready", "playwright_installed",
                "chromium_ready", "ocr_ready"):
        lines.append(f"{key}={facts[key]}")
    lines.append("")
    lines.append("网页任务触发时由 dispatcher/bootstrap 初始化；普通 `uv sync` 无需安装。")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="web_automation capability doctor")
    parser.add_argument("--json", action="store_true", help="machine-readable output")
    args = parser.parse_args(argv)

    # Deliberately imported lazily so doctor works before .venv exists.
    from web_automation.scripts.bootstrap import collect_web_facts

    facts = collect_web_facts(REPO_ROOT)
    if args.json:
        print(json.dumps(facts, ensure_ascii=False, indent=2))
    else:
        print(format_report(facts))
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    raise SystemExit(main())
