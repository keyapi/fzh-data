#!/usr/bin/env python3
"""Cross-platform agent environment doctor for fzh-data.

Default: detect + recommend only (never auto-install).
Windows probes: && chain, GBK vs UTF-8 read, Set-Content BOM.

Usage:
  uv run python scripts/env_doctor.py
  uv run python scripts/env_doctor.py --json
  uv run python scripts/env_doctor.py --probe
  uv run python scripts/env_doctor.py --apply-ps7   # Windows only, after user consent
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
SKILL_PATH = ROOT / ".agents" / "skills" / "windows-agent-shell" / "SKILL.md"
CHINESE_SAMPLE = "赛狐SKU"
WINGET_PS7 = [
    "winget",
    "install",
    "--id",
    "Microsoft.PowerShell",
    "--accept-package-agreements",
    "--accept-source-agreements",
]


def which(name: str) -> str | None:
    return shutil.which(name)


def _run(
    argv: list[str],
    *,
    timeout: float = 30,
    cwd: str | Path | None = None,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        argv,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
        cwd=cwd,
    )


def _run_ps(shell: str, command: str, *, timeout: float = 30) -> subprocess.CompletedProcess[str]:
    exe = which(shell)
    if not exe:
        raise FileNotFoundError(shell)
    return _run(
        [exe, "-NoProfile", "-NonInteractive", "-Command", command],
        timeout=timeout,
    )


def _ps_version(shell: str) -> str | None:
    if not which(shell):
        return None
    try:
        cp = _run_ps(shell, "$PSVersionTable.PSVersion.ToString()")
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return None
    if cp.returncode != 0:
        return None
    return (cp.stdout or "").strip() or None


def _console_codepage() -> int | None:
    if not sys.platform.startswith("win"):
        return None
    try:
        cp = _run(["cmd", "/c", "chcp"], timeout=10)
        # Output like: Active code page: 936
        text = (cp.stdout or "") + (cp.stderr or "")
        digits = "".join(ch if ch.isdigit() else " " for ch in text).split()
        return int(digits[-1]) if digits else None
    except (OSError, ValueError, subprocess.TimeoutExpired):
        return None


def collect_facts(repo_root: Path | None = None) -> dict[str, Any]:
    root = repo_root or ROOT
    skill = (root / ".agents" / "skills" / "windows-agent-shell" / "SKILL.md").is_file()
    is_windows = sys.platform.startswith("win")
    web_auto = root / "web_automation"
    return {
        "os": platform.system(),
        "is_windows": is_windows,
        "powershell_51": {
            "present": bool(which("powershell")),
            "version": _ps_version("powershell") if is_windows else None,
        },
        "pwsh": {
            "present": bool(which("pwsh")),
            "version": _ps_version("pwsh"),
        },
        "console_codepage": _console_codepage(),
        "python_stdout_encoding": getattr(sys.stdout, "encoding", None),
        "python_utf8_env": os.environ.get("PYTHONUTF8"),
        "skill_windows_agent_shell": skill,
        "web_automation": {
            "available": (web_auto / "pyproject.toml").is_file(),
            "ready": (web_auto / ".venv").is_dir(),
        },
        "tools": {
            "git": bool(which("git")),
            "uv": bool(which("uv")),
            "node": bool(which("node")),
        },
    }


def build_recommendations(facts: dict[str, Any]) -> list[dict[str, str]]:
    recs: list[dict[str, str]] = []
    tools = facts.get("tools") or {}

    if not tools.get("git"):
        recs.append(
            {
                "code": "install_git",
                "severity": "high",
                "message": "未检测到 git。Windows: winget install Git.Git；Mac: brew install git；Linux: apt/yum 安装 git。",
            }
        )
    if not tools.get("uv"):
        recs.append(
            {
                "code": "install_uv",
                "severity": "high",
                "message": "未检测到 uv。Windows: irm https://astral.sh/uv/install.ps1 | iex；Mac/Linux: curl -LsSf https://astral.sh/uv/install.sh | sh",
            }
        )
    if not tools.get("node"):
        recs.append(
            {
                "code": "install_node",
                "severity": "medium",
                "message": "未检测到 Node.js。Windows: winget install OpenJS.NodeJS.LTS；Mac: brew install node。",
            }
        )

    web_auto = facts.get("web_automation") or {}
    if web_auto.get("available"):
        if web_auto.get("ready"):
            recs.append(
                {
                    "code": "web_automation_ready",
                    "severity": "info",
                    "message": "网页自动化能力舱已就绪（web_automation/.venv 存在）。需要浏览器任务时 Agent 会先跑 dispatcher 检查状态。",
                }
            )
        else:
            recs.append(
                {
                    "code": "web_automation_on_demand",
                    "severity": "info",
                    "message": (
                        "检测到网页自动化能力舱 web_automation/，但尚未初始化。"
                        "普通 `uv sync` 不需要它；首个网页任务触发时由 "
                        "web_automation/scripts/bootstrap.py 自动建独立 .venv + Chromium，"
                        "OCR 仅在显式请求时安装。无需在本步手动安装。"
                    ),
                }
            )

    if facts.get("is_windows"):
        pwsh = facts.get("pwsh") or {}
        if not pwsh.get("present"):
            recs.append(
                {
                    "code": "install_pwsh_stable",
                    "severity": "high",
                    "message": (
                        "仅有 Windows PowerShell 5.1，缺少 PowerShell 7 (pwsh)。"
                        "Agent 常用 && 会 ParserError；建议安装稳定版（勿装 Preview）："
                        " winget install --id Microsoft.PowerShell --accept-package-agreements"
                    ),
                }
            )
        else:
            recs.append(
                {
                    "code": "pwsh_ok",
                    "severity": "info",
                    "message": f"已安装 PowerShell 7: {pwsh.get('version') or 'unknown'}。Agent 优先用 pwsh -NoProfile -Command。",
                }
            )

        codepage = facts.get("console_codepage")
        enc = (facts.get("python_stdout_encoding") or "").lower()
        gbk_risk = False
        if codepage in (936, 54936):
            gbk_risk = True
        if enc and "utf" not in enc and "65001" not in enc:
            gbk_risk = True
        # Even with pwsh, warn if console still GBK and no pwsh? Plan: only when risk.
        # When pwsh present and codepage 65001, skip. When pwsh present but 936, still warn lightly.
        if gbk_risk:
            # If only 5.1, high; if pwsh present, still note console GBK for 5.1 paths
            if not pwsh.get("present"):
                recs.append(
                    {
                        "code": "encoding_gbk_risk",
                        "severity": "high",
                        "message": (
                            f"控制台代码页={codepage}，Python stdout={facts.get('python_stdout_encoding')}。"
                            "GBK/cp936 默认读取器会把 UTF-8 中文文档读成乱码。"
                            "读文件用 Get-Content -Encoding UTF8 或 Python encoding='utf-8'；"
                            "写文件禁止 PS 5.1 Set-Content -Encoding UTF8（会写 BOM）。"
                            "不要打开系统「Beta: 全球语言使用 UTF-8」。"
                        ),
                    }
                )
            else:
                recs.append(
                    {
                        "code": "encoding_console_note",
                        "severity": "medium",
                        "message": (
                            f"仍检测到代码页={codepage} / stdout={facts.get('python_stdout_encoding')}。"
                            "用 pwsh 读写 UTF-8；若必须走 powershell.exe，显式 -Encoding UTF8 读，"
                            "写文件用 Python（无 BOM）。"
                        ),
                    }
                )

        if facts.get("skill_windows_agent_shell"):
            recs.append(
                {
                    "code": "load_windows_agent_shell",
                    "severity": "info",
                    "message": "项目含 windows-agent-shell skill；在 Windows 上跑 shell 前应加载，避免 bash 语法与 BOM。",
                }
            )
        else:
            recs.append(
                {
                    "code": "missing_windows_skill",
                    "severity": "medium",
                    "message": "未找到 .agents/skills/windows-agent-shell/SKILL.md，请从最新 main/feature 分支拉取。",
                }
            )
    else:
        recs.append(
            {
                "code": "windows_skill_not_applicable",
                "severity": "info",
                "message": "非 Windows：跳过 PowerShell 7 / GBK 建议；windows-agent-shell 执行约定不适用。",
            }
        )

    return recs


# ---------------------------------------------------------------------------
# Probes
# ---------------------------------------------------------------------------


def probe_and_chain(shell: str) -> dict[str, Any]:
    cp = _run_ps(shell, "Write-Output a && Write-Output b")
    ok = cp.returncode == 0 and "a" in (cp.stdout or "") and "b" in (cp.stdout or "")
    return {
        "name": f"{shell}_and_chain",
        "ok": ok,
        "returncode": cp.returncode,
        "stdout": (cp.stdout or "").strip(),
        "stderr": (cp.stderr or "").strip(),
    }


def probe_compat_chain(shell: str) -> dict[str, Any]:
    cp = _run_ps(shell, "Write-Output a; if ($?) { Write-Output b }")
    ok = cp.returncode == 0 and "a" in (cp.stdout or "") and "b" in (cp.stdout or "")
    return {
        "name": f"{shell}_compat_chain",
        "ok": ok,
        "returncode": cp.returncode,
        "stdout": (cp.stdout or "").strip(),
        "stderr": (cp.stderr or "").strip(),
    }


def _ps_quote(path: Path | str) -> str:
    return str(path).replace("'", "''")


def _probe_read_to_file(shell: str, src: Path, *, encoding_arg: str | None) -> dict[str, Any]:
    """Read via PowerShell, write result with .NET UTF-8 no-BOM (avoids console CP pollution)."""
    import tempfile

    fd, name = tempfile.mkstemp(prefix="env_doctor_read_", suffix=".txt")
    os.close(fd)
    out = Path(name)
    try:
        src_q = _ps_quote(src)
        out_q = _ps_quote(out)
        if encoding_arg:
            get_cmd = (
                f"(Get-Content -LiteralPath '{src_q}' -Encoding {encoding_arg} -Raw).Trim()"
            )
            name_suffix = encoding_arg.lower()
        else:
            get_cmd = f"(Get-Content -LiteralPath '{src_q}' -Raw).Trim()"
            name_suffix = "default"
        # WriteAllText with UTF8Encoding(false) = no BOM
        ps = (
            f"$t = {get_cmd}; "
            f"[IO.File]::WriteAllText('{out_q}', $t, "
            f"[Text.UTF8Encoding]::new($false))"
        )
        cp = _run_ps(shell, ps)
        text = out.read_text(encoding="utf-8") if out.is_file() else ""
        return {
            "name": f"{shell}_read_{name_suffix}",
            "ok": text == CHINESE_SAMPLE,
            "text": text,
            "returncode": cp.returncode,
            "stderr": (cp.stderr or "").strip(),
        }
    finally:
        out.unlink(missing_ok=True)


def probe_read_utf8_default(shell: str, path: Path) -> dict[str, Any]:
    return _probe_read_to_file(shell, path, encoding_arg=None)


def probe_read_utf8_explicit(shell: str, path: Path) -> dict[str, Any]:
    return _probe_read_to_file(shell, path, encoding_arg="UTF8")


def probe_set_content_utf8_bom(shell: str, path: Path, content: str) -> dict[str, Any]:
    lit = str(path).replace("'", "''")
    # Pass content via env-safe single quotes
    safe = content.replace("'", "''")
    cp = _run_ps(
        shell,
        f"Set-Content -LiteralPath '{lit}' -Value '{safe}' -Encoding UTF8",
    )
    data = path.read_bytes() if path.is_file() else b""
    has_bom = data[:3] == b"\xef\xbb\xbf"
    return {
        "name": f"{shell}_set_content_bom",
        "ok": has_bom,  # ok means "reproduced BOM bug" for documentation
        "has_bom": has_bom,
        "returncode": cp.returncode,
        "stderr": (cp.stderr or "").strip(),
        "size": len(data),
    }


def run_probes(tmp_dir: Path | None = None) -> dict[str, Any]:
    if not sys.platform.startswith("win"):
        return {"skipped": True, "reason": "not Windows"}

    import tempfile

    cleanup = False
    if tmp_dir is None:
        tmp_dir = Path(tempfile.mkdtemp(prefix="env_doctor_"))
        cleanup = True

    results: dict[str, Any] = {"skipped": False, "items": []}
    utf8_file = tmp_dir / "sample_utf8.txt"
    utf8_file.write_bytes((CHINESE_SAMPLE + "\n").encode("utf-8"))  # no BOM

    try:
        if which("powershell"):
            results["items"].append(probe_and_chain("powershell"))
            results["items"].append(probe_compat_chain("powershell"))
            results["items"].append(probe_read_utf8_default("powershell", utf8_file))
            results["items"].append(probe_read_utf8_explicit("powershell", utf8_file))
            bom_path = tmp_dir / "bom_out.txt"
            results["items"].append(
                probe_set_content_utf8_bom("powershell", bom_path, CHINESE_SAMPLE)
            )
        if which("pwsh"):
            results["items"].append(probe_and_chain("pwsh"))
            results["items"].append(probe_compat_chain("pwsh"))
            results["items"].append(probe_read_utf8_default("pwsh", utf8_file))
            results["items"].append(probe_read_utf8_explicit("pwsh", utf8_file))
        else:
            results["pwsh_note"] = "pwsh not installed — PS7 probes skipped"
    finally:
        if cleanup:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    return results


def format_human_report(report: dict[str, Any]) -> str:
    facts = report["facts"]
    lines = [
        "=== fzh-data 环境体检 ===",
        f"OS: {facts.get('os')}",
        f"PowerShell 5.1: {facts.get('powershell_51')}",
        f"PowerShell 7 (pwsh): {facts.get('pwsh')}",
        f"控制台代码页: {facts.get('console_codepage')}",
        f"Python stdout: {facts.get('python_stdout_encoding')}",
        f"PYTHONUTF8: {facts.get('python_utf8_env')}",
        f"windows-agent-shell skill: {facts.get('skill_windows_agent_shell')}",
        f"tools: {facts.get('tools')}",
        "",
        "--- 建议（默认只建议，不自动安装）---",
    ]
    for r in report.get("recommendations") or []:
        lines.append(f"[{r.get('severity')}] {r.get('code')}: {r.get('message')}")

    probes = report.get("probes")
    if probes:
        lines.append("")
        lines.append("--- 探针 ---")
        if probes.get("skipped"):
            lines.append(f"跳过: {probes.get('reason')}")
        else:
            if probes.get("pwsh_note"):
                lines.append(probes["pwsh_note"])
            for item in probes.get("items") or []:
                lines.append(
                    f"{item.get('name')}: ok={item.get('ok')} rc={item.get('returncode')} "
                    f"text={item.get('text', item.get('has_bom', ''))!r}"
                )
    lines.append("")
    lines.append("同事：请把上述建议发给用户确认后再安装；不要擅自 winget / 全量导入。")
    return "\n".join(lines)


def apply_ps7() -> int:
    if not sys.platform.startswith("win"):
        print("`--apply-ps7` 仅 Windows 可用", file=sys.stderr)
        return 2
    print("即将执行（稳定版，非 Preview）:")
    print(" ", " ".join(WINGET_PS7))
    if not which("winget"):
        print("未找到 winget", file=sys.stderr)
        return 1
    cp = subprocess.run(WINGET_PS7)
    return cp.returncode


def build_report(*, probe: bool = False, repo_root: Path | None = None) -> dict[str, Any]:
    facts = collect_facts(repo_root)
    recs = build_recommendations(facts)
    probes = run_probes() if probe else None
    return {"facts": facts, "recommendations": recs, "probes": probes}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="fzh-data agent environment doctor")
    parser.add_argument("--json", action="store_true", help="Print JSON report")
    parser.add_argument("--probe", action="store_true", help="Run Windows && / UTF-8 probes")
    parser.add_argument(
        "--apply-ps7",
        action="store_true",
        help="Install PowerShell 7 stable via winget (explicit consent)",
    )
    parser.add_argument(
        "--recommend-only",
        action="store_true",
        default=True,
        help="Detect + recommend only (default)",
    )
    args = parser.parse_args(argv)

    if args.apply_ps7:
        return apply_ps7()

    # Prefer UTF-8 console output on Windows so Chinese recommendations are readable.
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

    report = build_report(probe=args.probe)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(format_human_report(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
