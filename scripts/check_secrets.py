#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""扫描工作区里的明文凭证：脚本里不该出现硬编码的密码/token。

与 AGENTS.md 第 9 条的 `git diff` 扫描互补——那条只看**将要提交的 diff**，
这条看**工作区**，所以未 `git add` 的脚本（例如曾经的 `nas_product_visuals/nas_cmd.py`）
也能被抓到。

用法:
  uv run python scripts/check_secrets.py            # 扫全仓库工作区
  uv run python scripts/check_secrets.py --path .   # 指定目录
  uv run python scripts/check_secrets.py --include-tests
  uv run python scripts/check_secrets.py --quiet    # 只报错，不打进度

退出码：发现即 1。
"""
from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

SKIP_DIRS = {
    ".git",
    ".claude",  # worktrees/ 下有上百份完整 checkout
    ".venv",
    "venv",
    "node_modules",
    "__pycache__",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    "out",
    "data",
    "dist",
    "build",
}

MAX_BYTES = 2 * 1024 * 1024  # 超大文件（打包 JSON 等）跳过，避免拖垮扫描

SCAN_SUFFIXES = {
    ".py",
    ".sh",
    ".bash",
    ".zsh",
    ".ps1",
    ".js",
    ".mjs",
    ".cjs",
    ".ts",
    ".ipynb",
    ".cfg",
    ".ini",
    ".yaml",
    ".yml",
    ".toml",
    ".json",
}

# key 名字里出现这些词，就要求它的值不能是字面量
SECRET_KEY_TOKENS = ("pass", "pwd", "secret", "token", "apikey", "api_key", "credential")

# 这些后缀说明值是位置/名字，不是密钥本体
NON_SECRET_KEY_SUFFIXES = ("_path", "_file", "_dir", "_name", "_url", "_header", "_env")

# 模板文件名（要入库的示例），不是真凭证文件
TEMPLATE_SUFFIXES = (".example", ".sample", ".template", ".dist")

# 出现这些说明值是从环境/配置取的，不是硬编码
INDIRECT = re.compile(r"getenv|environ|env\[|settings|\.get\(|load_dotenv|input\(|argv|\$\{")

_PLACEHOLDER_WORDS = (
    "test",
    "dummy",
    "fake",
    "sample",
    "example",
    "placeholder",
    "your",
    "replace_me",
    "changeme",
    "redact",
)

ASSIGN = re.compile(r"""(?i)([A-Za-z_][A-Za-z0-9_]*)\s*[:=]\s*(['"])([^'"\n]{6,})\2""")
SSHPASS = re.compile(r"""(?i)sshpass\s+-p\s*['"]?([^\s'"]{4,})""")
PRIVATE_KEY = re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")
ENVISH = re.compile(r"^[A-Z][A-Z0-9_]{3,}$")


def _is_placeholder(value: str) -> bool:
    v = value.strip()
    low = v.lower()
    if not low:
        return True
    if set(v) <= {"*", "x", "X"}:  # xxxxx / ****
        return True
    if low in {"none", "null", "nil", "todo", "..."}:
        return True
    if low.startswith(("<", "{{", "${", "%", "{", "$")):  # <fill-me> / {{var}} / ${VAR} / %s
        return True
    if low.startswith("x-") and any(tok in low for tok in SECRET_KEY_TOKENS):
        return True  # HTTP 头名，例如 x-tongtool-secret-key
    return any(low.startswith(w) for w in _PLACEHOLDER_WORDS)


def _key_is_secret(key: str) -> bool:
    k = key.lower()
    if any(k.endswith(s) for s in NON_SECRET_KEY_SUFFIXES):
        return False
    return any(tok in k for tok in SECRET_KEY_TOKENS)


@dataclass(frozen=True)
class Finding:
    path: str
    line: int
    kind: str
    detail: str

    def __str__(self) -> str:
        return f"{self.path}:{self.line}: [{self.kind}] {self.detail}"


def scan_text(text: str, path: str = "<text>", *, scan_tests: bool = True) -> list[Finding]:
    """纯函数，方便单测。path 只用于报位置。"""
    if not scan_tests and _is_test_path(path):
        return []
    out: list[Finding] = []
    for n, line in enumerate(text.splitlines(), start=1):
        if PRIVATE_KEY.search(line):
            out.append(Finding(path, n, "private-key", "内联私钥"))
            continue
        if INDIRECT.search(line):
            continue
        m = SSHPASS.search(line)
        if m and not _is_placeholder(m.group(1)):
            out.append(Finding(path, n, "sshpass", f"明文密码 {_mask(m.group(1))}"))
            continue
        for km in ASSIGN.finditer(line):
            key, value = km.group(1), km.group(3)
            if not _key_is_secret(key):
                continue
            if ENVISH.match(value) or _is_placeholder(value):
                continue
            if any(tok in value.lower() for tok in SECRET_KEY_TOKENS):
                continue  # 值本身就是个标签（x-tongtool-secret-key），不是密钥
            out.append(Finding(path, n, "literal", f"{key} = {_mask(value)}"))
    return out


def _is_test_path(path: str) -> bool:
    p = Path(path)
    name = p.name.lower()
    return (
        any(part.lower() == "tests" for part in p.parts)
        or name.startswith("test_")
        or name.endswith("_test.py")
    )


def _mask(v: str, head: int = 2) -> str:
    v = v.strip()
    if len(v) <= head + 2:
        return "*" * len(v)
    return v[:head] + "*" * (len(v) - head)


def iter_files(root: Path, *, include_tests: bool):
    """os.walk + 原地剪枝；rglob 会走进 .git/.venv 再过滤，太慢。"""
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if d not in SKIP_DIRS)
        for name in sorted(filenames):
            p = Path(dirpath) / name
            if p.suffix.lower() not in SCAN_SUFFIXES:
                continue
            if not include_tests and _is_test_path(str(p.relative_to(root))):
                continue
            try:
                if p.stat().st_size > MAX_BYTES:
                    continue
            except OSError:
                continue
            yield p


def _is_git_ignored(root: Path, rel: str) -> bool:
    """被 gitignore 的文件不报（secrets/、.codex_tmp/ 本来就该放东西）。

    逐文件问 git；不要预先把 `git ls-files --others --ignored` 收成集合——它不进
    嵌套仓库（`.codex_tmp/xxx/` 若是另一个 clone 就整片漏掉）。
    """
    try:
        r = subprocess.run(
            ["git", "check-ignore", "-q", rel], cwd=root, capture_output=True, timeout=30
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return r.returncode == 0


def _tracked_files(root: Path) -> set[str]:
    try:
        r = subprocess.run(
            ["git", "ls-files", "-z"], cwd=root, capture_output=True, timeout=60
        )
    except (OSError, subprocess.SubprocessError):
        return set()
    if r.returncode != 0:
        return set()
    return {p for p in r.stdout.decode("utf-8", errors="replace").split("\0") if p}


def unignored_env_files(root: Path) -> list[str]:
    """捞出既没被 gitignore、也没被 git 跟踪的 `.env*`（例如 `.env.bak`）。

    `.env.example` 这类模板是要入库的（tracked），不算问题。
    """
    tracked = _tracked_files(root)
    hits = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if d not in SKIP_DIRS)
        for name in sorted(filenames):
            if not name.startswith(".env"):
                continue
            if name.lower().endswith(TEMPLATE_SUFFIXES):
                continue  # .env.example 这类模板要入库
            p = Path(dirpath) / name
            rel = p.relative_to(root).as_posix()
            if rel in tracked:
                continue
            try:
                r = subprocess.run(
                    ["git", "check-ignore", "-q", rel],
                    cwd=root,
                    capture_output=True,
                    timeout=30,
                )
            except (OSError, subprocess.SubprocessError):
                continue
            if r.returncode != 0:
                hits.append(rel)
    return hits


def main() -> None:
    ap = argparse.ArgumentParser(description="扫描明文凭证")
    ap.add_argument("--path", default=str(ROOT), help="要扫的根目录")
    ap.add_argument("--include-tests", action="store_true", help="连 tests/ 一起扫（默认跳过，测试常含假密钥）")
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()

    root = Path(args.path).resolve()
    findings: list[Finding] = []
    scanned = 0
    for p in iter_files(root, include_tests=args.include_tests):
        rel = p.relative_to(root).as_posix()
        try:
            text = p.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        scanned += 1
        hits = scan_text(text, rel, scan_tests=args.include_tests)
        if hits and not _is_git_ignored(root, rel):
            findings.extend(hits)

    for rel in unignored_env_files(root):
        findings.append(Finding(rel, 0, "env-not-ignored", "疑似凭证文件且未被 .gitignore 排除"))

    if findings:
        print(f"发现 {len(findings)} 处疑似明文凭证（扫了 {scanned} 个文件）：\n")
        for f in findings:
            print(f"  {f}")
        print("\n改法：把值挪到 .env（.env 已被 gitignore），脚本里用 os.getenv / 模块 env loader 读。")
        print("详见 AGENTS.md 第 9 条与 CONTRIBUTING.md 安全检查章节。")
        sys.exit(1)

    if not args.quiet:
        print(f"OK: 扫了 {scanned} 个文件，没有明文凭证。")


if __name__ == "__main__":
    main()
