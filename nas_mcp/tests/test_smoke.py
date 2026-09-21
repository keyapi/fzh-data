#!/usr/bin/env python3
"""nas_mcp 只读冒烟测试（会真的连 NAS，但只读）。

用法（在仓库根执行）：
    uv run python nas_mcp/tests/test_smoke.py

需要 NAS_API/.env 里的 NAS_URL / NAS_USERNAME / NAS_PASSWORD（脚本会加载它）。
不会写入 NAS 任何内容。
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

# 加载 NAS 凭证（与 NAS_API 同一份 .env）。
# 注意：凭证在**父仓库**里，worktree 内通常没有 —— 两处都找。
candidates = [REPO / "NAS_API" / ".env"]
try:
    parent_repo = Path(__file__).resolve().parents[5]   # <repo>/.claude/worktrees/<wt>/nas_mcp/tests/x.py
    if (parent_repo / "NAS_API" / ".env").is_file():
        candidates.append(parent_repo / "NAS_API" / ".env")
except IndexError:
    pass
env_file = next((p for p in candidates if p.is_file()), None)
if env_file:
    print(f"[env] 使用 {env_file}")
    for line in env_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))
else:
    print("[env] 未找到 NAS_API/.env —— 只跑离线护栏检查")

os.environ.setdefault("NAS_MCP_TOKEN", "test-token")

sys.path.insert(0, str(REPO / "nas_mcp"))
import server as S  # noqa: E402

ok = fail = 0


def check(label: str, cond: bool, extra: str = "") -> None:
    global ok, fail
    if cond:
        ok += 1
        print(f"  PASS  {label} {extra}")
    else:
        fail += 1
        print(f"  FAIL  {label} {extra}")


print(f"ROOT = {S.ROOT}\n")

print("── 1) 路径护栏（越界必须被拒）")
for bad in ["/etc/passwd", "/FZH共享文件夹/../../etc", "/其他共享文件夹", "/FZH共享文件夹X/x"]:
    try:
        S.safe_path(bad)
        check(f"拒绝 {bad}", False, "← 竟然放行了！")
    except S.PathDenied:
        check(f"拒绝 {bad}", True)
check("放行根目录", S.safe_path("") == S.ROOT, f"-> {S.safe_path('')}")
check("放行子目录", S.safe_path("B-部门负责人共享").startswith(S.ROOT))

print("\n── 2) nas_health")
h = S.tool_health({})
check("available=True", h.get("available") is True, str(h))

print("\n── 3) nas_list_folder")
r = S.tool_list({"limit": 5})
check("返回条目", r.get("count", 0) > 0, f"count={r.get('count')}")
names = [i["name"] for i in r.get("items", [])]
check("拿到名字", len(names) > 0, str(names[:4]))

print("\n── 4) nas_file_info")
if names:
    info = S.tool_info({"path": f"{S.ROOT}/{names[0]}"})
    check("查到条目", not info.get("not_found"), str(info)[:120])

print("\n── 5) nas_read_text 的护栏（不该读的不读）")
# 找一个目录：读它必须被拒
dirs = [i for i in r.get("items", []) if i.get("is_dir")]
if dirs:
    try:
        S.tool_read_text({"path": dirs[0]["path"]})
        check("目录不可被 read_text", False, "← 竟然读了目录")
    except ValueError as e:
        check("目录不可被 read_text", "文件夹" in str(e), f"({e})")
# 非白名单扩展名必须被拒
try:
    S.tool_read_text({"path": f"{S.ROOT}/x.exe"})
    check("非文本扩展名被拒", False, "← 竟然放行")
except ValueError as e:
    check("非文本扩展名被拒", "白名单" in str(e) or "不存在" in str(e), f"({e})")

print("\n── 6) tools/list 只含只读工具")
tool_names = [t["name"] for t in S.TOOLS]
check("无写/删工具",
      not any(w in n for n in tool_names for w in ("delete", "create", "move", "upload", "write")),
      str(tool_names))

print(f"\n结果：{ok} passed, {fail} failed")
sys.exit(1 if fail else 0)
