"""Fixed dispatcher for web automation capability routing.

Weak-model-safe entrypoint: an agent (or human) runs

    uv run python web_automation/scripts/dispatch.py <task> [--check] [--confirm-scope TXT]

and receives a deterministic status. The dispatcher never guesses a Python
environment or a script path; routing, risk and fallback rules all live in
capabilities.yaml.
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import os
import subprocess
import sys
from pathlib import Path

from web_automation.scripts.runtime import (
    build_script_command,
    classify_failure,
    load_capabilities,
    platform_profile_present,
    run_result_from_output,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
MATRIX_PATH = REPO_ROOT / "web_automation" / "capabilities.yaml"

EXIT_READY = 0
EXIT_EXEC_FAILED = 1
EXIT_BLOCKED = 2
EXIT_NEED_ACTION = 3
NEED_STATUSES = frozenset(
    {"NEED_USER_CONFIRMATION", "NEED_BROWSER", "NEED_OCR", "NEED_LOGIN"}
)


@dataclasses.dataclass(frozen=True)
class RunResult:
    returncode: int
    failure_code: str | None


@dataclasses.dataclass(frozen=True)
class DispatchResult:
    status: str
    task: str
    mode: str
    channel: str | None
    risk: str
    command: tuple[str, ...]
    reason: str


def dispatch(
    task: str,
    *,
    check: bool,
    with_ocr: bool,
    confirm_scope: str | None,
    passthrough: list[str],
    runner: object,
    env_facts: dict[str, object] | None = None,
    profile_present: bool | None = None,
) -> DispatchResult:
    matrix = load_capabilities(MATRIX_PATH)
    if task not in matrix:
        return DispatchResult(
            status="BLOCKED", task=task, mode="?", channel=None, risk="?",
            command=(), reason=f"unknown capability: {task}",
        )
    cap = matrix[task]

    if cap.risk == "write" and not (confirm_scope and confirm_scope.strip()):
        return DispatchResult(
            status="NEED_USER_CONFIRMATION", task=task, mode=cap.mode,
            channel=cap.primary, risk=cap.risk, command=(),
            reason="写操作必须先确认范围：请带 --confirm-scope \"具体文件/SKU/仓库范围\"",
        )

    if cap.primary == "mcp":
        return DispatchResult(
            status="READY", task=task, mode=cap.mode, channel="mcp",
            risk=cap.risk, command=(),
            reason="该任务由 Agent 用 Playwright MCP 探路并闭环验证；不启动 Python 脚本",
        )

    channel = cap.primary
    command = tuple(
        build_script_command(REPO_ROOT, cap, passthrough, channel=channel)
    )
    if check:
        return _check_env(
            cap, command, with_ocr=with_ocr,
            env_facts=env_facts, profile_present=profile_present,
        )

    result: RunResult = runner(command, with_ocr=with_ocr)
    if result.returncode == 0:
        return DispatchResult(
            status="READY", task=task, mode=cap.mode, channel=channel,
            risk=cap.risk, command=command, reason="success",
        )

    # API-first may fall back to browser only for explicitly allowed codes.
    fallback = getattr(cap, "fallback", None)
    if (
        channel == "api"
        and result.failure_code
        and fallback
        and classify_failure(cap, result.failure_code) == "fallback"
    ):
        browser_cmd = tuple(
            build_script_command(REPO_ROOT, cap, passthrough, channel="browser")
        )
        browser_result: RunResult = runner(browser_cmd, with_ocr=with_ocr)
        if browser_result.returncode == 0:
            return DispatchResult(
                status="READY", task=task, mode=cap.mode, channel="browser",
                risk=cap.risk, command=browser_cmd,
                reason=f"api failed ({result.failure_code}); browser fallback ok",
            )
        return DispatchResult(
            status="BLOCKED", task=task, mode=cap.mode, channel="browser",
            risk=cap.risk, command=browser_cmd,
            reason=f"api failed ({result.failure_code}) and browser fallback also failed",
        )

    reason = (
        f"failed on {channel}"
        if result.failure_code is None
        else f"{result.failure_code} on {channel}: 禁止静默回退，需人工处理"
    )
    return DispatchResult(
        status="BLOCKED", task=task, mode=cap.mode, channel=channel,
        risk=cap.risk, command=command, reason=reason,
    )


def _check_env(
    cap,
    command: tuple[str, ...],
    *,
    with_ocr: bool,
    env_facts: dict[str, object] | None,
    profile_present: bool | None,
) -> DispatchResult:
    facts = env_facts
    if facts is None:
        from web_automation.scripts.bootstrap import collect_web_facts

        raw = collect_web_facts(REPO_ROOT)
        facts = {**raw, "env_ready": raw["child_env_ready"]}
    if not facts.get("uv_present", True):
        return DispatchResult(
            status="BLOCKED", task=cap.task, mode=cap.mode, channel=cap.primary,
            risk=cap.risk, command=(), reason="uv not found; install uv first",
        )
    if not facts.get("env_ready") or not facts.get("chromium_ready"):
        return DispatchResult(
            status="NEED_BROWSER", task=cap.task, mode=cap.mode, channel=cap.primary,
            risk=cap.risk, command=command,
            reason="子环境或 Chromium 未就绪：先跑 uv run python web_automation/scripts/bootstrap.py",
        )
    if with_ocr and not facts.get("ocr_ready"):
        return DispatchResult(
            status="NEED_OCR", task=cap.task, mode=cap.mode, channel=cap.primary,
            risk=cap.risk, command=command,
            reason="OCR 未安装：先问用户，需要才 bootstrap --with-ocr",
        )
    present = profile_present
    if present is None:
        present = platform_profile_present(
            cap.platform, REPO_ROOT / "web_automation",
        )
    if not present:
        return DispatchResult(
            status="NEED_LOGIN", task=cap.task, mode=cap.mode, channel=cap.primary,
            risk=cap.risk, command=command,
            reason="尚无持久化登录 profile：先在浏览器里人工登录一次",
        )
    return DispatchResult(
        status="READY", task=cap.task, mode=cap.mode, channel=cap.primary,
        risk=cap.risk, command=command,
        reason=f"route ok (mode={cap.mode}, channel={cap.primary})",
    )


# ---------------------------------------------------------------------------
# CLI orchestration (bootstrap + subprocess)
# ---------------------------------------------------------------------------


def _real_runner(command: tuple[str, ...], *, with_ocr: bool) -> RunResult:
    from web_automation.scripts.bootstrap import collect_web_facts, run_install_commands

    print(">", " ".join(command))
    facts = collect_web_facts(REPO_ROOT)
    facts["env_ready"] = facts["child_env_ready"]
    if run_install_commands(facts, with_ocr) != 0:
        return RunResult(returncode=2, failure_code="BOOTSTRAP_FAILED")
    proc = subprocess.Popen(
        list(command), cwd=REPO_ROOT,
        env={**os.environ, "PYTHONIOENCODING": "utf-8"},
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        text=True, encoding="utf-8", errors="replace",
    )
    chunks: list[str] = []
    assert proc.stdout is not None
    for line in proc.stdout:
        print(line, end="")
        chunks.append(line)
    proc.wait()
    parsed = run_result_from_output(proc.returncode or 0, "".join(chunks))
    return RunResult(parsed.returncode, parsed.failure_code)


def _cli_exit_code(result: DispatchResult) -> int:
    if result.status == "READY":
        return EXIT_READY
    if result.status in NEED_STATUSES:
        return EXIT_NEED_ACTION
    return EXIT_BLOCKED


def _split_passthrough(argv: list[str]) -> tuple[list[str], list[str]]:
    """Return (own_args, passthrough_after_double_dash)."""
    if "--" in argv:
        idx = argv.index("--")
        return argv[:idx], argv[idx + 1:]
    return argv, []


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="dispatch.py",
        description="web_automation capability dispatcher",
    )
    parser.add_argument("task", help="capability task, e.g. sellfox.stock.export")
    parser.add_argument("--check", action="store_true", help="report route state only")
    parser.add_argument("--with-ocr", action="store_true", help="allow OCR login")
    parser.add_argument("--confirm-scope", help="required for write tasks")
    parser.add_argument("--json", action="store_true", help="machine-readable output")
    own, passthrough = _split_passthrough(list(argv or sys.argv[1:]))
    args = parser.parse_args(own)

    result = dispatch(
        args.task,
        check=args.check,
        with_ocr=args.with_ocr,
        confirm_scope=args.confirm_scope,
        passthrough=passthrough,
        runner=_real_runner,
    )

    if args.json:
        print(json.dumps(dataclasses.asdict(result), ensure_ascii=False))
    else:
        print(f"status={result.status}")
        if result.reason:
            print(f"reason={result.reason}")
        if result.command:
            print("command=" + " ".join(result.command))
    return _cli_exit_code(result)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    raise SystemExit(main())
