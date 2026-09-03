"""OKF doc structure for web_automation: frontmatter, per-dir index, no external paths."""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DOCS = ROOT / "web_automation" / "docs"
SKIP_DIRS = {"__pycache__"}


def _all_md() -> list[Path]:
    return [p for p in DOCS.rglob("*.md") if p.is_file()]


def test_docs_present():
    assert DOCS.is_dir()
    assert (DOCS / "index.md").is_file()
    assert (DOCS / "log.md").is_file()


def test_every_md_has_frontmatter_and_type():
    bad = []
    for p in _all_md():
        text = p.read_text(encoding="utf-8-sig", errors="replace")
        if not text.startswith("---"):
            bad.append(f"{p.relative_to(ROOT)}: no frontmatter")
            continue
        fm = text.split("---", 2)[1] if text.count("---") >= 2 else ""
        if not re.search(r"^type:\s*\S", fm, re.M):
            bad.append(f"{p.relative_to(ROOT)}: missing type field")
    assert not bad, "\n".join(bad)


def test_every_docs_dir_has_index():
    missing = []
    for d in DOCS.rglob("*"):
        if d.is_dir() and d.name not in SKIP_DIRS:
            if not (d / "index.md").is_file():
                missing.append(str(d.relative_to(ROOT)))
    assert not missing, f"dirs missing index.md: {missing}"


def test_user_facing_docs_have_no_external_repo_path():
    offenders = []
    for p in _all_md():
        text = p.read_text(encoding="utf-8-sig", errors="replace")
        if "D:\\Work\\赛狐\\网页自动化" in text or "D:/Work/赛狐/网页自动化" in text:
            offenders.append(str(p.relative_to(ROOT)))
    assert not offenders, f"external path in docs: {offenders}"
