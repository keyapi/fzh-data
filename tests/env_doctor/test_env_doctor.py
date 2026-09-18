"""Tests for scripts/env_doctor.py — recommendation matrix + Windows probes."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

import importlib.util

ROOT = Path(__file__).resolve().parents[2]
_SPEC = importlib.util.spec_from_file_location(
    "fzh_env_doctor", ROOT / "scripts" / "env_doctor.py"
)
assert _SPEC and _SPEC.loader
env_doctor = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(env_doctor)


# ---------------------------------------------------------------------------
# C. Recommendation matrix (runs on any OS)
# ---------------------------------------------------------------------------


def test_recommend_windows_ps51_only_suggests_pwsh_and_gbk():
    facts = {
        "os": "Windows",
        "is_windows": True,
        "powershell_51": {"present": True, "version": "5.1.26100.9168"},
        "pwsh": {"present": False, "version": None},
        "console_codepage": 936,
        "python_stdout_encoding": "cp936",
        "skill_windows_agent_shell": True,
        "tools": {"git": True, "uv": True, "node": True},
        "web_automation": {"available": True, "ready": True},
    }
    recs = env_doctor.build_recommendations(facts)
    codes = {r["code"] for r in recs}
    assert "install_pwsh_stable" in codes
    assert "encoding_gbk_risk" in codes
    assert "load_windows_agent_shell" in codes
    assert "install_pwsh_stable" not in {
        r["code"] for r in recs if r["code"] == "pwsh_ok"
    }


def test_recommend_windows_with_pwsh_skips_install():
    facts = {
        "os": "Windows",
        "is_windows": True,
        "powershell_51": {"present": True, "version": "5.1.26100.9168"},
        "pwsh": {"present": True, "version": "7.5.2"},
        "console_codepage": 65001,
        "python_stdout_encoding": "utf-8",
        "skill_windows_agent_shell": True,
        "tools": {"git": True, "uv": True, "node": True},
        "web_automation": {"available": True, "ready": True},
    }
    recs = env_doctor.build_recommendations(facts)
    codes = {r["code"] for r in recs}
    assert "install_pwsh_stable" not in codes
    assert "pwsh_ok" in codes
    assert "encoding_gbk_risk" not in codes


def test_recommend_posix_skips_windows_items():
    facts = {
        "os": "Darwin",
        "is_windows": False,
        "powershell_51": {"present": False, "version": None},
        "pwsh": {"present": False, "version": None},
        "console_codepage": None,
        "python_stdout_encoding": "utf-8",
        "skill_windows_agent_shell": True,
        "tools": {"git": True, "uv": True, "node": True},
        "web_automation": {"available": True, "ready": True},
    }
    recs = env_doctor.build_recommendations(facts)
    codes = {r["code"] for r in recs}
    assert "install_pwsh_stable" not in codes
    assert "encoding_gbk_risk" not in codes
    assert "windows_skill_not_applicable" in codes


def test_recommend_missing_tools():
    facts = {
        "os": "Linux",
        "is_windows": False,
        "powershell_51": {"present": False, "version": None},
        "pwsh": {"present": False, "version": None},
        "console_codepage": None,
        "python_stdout_encoding": "utf-8",
        "skill_windows_agent_shell": False,
        "tools": {"git": False, "uv": False, "node": True},
    }
    recs = env_doctor.build_recommendations(facts)
    codes = {r["code"] for r in recs}
    assert "install_git" in codes
    assert "install_uv" in codes
    assert "install_node" not in codes


def _windows_facts(**overrides):
    facts = {
        "os": "Windows",
        "is_windows": True,
        "powershell_51": {"present": True, "version": "5.1.26100.9168"},
        "pwsh": {"present": True, "version": "7.5.2"},
        "console_codepage": 65001,
        "python_stdout_encoding": "utf-8",
        "skill_windows_agent_shell": True,
        "tools": {"git": True, "uv": True, "node": True},
        "web_automation": {"available": True, "ready": False},
    }
    facts.update(overrides)
    return facts


def test_web_automation_available_not_ready_reports_on_demand():
    recs = env_doctor.build_recommendations(_windows_facts())
    codes = {r["code"] for r in recs}
    assert "web_automation_on_demand" in codes
    assert "web_automation_ready" not in codes


def test_web_automation_ready_reports_ready_only():
    recs = env_doctor.build_recommendations(
        _windows_facts(web_automation={"available": True, "ready": True})
    )
    codes = {r["code"] for r in recs}
    assert "web_automation_ready" in codes
    assert "web_automation_on_demand" not in codes


def test_web_automation_absent_no_rec():
    recs = env_doctor.build_recommendations(
        _windows_facts(web_automation={"available": False, "ready": False})
    )
    codes = {r["code"] for r in recs}
    assert "web_automation_on_demand" not in codes
    assert "web_automation_ready" not in codes


# ---------------------------------------------------------------------------
# A / B. Live Windows probes (skip on non-Windows or missing shells)
# ---------------------------------------------------------------------------

CHINESE_SAMPLE = "赛狐SKU"


def _has_powershell() -> bool:
    return env_doctor.which("powershell") is not None


def _has_pwsh() -> bool:
    return env_doctor.which("pwsh") is not None


@pytest.mark.skipif(not sys.platform.startswith("win"), reason="Windows only")
@pytest.mark.skipif(not _has_powershell(), reason="powershell.exe missing")
def test_probe_ps51_and_operator_fails():
    result = env_doctor.probe_and_chain("powershell")
    assert result["ok"] is False
    joined = (result.get("stderr") or "") + (result.get("stdout") or "")
    assert "&&" in joined or "ParserError" in joined or result["returncode"] != 0


@pytest.mark.skipif(not sys.platform.startswith("win"), reason="Windows only")
@pytest.mark.skipif(not _has_pwsh(), reason="pwsh not installed yet")
def test_probe_pwsh_and_operator_succeeds():
    result = env_doctor.probe_and_chain("pwsh")
    assert result["ok"] is True
    assert result["returncode"] == 0


@pytest.mark.skipif(not sys.platform.startswith("win"), reason="Windows only")
@pytest.mark.skipif(not _has_powershell(), reason="powershell.exe missing")
def test_probe_ps51_compat_chain_succeeds():
    result = env_doctor.probe_compat_chain("powershell")
    assert result["ok"] is True


@pytest.mark.skipif(not sys.platform.startswith("win"), reason="Windows only")
@pytest.mark.skipif(not _has_powershell(), reason="powershell.exe missing")
def test_probe_ps51_default_read_utf8_chinese_garbles(tmp_path: Path):
    utf8_file = tmp_path / "sample_utf8.txt"
    utf8_file.write_text(CHINESE_SAMPLE + "\n", encoding="utf-8")
    result = env_doctor.probe_read_utf8_default("powershell", utf8_file)
    # Default Get-Content on CP936 typically mis-decodes UTF-8 Chinese.
    assert result["text"] != CHINESE_SAMPLE


@pytest.mark.skipif(not sys.platform.startswith("win"), reason="Windows only")
@pytest.mark.skipif(not _has_powershell(), reason="powershell.exe missing")
def test_probe_ps51_explicit_utf8_read_ok(tmp_path: Path):
    utf8_file = tmp_path / "sample_utf8.txt"
    utf8_file.write_text(CHINESE_SAMPLE + "\n", encoding="utf-8")
    result = env_doctor.probe_read_utf8_explicit("powershell", utf8_file)
    assert result["text"] == CHINESE_SAMPLE


@pytest.mark.skipif(not sys.platform.startswith("win"), reason="Windows only")
@pytest.mark.skipif(not _has_pwsh(), reason="pwsh not installed yet")
def test_probe_pwsh_default_read_utf8_ok(tmp_path: Path):
    utf8_file = tmp_path / "sample_utf8.txt"
    utf8_file.write_text(CHINESE_SAMPLE + "\n", encoding="utf-8")
    result = env_doctor.probe_read_utf8_default("pwsh", utf8_file)
    assert result["text"] == CHINESE_SAMPLE


@pytest.mark.skipif(not sys.platform.startswith("win"), reason="Windows only")
@pytest.mark.skipif(not _has_powershell(), reason="powershell.exe missing")
def test_probe_ps51_set_content_utf8_writes_bom(tmp_path: Path):
    out = tmp_path / "bom_out.txt"
    result = env_doctor.probe_set_content_utf8_bom("powershell", out, CHINESE_SAMPLE)
    assert result["has_bom"] is True
    assert out.read_bytes()[:3] == b"\xef\xbb\xbf"


def test_format_report_contains_chinese_headers():
    report = {
        "facts": {
            "os": "Windows",
            "is_windows": True,
            "powershell_51": {"present": True, "version": "5.1.0"},
            "pwsh": {"present": False, "version": None},
            "console_codepage": 936,
            "python_stdout_encoding": "cp936",
            "skill_windows_agent_shell": True,
            "tools": {"git": True, "uv": True, "node": True},
            "web_automation": {"available": True, "ready": True},
        },
        "recommendations": env_doctor.build_recommendations(
            {
                "os": "Windows",
                "is_windows": True,
                "powershell_51": {"present": True, "version": "5.1.0"},
                "pwsh": {"present": False, "version": None},
                "console_codepage": 936,
                "python_stdout_encoding": "cp936",
                "skill_windows_agent_shell": True,
                "tools": {"git": True, "uv": True, "node": True},
                "web_automation": {"available": True, "ready": True},
            }
        ),
        "probes": None,
    }
    text = env_doctor.format_human_report(report)
    assert "环境体检" in text
    assert "建议" in text
