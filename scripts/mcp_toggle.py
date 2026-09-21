#!/usr/bin/env python3
"""启用/停用 Claude Desktop 3P 配置里的 MCP server，保留配置不删除。

停用 = 把条目从 `mcpServers` 移到 `_disabled_mcpServers`（Claude Desktop 只读
`mcpServers`，未知的顶层键直接忽略）。启用 = 挪回去。
两者都需要**重启 Claude Desktop** 才生效；OAuth token 不受影响。

Usage:
  uv run python scripts/mcp_toggle.py                      # 查看当前状态
  uv run python scripts/mcp_toggle.py notion-company off   # 停用（保留配置）
  uv run python scripts/mcp_toggle.py notion-company on    # 启用
  uv run python scripts/mcp_toggle.py --normal             # 改普通模式配置
  uv run python scripts/mcp_toggle.py --config <path>      # 指定配置文件
"""

import argparse
import json
import os
import shutil
import sys
from datetime import datetime
from pathlib import Path

# Windows 控制台默认 cp936，中文会乱码；强制 UTF-8 输出。
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8")

ACTIVE = "mcpServers"
DISABLED = "_disabled_mcpServers"


def find_config(explicit: str | None, normal: bool) -> Path:
    if explicit:
        p = Path(explicit).expanduser()
        if not p.is_file():
            sys.exit(f"配置文件不存在: {p}")
        return p

    local = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~/AppData/Local")
    sub = "Claude" if normal else "Claude-3p"
    pattern = f"Packages/Claude_*/LocalCache/Roaming/{sub}/claude_desktop_config.json"
    found = sorted(Path(local).glob(pattern))
    if not found:
        sys.exit(f"找不到配置（{sub} 模式），请用 --config 指定路径\n查找模式: {local}/{pattern}")
    if len(found) > 1:
        print(f"⚠ 匹配到 {len(found)} 个配置，使用第一个: {found[0]}")
    return found[0]


def load(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        sys.exit(f"配置文件不是合法 JSON，未做任何改动: {e}")


def save(path: Path, doc: dict) -> None:
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    bak = Path(f"{path}.bak-{stamp}")
    shutil.copy2(path, bak)
    print(f"已备份 → {bak.name}")

    path.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    json.loads(path.read_text(encoding="utf-8"))  # 回读校验
    print("已写入并通过 JSON 校验")


def show_status(path: Path, doc: dict) -> None:
    active = list(doc.get(ACTIVE, {}))
    disabled = list(doc.get(DISABLED, {}))
    print(f"配置文件: {path}\n")
    print(f"已启用 ({len(active)}):")
    for name in active:
        print(f"  + {name}")
    if not active:
        print("  (无)")
    print(f"\n已停用但保留 ({len(disabled)}):")
    for name in disabled:
        print(f"  - {name}")
    if not disabled:
        print("  (无)")


def toggle(doc: dict, name: str, enable: bool) -> bool:
    src, dst = (DISABLED, ACTIVE) if enable else (ACTIVE, DISABLED)

    if name in doc.get(ACTIVE, {}) and name in doc.get(DISABLED, {}):
        sys.exit(f"'{name}' 同时存在于启用区和停用区，请手动检查配置")

    if name not in doc.get(src, {}):
        if name in doc.get(dst, {}):
            print(f"'{name}' 已处于{'启用' if enable else '停用'}状态，无需操作")
            return False
        known = sorted(set(doc.get(ACTIVE, {})) | set(doc.get(DISABLED, {})))
        sys.exit(f"找不到 server '{name}'\n可用的: {', '.join(known) or '(无)'}")

    entry = doc[src].pop(name)
    doc.setdefault(dst, {})[name] = entry
    print(f"已{'启用' if enable else '停用'} '{name}'")
    return True


def main() -> None:
    ap = argparse.ArgumentParser(
        description="启用/停用 Claude Desktop 配置里的 MCP server（保留配置不删除）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument("name", nargs="?", help="server 名称，如 notion-company")
    ap.add_argument("action", nargs="?", choices=["on", "off"], help="on=启用 / off=停用")
    ap.add_argument("--config", help="直接指定 claude_desktop_config.json 路径")
    ap.add_argument("--normal", action="store_true", help="改普通模式配置（默认 3P 模式）")
    args = ap.parse_args()

    path = find_config(args.config, args.normal)
    doc = load(path)

    if args.name is None:
        show_status(path, doc)
        return

    if args.action is None:
        sys.exit("需要指定动作: on 或 off（例: mcp_toggle.py notion-company off）")

    changed = toggle(doc, args.name, args.action == "on")
    if not changed:
        return

    save(path, doc)
    print("\n" + "=" * 60)
    print("⚠ 完全退出 Claude Desktop（托盘 → Quit）再打开才生效")
    print("  MCP 不热加载；OAuth token 不受影响，无需重新授权")
    print("=" * 60)


if __name__ == "__main__":
    main()
