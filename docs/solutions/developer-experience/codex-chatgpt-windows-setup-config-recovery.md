---
title: "Codex (ChatGPT Desktop) 更新后 Windows 安装失败与对话历史恢复"
date: 2026-07-14
category: developer-experience
module: tooling
problem_type: developer_experience
component: tooling
severity: medium
applies_when:
  - "Codex/ChatGPT Desktop 自动更新后启动报错"
  - "Windows 沙箱初始化卡在'完成设置'界面"
  - "更新后对话历史列表为空"
  - "config.toml 包含自定义 provider 或 trusted_projects"
tags:
  - codex
  - chatgpt
  - windows-setup
  - config-toml
  - session-recovery
  - troubleshooting
---

# Codex (ChatGPT Desktop) 更新后 Windows 安装失败与对话历史恢复

## Context

2026-07-14 OpenAI 将 Codex Desktop 自动更新并改名为 ChatGPT Desktop。更新后应用启动弹窗 "Windows 安装未完成"，点击"完成设置"无响应。社区（linux.do）有多个用户遇到同类问题。修复后对话历史丢失，需手动重建索引。

## Guidance

### 问题 1: Windows 安装未完成

**根因**: 新版本 ChatGPT 的 Windows sandbox 初始化对 `config.toml` 更严格。特定配置项 (`[trusted_projects]`、`model_provider = "custom"`) 在初始化阶段触发 sandbox ACL 配置，导致 setup 卡死。

**修复步骤**:

1. 备份并删除 config.toml，让应用重新生成默认配置:

```bash
cp ~/.codex/config.toml ~/.codex/config.toml.bak
rm ~/.codex/config.toml
```

2. 重启 ChatGPT → 点击"完成设置" → 应用正常进入

3. 逐步加回配置，每批测试一次:

| 批次 | 内容 | 结果 |
|------|------|------|
| 1 | 插件 + 桌面设置 | 安全 |
| 2 | MCP 服务器 (playwright, tavily 等) | 安全 |
| 3 | marketplace entries | 安全 |
| 4 | `[trusted_projects]` | 卡住 |
| 5 | `model_provider = "custom"` (初始化前) | 卡住 |
| 6 | `model_provider = "custom"` (初始化后) | 安全 |

**关键规则**:
- `[trusted_projects]` 不要在 config.toml 里手动写——通过 ChatGPT UI 的"信任的项目"入口添加
- 自定义 provider 必须等 Windows 初始化完成（应用能正常启动）后再加回

### 问题 2: 对话历史消失

**根因**: `~/.codex/session_index.jsonl` 损坏——磁盘上有 24 个会话文件但索引仅 11 条。

**修复脚本** (Python):

```python
import json, os, glob
from datetime import datetime, timezone

sessions_dir = os.path.expanduser(r"~\.codex\sessions")
session_files = glob.glob(os.path.join(sessions_dir, "**/*.jsonl"), recursive=True)

entries = []
for f in sorted(session_files, key=os.path.getmtime, reverse=True):
    sid, thread_name = "", ""
    with open(f, "r", encoding="utf-8") as fh:
        for line in fh:
            msg = json.loads(line.strip())
            # 兼容新旧 session_meta 格式
            if msg.get("type") == "session_meta":
                pl = msg.get("payload", {})
                sid = pl.get("session_id") or pl.get("id", "")
            # 提取第一个非系统用户消息作为标题
            if msg.get("type") == "response_item":
                pl = msg.get("payload", {})
                if pl.get("role") == "user" and not thread_name:
                    for c in pl.get("content", []):
                        t = c.get("text", "")
                        if t and not t.startswith("# AGENTS.md") and not t.startswith("<") and len(t) > 3:
                            thread_name = t.strip()[:100].replace("\n", " ")
                            break
            if sid and thread_name:
                break
    if not sid:
        continue
    if not thread_name:
        thread_name = f"会话 {sid[:8]}"
    mtime = os.path.getmtime(f)
    updated_at = datetime.fromtimestamp(mtime, tz=timezone.utc).isoformat()
    entries.append({"id": sid, "thread_name": thread_name, "updated_at": updated_at})

index_path = os.path.expanduser(r"~\.codex\session_index.jsonl")
with open(index_path, "w", encoding="utf-8") as out:
    for e in entries:
        out.write(json.dumps(e, ensure_ascii=False) + "\n")

print(f"重建完成: {len(entries)} 个会话")
```

重建后用 codex++ 的"立刻修复历史会话"恢复显示。

## Why This Matters

- ChatGPT 的 sandbox 初始化在 config.toml 解析阶段就可能失败，但错误提示不明确——"Windows 安装未完成"实际是配置解析阻塞了 sandbox setup
- 直接卸载重装会丢失所有自定义配置和会话历史——备份 config.toml 后删除重建是更安全的方案
- `session_index.jsonl` 是会话列表的唯一索引——损坏后应用无法枚举历史会话，但原始数据文件完好

## When to Apply

- ChatGPT Desktop 自动更新后首次启动闪退或卡在 setup 界面
- 更新后对话历史列表为空，但 `~/.codex/sessions/` 目录文件正常
- 手动添加过 `[trusted_projects]` 或自定义 model_provider 后应用无法启动
- 更新后重新安装 Codex 命令行工具后出现异常

## Examples

### 配置排查记录

```
干净 config → ✓ 启动正常
+ 所有插件    → ✓ 正常
+ MCP 服务器  → ✓ 正常
+ marketplace → ✓ 正常
+ trusted_projects → ✗ 卡住
+ custom provider (初始化前) → ✗ 卡住
+ custom provider (初始化后) → ✓ 正常
```

### 会话历史索引重建

```
修复前: session_index.jsonl 11 条 / 24 个文件 → codex++ 找到 0 条
修复后: session_index.jsonl 23 条 / 24 个文件 → codex++ 找到 23 条
```

## Related

- linux.do 社区讨论: https://linux.do/t/topic/2555857 — config.toml 导致 Windows setup 失败
- linux.do 社区讨论: https://linux.do/t/topic/2577788 — model_verbosity 参数错误
- 备份文件: `~/.codex/config.toml.bak` — 更新前的完整配置
