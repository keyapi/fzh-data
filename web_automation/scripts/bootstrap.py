"""Web automation capability bootstrap.

Idempotently prepares the isolated web_automation/.venv, Chromium, and
optionally the OCR dependency group. Runs from the repo root environment:

    uv run python web_automation/scripts/bootstrap.py --check
    uv run python web_automation/scripts/bootstrap.py            # install needed pieces
    uv run python web_automation/scripts/bootstrap.py --with-ocr # + OCR group on demand
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
WEB_ROOT = REPO_ROOT / "web_automation"
PROJECT_FLAG = "--project"
PROJECT_PATH = "web_automation"

ENV_SYNC = ["uv", "sync", PROJECT_FLAG, PROJECT_PATH]
CHROMIUM_INSTALL = [
    "uv", "run", PROJECT_FLAG, PROJECT_PATH,
    "python", "-m", "playwright", "install", "chromium",
]
OCR_SYNC = ["uv", "sync", PROJECT_FLAG, PROJECT_PATH, "--group", "ocr"]


def _venv_python(web_root: Path) -> Path:
    if sys.platform.startswith("win"):
        return web_root / ".venv" / "Scripts" / "python.exe"
    return web_root / ".venv" / "bin" / "python"


def _chromium_present(web_root: Path) -> bool:
    py = _venv_python(web_root)
    if not py.is_file():
        return False
    try:
        cp = subprocess.run(
            [str(py), "-m", "playwright", "install", "--dry-run", "chromium"],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=60,
        )
        text = (cp.stdout or "") + (cp.stderr or "")
        return "install" not in text or "No installs are required" in text
    except (OSError, subprocess.TimeoutExpired):
        return False


def probe_modules(python_exe: Path, names: tuple[str, ...]) -> bool:
    """Return True if *all* modules import in the given interpreter (not this process)."""
    if not python_exe.is_file() or not names:
        return False
    quoted = ", ".join(repr(n) for n in names)
    code = (
        "import importlib.util as i;"
        f"print('ok' if all(i.find_spec(n) for n in ({quoted},)) else 'no')"
    )
    try:
        cp = subprocess.run(
            [str(python_exe), "-c", code],
            capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=60,
        )
        return (cp.stdout or "").strip() == "ok"
    except (OSError, subprocess.TimeoutExpired):
        return False


def collect_web_facts(root: Path) -> dict[str, object]:
    web_root = root / "web_automation"
    facts = {
        "uv_present": bool(shutil.which("uv")),
        "child_env_ready": (web_root / ".venv").is_dir(),
        "playwright_installed": False,
        "chromium_ready": False,
        "ocr_ready": False,
    }
    if facts["child_env_ready"]:
        py = _venv_python(web_root)
        facts["playwright_installed"] = probe_modules(py, ("playwright",))
        if facts["playwright_installed"]:
            facts["chromium_ready"] = _chromium_present(web_root)
            facts["ocr_ready"] = probe_modules(py, ("ddddocr", "onnxruntime"))
    return facts


def plan_bootstrap(facts: dict[str, object], with_ocr: bool) -> list[list[str]]:
    commands: list[list[str]] = []
    if not facts.get("env_ready", False):
        commands.append(ENV_SYNC)
    if not facts.get("chromium_ready", False):
        commands.append(CHROMIUM_INSTALL)
    if with_ocr and not facts.get("ocr_ready", False):
        commands.append(OCR_SYNC)
    return commands


def _state_of(facts: dict[str, object], with_ocr: bool) -> str:
    if not facts.get("uv_present", False):
        return "BLOCKED"
    if not facts.get("env_ready", False) or not facts.get("chromium_ready", False):
        return "NEED_BROWSER"
    if with_ocr and not facts.get("ocr_ready", False):
        return "NEED_OCR"
    return "READY"


def run_install_commands(facts: dict[str, object], with_ocr: bool) -> int:
    commands = plan_bootstrap(facts, with_ocr)
    if not commands:
        print("READY: browser environment is up to date")
        return 0
    for cmd in commands:
        print(">", " ".join(cmd))
        cp = subprocess.run(cmd, cwd=REPO_ROOT)
        if cp.returncode != 0:
            print(f"FAILED: {cmd} (exit={cp.returncode})", file=sys.stderr)
            return cp.returncode
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="bootstrap web_automation capability pod")
    parser.add_argument("--check", action="store_true", help="only report state")
    parser.add_argument("--with-ocr", action="store_true", help="install optional OCR group")
    parser.add_argument("--json", action="store_true", help="machine-readable output")
    args = parser.parse_args(argv)

    facts = collect_web_facts(REPO_ROOT)
    facts["env_ready"] = facts["child_env_ready"]
    state = _state_of(facts, args.with_ocr)

    if args.json:
        print(json.dumps({"status": state, "facts": {
            k: v for k, v in facts.items() if k != "env_ready"
        }}, ensure_ascii=False))
    else:
        print(f"status={state}")
        for key in ("uv_present", "child_env_ready", "playwright_installed",
                    "chromium_ready", "ocr_ready"):
            print(f"  {key}={facts[key]}")

    if args.check:
        return 0 if state in {"READY", "BLOCKED"} else 3
    if state == "BLOCKED":
        print("BLOCKED: uv not found; install uv first", file=sys.stderr)
        return 1
    return run_install_commands(facts, args.with_ocr)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    raise SystemExit(main())
