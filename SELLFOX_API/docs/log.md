---
okf: v0.1
type: Log
title: SELLFOX_API 变更日志
description: 赛狐 API 模块的所有变更记录
tags: [sellfox, saihu, API]
timestamp: 2026-07-02
---

# 变更日志

## 2026-08-20

- **变更描述（hardening）**：dry-run 把赛狐名称不一致标为 `mismatch`；同 SKU 多条标 `blocked_duplicate`；`--child` 非法数量/缺冒号报错不静默丢弃；EN 空 `new_item_code_name` 标 `blocked_en`。
- **变更描述（#185）**：SKILL 瘦身；`AGENT_HANDOFF.md` 新增组合章节；更新 workflow 生产记录。
- **变更描述（OKF 四层对齐）**：`combo-ops.md` 升格为稳定操作手册；HANDOFF 组合章节收成热区（冻结 + 读哪）；Skill Read First 改为 combo-ops → HANDOFF 热区。

## 2026-08-19

- **变更描述**: 增加 EN Product Bundle ↔ 赛狐组合商品对账命令 `sync-combos`、EN `en-preview`/`en-create`（只传 items）、创建后程序化回读断言，以及纯逻辑测试。同事 Agent 默认走 Skill `sellfox-combo-create`，禁止无范围全量和 PUT 改组成。


## v0.2 — 2026-07-02: API 实战验证 + 新脚本

- 创建 `fetch_ad_reports.py` — 纯 stdlib 脚本，通过赛狐 OpenAPI 拉取 4 种 SP 广告报告
- 使用新账号 (App ID: 368684) 成功完成端到端测试：认证 → 店铺列表 → 创建任务 → 轮询 → 下载
- 发现并记录 6 条新集成教训（编码、文件格式、参数、状态、URL、限流），更新到 `lessons/2026-06-25-sellfox-integration-lessons.md` (10→16 条)
- 凭证标准化：新建 `SELLFOX_API/.env` (gitignored)，脚本优先读此路径
- 关键发现：`requests` 库在中文 Windows 下签名失败，全部改用 `urllib`

## v0.3 — 2026-07-02: 全量报告拉取 + 字段定义文档

- 新增 `fetch_ad_reports.py` — SP 4 种核心报告 (Campaign/Targeting/SearchTerm/Placement)，支持 `--shop`/`--days`/`--shop-name`
- 新增 `fetch_extra_reports.py` — SP 额外 3 种报告 (AdGroup/AdProduct/PurchasedItem)
- 新增 `fetch_sb_sd_reports.py` — SB 7 种 + SD 5 种全量报告
- BJRYECLTD-US (id=596841) June 2026: 成功拉取 20 个报告 (SP 8 + SB 7 + SD 5), 2,337 行 SP 数据
- 确认 SB/SD 投放极少: SB 全部空数据, SD 仅 1 个 VCPM 再营销 campaign
- 列名映射: `advertise/docs/reference/sp-report-column-reference.md` (SP 162 字段) + `sb-sd-report-column-reference.md` (SB+SD 419 字段)
- 新增 `amazon-official-docs/` 归档: 18 个 SP 来源 + 12 个 SB/SD 来源交叉验证

## v0.1 — 2026-07-01: 初始创建

- 从 `advertise/docs/sellfox-api/` 独立为根目录 `SELLFOX_API/`
- 用 Playwright 浏览器自动化从 `sellfoxapi.apifox.cn` 下载全部 419 个 API .md 文档
- 文档按赛狐原始模块结构组织: 16 个模块、3 级层级
- 创建 `download_docs.py` — 可增量更新、记录下载时间戳
- 从 `advertise/docs/` 迁移 sellfox 相关 research + lessons 文档
- 新建 AGENT_HANDOFF.md + OKF 文档骨架

### 数据源

- llms.txt: `https://sellfoxapi.apifox.cn/llms.txt` (77,594 字符, 858 行)
- 认证方式: Apifox 密码 (VZKGdd0Q) → browser cookie → requests
- 下载时间: 2026-07-01T03:09:45Z
- 成功率: 419/419

### 已知限制

- Cookie 有时效性，重新下载需先更新 cookie
- 部分文档极短（如 `申请API权限` 仅一行提示），属 Apifox 原文内容
- `?nav=` 参数对 .md 内容无影响，llms.txt 中有大量重复链接
