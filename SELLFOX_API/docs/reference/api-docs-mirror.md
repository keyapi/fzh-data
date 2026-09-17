---
okf: v0.1
type: Reference
title: 赛狐 Apifox API 文档本地镜像刷新
description: 从 sellfoxapi.apifox.cn 拉取 llms.txt 与端点 Markdown 的约定、对账步骤与禁止事项
tags: [sellfox, apifox, api-docs, mirror, download_docs]
resource: SELLFOX_API/download_docs.py
timestamp: 2026-09-09
---

# 赛狐 Apifox API 文档本地镜像刷新

## 文档源与落盘位置

| 项 | 值 |
|----|-----|
| 线上文档站 | `https://sellfoxapi.apifox.cn/` |
| 机器可读索引 | `https://sellfoxapi.apifox.cn/llms.txt` |
| 本地镜像根 | [`SELLFOX_API/docs/api-reference/`](../api-reference/) |
| 下载脚本 | [`SELLFOX_API/download_docs.py`](../../download_docs.py) |
| 更新公告 | [`开发指南/更新公告.md`](../api-reference/开发指南/更新公告.md) |

密码只放在本机 `.env` 的 `SELLFOX_API_DOC_KEY`（gitignore）。**禁止**写入仓库文档、commit、PR、聊天粘贴、log 明文。

## 认证方式（已验证）

1. WebFetch / `?password=` query **无效**（交互式密码门）。
2. 浏览器打开文档站 → 填密码 → 点「访问文档」→ 拿到 Cookie。
3. Cookie 写入 `SELLFOX_API/docs/api-reference/cookie.txt`（gitignore；勿提交）。
4. 用 Cookie 拉 `llms.txt` 与各 `doc-*.md` / `api-*.md`。

## 推荐核对流程（先轻量再全量）

1. 刷新 Cookie（见上）。
2. 拉取新 `llms.txt`，与本地 `llms.txt` 用 `download_docs.parse_llms` 对账：
   - `total_unique` 数量
   - URL 增删
   - 标题 / 路径变更
3. 单独重下「更新公告」，看官方 changelog 是否比本地新。
4. **仅当索引或公告有变化**：

```bash
uv run python SELLFOX_API/download_docs.py --all --force --delay 0.25
```

`--force` 覆盖已存在文件；默认无 `--force` 会 skip 已存在路径（增量补洞）。

5. 删掉改名残留的孤儿 `.md`（期望路径以当前 `llms.txt` 解析结果为准）。
6. 更新 [`docs/log.md`](../log.md)、模块端点计数（HANDOFF / Skill / `docs/index.md`）、跑 `uv run python scripts/update_index.py`。

## 落盘标准

- 按 Apifox 原文 **模块 / 子模块 / 标题.md** 三级落盘（Windows 安全文件名）。
- 内容须为 Markdown（含 OpenAPI YAML），不是 HTML 登录页。
- `?nav=` 去重；以 base URL 为唯一键。

## 隐私与安全

| 允许 | 禁止 |
|------|------|
| 写「密码在 `.env` 的 `SELLFOX_API_DOC_KEY`」 | 明文密码、Cookie、`apifox-auth-key` |
| 对账数字：旧 N → 新 M、增减标题 | 把 `cookie.txt` / `download_log.json` 提交进 git |
| 记录刷新日期与成功率 | 在 PR / log / Skill 复述密钥 |

## 能力边界

本流程只证明 **Apifox 文档是否更新**。若对方「接口已改、文档未发」，还需对具体业务接口实测（不在本脚本默认范围）。

## 相关

- 完整学习记录：[`docs/solutions/conventions/sellfox-apifox-api-docs-mirror-refresh.md`](../../../docs/solutions/conventions/sellfox-apifox-api-docs-mirror-refresh.md)
- Agent 入口：[`AGENT_HANDOFF.md`](../../AGENT_HANDOFF.md)
