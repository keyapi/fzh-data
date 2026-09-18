---
name: channel-account-sync
description: >
  Google 表「和运营部共享」渠道账号与生产 EN Channel Account 对账/写入。
  当用户提到渠道账号、Channel Account、运营人员、FZHSX 欧洲、AMZFZHSXEUR、
  Illiosenergy、Kaufland AT/IT/FR、店铺负责人、渠道账号别名、vilavi_pim
  渠道主数据时触发。不要用于通途仓库改名（tongtool-warehouse-sync）
  或 OSTKUS/Wayfair 账期对账（platform-account-reconciliation）。
metadata:
  module: channel_account_sync
  docs: docs/solutions/workflow-issues/en-channel-account-gsheet-sync.md
  updated: 2026-08-25
---

# 渠道账号表 → EN Channel Account

完整规则见 `docs/solutions/workflow-issues/en-channel-account-gsheet-sync.md`。接手顺序在 `channel_account_sync/AGENT_HANDOFF.md`。

## 必须先做

1. 读解决方案文档和 `channel_account_sync/AGENT_HANDOFF.md`。
2. 凭证在父仓库：`EN_API/.env`、`secrets/gsheets-service-account.json`。
3. 一律 `uv run python`。默认 dry-run；`--apply` 须用户确认。
4. 先 fetch → compare → 把计划计数给用户，再 apply。

## 铁律

- Amazon 禁止 EUR/EU；欧洲九国抄 Johna：DE ES FR IT UK PL NL BE SE。
- 负责人人变了才加行；开卖后空月写 `待分配`；中文名含 `&`。
- 不建 `null`。不合并 `WFDANEEYUS` / `WFDaneeyUS`。
- Illios：channel `Illiosenergy`、code `ILLIOS`、账号 `ILLIOSPL`。
- GET 子表 list 会 403；PUT 父文档整表。去 Expect 头防 417。
- 不要提交 `channel_account_sync/out/` 快照。

## 管道

| 目的 | 命令 |
|------|------|
| 拉表+EN | `uv run python channel_account_sync/fetch_sources.py` |
| 出计划 | `uv run python channel_account_sync/compare.py` |
| 预览 | `uv run python channel_account_sync/apply.py` |
| 写入 | `uv run python channel_account_sync/apply.py --apply` |
