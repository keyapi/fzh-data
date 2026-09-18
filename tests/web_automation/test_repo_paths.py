"""No tracked root code may reference the old external browser repo or its Windows venv.

Historical docs (design specs, superpowers plans) and local settings are excluded.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

EXTERNAL_PATTERNS = [
    "D:\\Work\\赛狐\\网页自动化",
    "D:/Work/赛狐/网页自动化",
    ".venv\\Scripts\\python.exe",
    ".venv/bin/python",
]
EXCLUDE_GLOBS = [
    ".claude/settings.local.json",
    "docs/superpowers/**",
    "*.md",  # prose is covered by docs tests; this test focuses on code
]


def _tracked_files() -> list[Path]:
    cp = subprocess.run(
        ["git", "ls-files"], cwd=ROOT, capture_output=True, text=True,
        encoding="utf-8", errors="replace",
    )
    return [ROOT / p for p in cp.stdout.splitlines() if p]


def test_tracked_code_has_no_external_repo_path():
    offenders = []
    for f in _tracked_files():
        if f.suffix != ".py":
            continue
        # 迁移测试自身断言这些旧路径不存在，故扫描真实代码时排除本目录。
        if f.relative_to(ROOT).parts[:2] == ("tests", "web_automation"):
            continue
        text = f.read_text(encoding="utf-8", errors="replace")
        for pat in EXTERNAL_PATTERNS:
            if pat in text:
                offenders.append((str(f.relative_to(ROOT)), pat))
    assert not offenders, f"external path in code: {offenders}"


def test_specific_root_integrators_clean():
    files = [
        "warehouse_restock/run_full_restock_flow.py",
        "warehouse_restock/test_e2e_flow.py",
        "missing_products/identify_missing_products.py",
        "missing_products/audit_three_systems.py",
    ]
    for rel in files:
        text = (ROOT / rel).read_text(encoding="utf-8", errors="replace")
        assert "D:\\Work\\赛狐\\网页自动化" not in text, rel
        assert "D:/Work/赛狐/网页自动化" not in text, rel
        assert "WEB_AUTO = Path" not in text, f"{rel} still has WEB_AUTO"


def test_web_automation_py_has_no_machine_cursor_path():
    """迁入脚本不得写死本仓库在开发机上的绝对路径。"""
    offenders = []
    web = ROOT / "web_automation"
    for py in web.rglob("*.py"):
        text = py.read_text(encoding="utf-8", errors="replace")
        if "D:/Work/赛狐/Cursor" in text or "D:\\Work\\赛狐\\Cursor" in text:
            offenders.append(str(py.relative_to(ROOT)))
    assert not offenders, f"machine path in web_automation: {offenders}"
