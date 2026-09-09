---
title: 赛狐 Apifox API 文档本地镜像刷新与对账
date: 2026-09-09
category: conventions
module: SELLFOX_API
problem_type: convention
component: development_workflow
severity: medium
applies_when:
  - "怀疑赛狐 OpenAPI / Apifox 文档有更新"
  - "需要刷新 SELLFOX_API/docs/api-reference 本地镜像"
  - "新 Agent 要找赛狐 API 端点 Markdown 从哪来、怎么更新"
tags:
  - sellfox
  - apifox
  - api-docs
  - mirror
  - download_docs
  - llms-txt
  - documentation
related_components:
  - tooling
---

# 赛狐 Apifox API 文档本地镜像刷新与对账

## Context

赛狐开放平台 API 文档托管在密码保护的 Apifox 共享站 `sellfoxapi.apifox.cn`。项目在 `SELLFOX_API/docs/api-reference/` 维护一份离线 Markdown 镜像（按模块三级目录 + `llms.txt` 索引），供 Agent 查端点 schema，避免每次上网。

2026-07-01 首次全量镜像约 **419** 端点。2026-09-09 对照线上索引发现文档侧确有持续更新（对方曾口头称「API 在加紧更新」）。本地旧「更新公告」止于 2026-06-25；线上公告已含 7/8/9 月条目，最新到 **2026-09-07**。索引对账：**419 → 443**（+25 / −1 / 17 标题变更）。

WebFetch / URL 带 `?password=` **过不了** Apifox 交互式密码门；必须用浏览器登录拿 Cookie，再跑 `download_docs.py`。

## Guidance

### 找文档

1. 入口：[`SELLFOX_API/AGENT_HANDOFF.md`](../../../SELLFOX_API/AGENT_HANDOFF.md) → `docs/api-reference/<模块>/`
2. 索引：`docs/api-reference/llms.txt`（可 grep）
3. 刷新操作手册（OKF Reference）：[`SELLFOX_API/docs/reference/api-docs-mirror.md`](../../../SELLFOX_API/docs/reference/api-docs-mirror.md)

### 刷新标准流程

1. 确认本机 `.env` 有 `SELLFOX_API_DOC_KEY`（勿写入仓库）。
2. 浏览器登录 Apifox → Cookie 写入 `docs/api-reference/cookie.txt`（gitignore）。
3. 先 diff 新 `llms.txt` 与「更新公告」，再决定是否全量。
4. 有变化时：

```bash
uv run python SELLFOX_API/download_docs.py --all --force --delay 0.25
```

5. 清理改名孤儿 `.md`；更新 `docs/log.md`、端点计数；`uv run python scripts/update_index.py`。

### 隐私

- 文档/PR/Skill/log **禁止**明文密码、Cookie、`apifox-auth-key`。
- `cookie.txt`、`download_log.json`、`llms_parsed.json` 已在 `.gitignore`。

### 能力边界

镜像刷新只回答「**文档**是否更新」。接口行为与文档不一致时，另做 API 实测。

## Why This Matters

- 过期镜像会让 Agent 按已下线或即将下线接口写集成（例如备货/FBA 1.0 → 2.0、利润 V2、多平台售后）。
- 先索引 diff 再全量，避免无意义的数百次下载。
- 密码曾误写入 `docs/log.md` 历史行；刷新流程必须把密钥留在 `.env`，并清理历史明文。

## When to Apply

- 赛狐人员提示 API/文档在更新，或业务调用出现「文档与实装不符」。
- 新开对话需要确认本地 `api-reference` 是否可信。
- 修改 `download_docs.py` 或端点计数文档时。

## Examples

### 2026-09-09 对账摘要（可复查）

| 项 | 值 |
|----|-----|
| 旧唯一端点 | 419 |
| 新唯一端点 | 443 |
| 新增示例 | 采购变更列表/详情、海外仓备货 2.0、FBA 发货单 2.0、三方仓库存、多平台售后列表、请款池其他费用 V2 |
| 删除示例 | 仓库「创建调整单」（旧灰度路径，标题迁移） |
| 官方公告最新 | 2026-09-07（批次入库负库存调整字段等） |
| 全量下载 | 443/443 成功；`download_docs.py` 增加 `--force` |

### 错误示范 → 正确示范

| 错误 | 正确 |
|------|------|
| WebFetch 带 password query | 浏览器交互登录拿 Cookie |
| 无 `--force` 以为已更新 | 已存在文件会被 skip；覆盖需 `--force` |
| 把密码写进 `log.md` | 只写「密钥在 `.env` 的 `SELLFOX_API_DOC_KEY`」 |

## Related

- [`SELLFOX_API/docs/reference/api-docs-mirror.md`](../../../SELLFOX_API/docs/reference/api-docs-mirror.md) — OKF 操作手册
- [`SELLFOX_API/docs/research/2026-06-25-sellfox-api-exploration.md`](../../../SELLFOX_API/docs/research/2026-06-25-sellfox-api-exploration.md) — 初次探索
- [`docs/solutions/documentation-gaps/unverified-external-api-claims-in-docs.md`](../documentation-gaps/unverified-external-api-claims-in-docs.md) — 外部 API 声明须对照官方文档
- [`docs/solutions/architecture-patterns/sellfox-api-proxy-design.md`](../architecture-patterns/sellfox-api-proxy-design.md) — 代理访问（非文档镜像）
