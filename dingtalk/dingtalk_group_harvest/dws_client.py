# -*- coding: utf-8 -*-
"""DWS CLI 子进程封装。所有读取都走用户 OAuth 身份，不存任何凭证。"""
from __future__ import annotations

import json
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence

from .paths import dws_exe


class DwsError(RuntimeError):
    """DWS 调用失败，自带命令与原始输出，便于报告里追溯。"""

    def __init__(self, message: str, *, argv: Sequence[str] | None = None, stdout: str = "", stderr: str = ""):
        super().__init__(message)
        self.argv = list(argv or [])
        self.stdout = stdout
        self.stderr = stderr


class DwsAuthError(DwsError):
    pass


class DwsIncompleteError(DwsError):
    pass


@dataclass
class DwsResult:
    argv: list[str]
    returncode: int
    stdout: str
    stderr: str


def run_dws(
    args: Sequence[str],
    *,
    cwd: Path | str | None = None,
    timeout: int = 600,
    retries: int = 2,
) -> DwsResult:
    argv = [dws_exe(), *args]
    last: DwsResult | None = None
    for attempt in range(retries + 1):
        try:
            proc = subprocess.run(
                argv,
                cwd=str(cwd) if cwd else None,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout,
            )
        except subprocess.TimeoutExpired as exc:
            last = DwsResult(argv, 124, exc.stdout or "", exc.stderr or "timeout")
        else:
            last = DwsResult(argv, proc.returncode, proc.stdout, proc.stderr)
            if proc.returncode == 0:
                return last
        if attempt < retries:
            time.sleep(2 ** attempt)
    assert last is not None
    return last


def parse_json(stdout: str, stderr: str = "") -> dict[str, Any]:
    text = (stdout or "").strip()
    if not text:
        raise DwsError("DWS 没有返回 JSON", stdout=stdout, stderr=stderr)
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        start, end = text.find("{"), text.rfind("}")
        if start < 0 or end <= start:
            raise DwsError("DWS 输出不是 JSON", stdout=stdout, stderr=stderr)
        try:
            data = json.loads(text[start : end + 1])
        except json.JSONDecodeError as exc:
            raise DwsError(f"DWS JSON 解析失败: {exc}", stdout=stdout, stderr=stderr)
    if not isinstance(data, dict):
        raise DwsError("DWS 返回的 JSON 顶层不是对象", stdout=stdout, stderr=stderr)
    if data.get("error"):
        err = data["error"]
        message = err.get("message") if isinstance(err, dict) else str(err)
        raise DwsError(message or "DWS 返回 error", stdout=stdout, stderr=stderr)
    return data


def run_json(
    args: Sequence[str],
    *,
    cwd: Path | str | None = None,
    timeout: int = 600,
    retries: int = 2,
) -> dict[str, Any]:
    result = run_dws(args, cwd=cwd, timeout=timeout, retries=retries)
    if result.returncode != 0:
        try:
            data = parse_json(result.stdout, result.stderr)
        except DwsError:
            raise DwsError(
                f"DWS 退出码 {result.returncode}",
                argv=result.argv,
                stdout=result.stdout,
                stderr=result.stderr,
            )
        if data.get("error"):
            raise DwsError(
                str(data["error"].get("message", data["error"])),
                argv=result.argv,
                stdout=result.stdout,
                stderr=result.stderr,
            )
        raise DwsError(
            f"DWS 退出码 {result.returncode}",
            argv=result.argv,
            stdout=result.stdout,
            stderr=result.stderr,
        )
    return parse_json(result.stdout, result.stderr)


def read_output(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise DwsError(f"DWS 没有生成输出文件: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def auth_status() -> dict[str, Any]:
    return run_json(["auth", "status"])


def ensure_auth() -> dict[str, Any]:
    status = auth_status()
    if not status.get("authenticated") or not status.get("token_valid"):
        raise DwsAuthError(
            "DWS 登录态无效。先在交互终端运行 `dws auth login` 并扫码，再重跑。"
        )
    return status


def validate_complete(data: dict[str, Any], operation: str) -> None:
    failures = data.get("failures") or []
    if data.get("complete") is False or data.get("hasMore") or failures:
        detail = f"{operation} 结果不完整"
        if failures:
            detail += f"，失败项 {len(failures)} 个"
        raise DwsIncompleteError(detail)
