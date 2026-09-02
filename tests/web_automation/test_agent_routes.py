"""Agent skill routing: no external repo paths, browser business skills use dispatcher."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

SKILLS = [
    ".agents/skills/web-automation/SKILL.md",
    ".agents/skills/playwright-setup/SKILL.md",
    ".agents/skills/tongtu-automation/SKILL.md",
    ".agents/skills/sellfox-automation/SKILL.md",
    ".agents/skills/stock-init/SKILL.md",
    ".agents/skills/warehouse-restock/SKILL.md",
]

# 业务路由 skills 必须先跑 dispatcher；playwright-setup 是纯环境技能（走 doctor/bootstrap）。
BROWSER_SKILLS = [
    ".agents/skills/web-automation/SKILL.md",
    ".agents/skills/tongtu-automation/SKILL.md",
    ".agents/skills/sellfox-automation/SKILL.md",
]


def _read(rel: str) -> str:
    text = (ROOT / rel).read_text(encoding="utf-8-sig", errors="replace")
    return text


def test_skills_never_reference_external_repo():
    for rel in SKILLS:
        assert (ROOT / rel).is_file(), f"missing {rel}"
        text = _read(rel)
        assert "D:\\Work\\赛狐\\网页自动化" not in text, rel
        assert "D:/Work/赛狐/网页自动化" not in text, rel


def test_browser_skills_use_dispatcher():
    for rel in BROWSER_SKILLS:
        text = _read(rel)
        assert "web_automation/scripts/dispatch.py" in text, rel


def test_browser_skills_state_check_first():
    for rel in BROWSER_SKILLS:
        text = _read(rel)
        assert "dispatch.py" in text and "--check" in text, rel


def test_write_rules_carry_confirm_scope():
    text = _read(".agents/skills/sellfox-automation/SKILL.md")
    assert "confirm-scope" in text or "NEED_USER_CONFIRMATION" in text
