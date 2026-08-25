---
okf: v0.1
type: Reference
title: Google 表渠道账号同步到 EN Channel Account
date: 2026-08-25
last_updated: 2026-08-25
category: workflow-issues
module: channel_account_sync
problem_type: workflow_issue
component: tooling
severity: high
applies_when:
  - "要把「和运营部共享」里的渠道账号写进生产 EN Channel Account"
  - "Amazon 欧洲店被写成 EUR/EU，需要按 Johna 九国站点拆开"
  - "负责人按月切了太多行，需要按人变了才加行重算"
tags:
  - channel-account
  - google-sheet
  - erpnext
  - vilavi-pim
  - amazon
  - owner-timeline
related_components:
  - EN_API
  - tongtool_order_cost
---

# Google 表渠道账号同步到 EN Channel Account

## Context

运营在 Google 表「和运营部共享」→「渠道账号（20260521起在此维护）」维护渠道店铺。生产 EN（`erpnext.vilavi.cn`，`vilavi_pim`）的 `Channel Account` 大约从 2026-02 起很少跟表。2026-08-24/25 对照后把表当事实源写入生产。

表是运营源；EN 是系统主数据。不要反过来用 EN 覆盖表。

当时的摩擦：按月切 Owner 得到约 367 行（同人连续月）；表上曾有 `AMZFZHSXEUR`，但 Amazon 只有国家站；`Illiosenergy` 不能当完整 `channel_code`；子表 list API 403；Frappe 对 `Expect: 100-continue` 回 417；`Owner.user` 现网是中文名 Data。

## Guidance

1. **先读表、再计划、再探路、最后 `--apply`。** 默认 dry-run。

```powershell
uv run python channel_account_sync/fetch_sources.py
uv run python channel_account_sync/compare.py
uv run python channel_account_sync/apply.py
uv run python channel_account_sync/apply.py --apply
```

Sheet：https://docs.google.com/spreadsheets/d/1nbMO-wf-Oj7HIuYlPOtrC7F8QtsEPDE80BmXo8G6O3Y/edit?gid=763421711  
EN token：父仓库 `EN_API/.env` 的 `PROD_ERP_API_KEY` / `PROD_ERP_API_SECRET`。gspread：`secrets/gsheets-service-account.json`。

2. **Amazon 只建国家站。** 禁止 `AMZFZHSXEUR` / `EUR` / `EU`。欧洲九国与 Johna 对齐：`DE ES FR IT UK PL NL BE SE`。旧名 `AMZFZHSXEUR` 只作为 **DE** 的别名。
3. **负责人按「人变了才加行」。** 连续同名月份合成一条 `from_date=YYYY-MM-01`。
4. **`Channel Account Owner.user` 写中文名**，包括 `荆春雨&张振朋` 和 `待分配`。开卖后的空月也写成 `待分配`。不要改成 User 邮箱。
5. **Illiosenergy**：Sales Channel 名 `Illiosenergy`、代码 `ILLIOS`；账号 `ILLIOSPL`。
6. **不要建** 表行 `null`。**Wayfair 的 `WFEU` 可以是 EU**。`WFDANEEYUS` 与 `WFDaneeyUS` 是两个账号。
7. **Kaufland** `supported_regions` 追加 `AT,IT,FR`。不要给 Amazon 加 EUR。
8. **子表不能用 list API**（本会话 403）。GET 父文档带出 `channel_account_alias` 与 `owners`。PUT 提交整表。
9. **REST 去 Expect**，否则生产 417。
10. **写入前 canary。** 2026-08-25 探路是 `AMZFZHSXUS` 补 `林俊彪` @ `2026-07-01`。Cursor 自动拦截时先本机批准，不要当成 EN 校验失败。

`Channel Account` 写入时带 `account_id`（本会话 DocType 探查为 `autoname = field:account_id`）。

## Why This Matters

月切负责人会把同一人拆碎。Amazon EUR 不是合法店铺粒度。中文名是存量事实，改成邮箱会对不上运营表。

## When to Apply

- 用户提到渠道账号、Channel Account、运营人员YYYYMM、FZHSX 欧洲、Illiosenergy。
- 表上新增店铺、改别名、换运营负责人。
- 不要用于通途仓库改名（`tongtool-warehouse-sync`）或平台账期对账（`platform-account-reconciliation`）。

## Examples

表：202511–202606 于彬，202607 林俊彪，202608 陈立彬 → EN 三条：`于彬@2025-11-01` → `林俊彪@2026-07-01` → `陈立彬@2026-08-01`。

`AMZStruseryPL` = AMZ + Strusery + PL；`KFLAT` = KFL + 空 + AT。

2026-08-25 生产（不要无故重跑 `--apply`）：Kaufland 补 AT/IT/FR；新建 Illiosenergy；新建 18 个账号；10 条别名；122 个已有账号补负责人，失败 0。`Operation Staff Settings` 未改。清单见 `channel_account_sync/docs/research/2026-08-25-prod-apply.md`。

## Related

- [模块接手](../../channel_account_sync/AGENT_HANDOFF.md)
- [命名规则](../../channel_account_sync/docs/reference/naming-rules.md)
- [字段对照](../../channel_account_sync/docs/reference/sheet-and-en-fields.md)
- [同步规则](../../channel_account_sync/docs/specs/sync-rules.md)
- [第一次写入踩坑](../../channel_account_sync/docs/lessons/2026-08-25-first-prod-sync.md)
- 同类「表 → EN」：[tongtu-warehouse-rename-reconciliation.md](tongtu-warehouse-rename-reconciliation.md)
