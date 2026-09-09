---
okf: v0.1
type: Handoff
title: 赛狐自动拉取 Amazon 账期 — 子项目交接
description: 用赛狐 OpenAPI(结算中心V2 + 紫鸟/赛狐插件列式报表) 自动取回 Amazon 账期费用、做科目解析、与钉钉运营提交值对账；含赛狐店名↔渠道账号交叉表
tags: [sellfox, amazon, settlement, account-period, reconciliations, handoff]
timestamp: 2026-09-09
---

# 赛狐自动拉取 Amazon 账期

> 财务每月只靠运营在钉钉手动提交 Amazon 账期金额（后台截图 + 附件 txt）。本子项目用赛狐 OpenAPI + 紫鸟插件报表把 Amazon 账期自动取回并解析，与运营提交值比对。`reconcile_amazon.py` 已跑通实测。

> **先读**：[深度调研](docs/research/saihu-amazon-settlement-autofetch-2026-09-09.md) 与 [科目映射](docs/reference/column-mapping.md)、[端点/字段](docs/reference/settlement-v2-endpoints.md)。本文是入口：背景、数据源、关键结论、文件位置、运行方式、交接清单。

## 1. 业务背景
- 运营在钉钉提交「销售收款确认单」（一行=一条账期；金额来自 Amazon 后台截图+附件 txt）；另一财务同事按发起时间 4号~下月3号 归桶到 NAS，归档文件名 `Amazon&新平台成本 YYYYMMDD-YYYYMMDD 销售收款确认单-<ts>[ _合并汇率&账号_<ts>].xlsx`。
- 痛点：运营须 3 号前按时提交、金额靠人填易错；审批有 完成/审批中/撤销/拒绝 不确定性（代码只假设 `审批状态∈[完成,审批中] & 审批结果≠拒绝`）；Amazon 结算 txt 欧美小数/分隔符不同、SKU 空格错列，旧解析只能可靠提取 Tax。
- 目标：**Amazon 账期费用自动取回 + 科目解析 + 与运营提交值对账**。

## 2. 数据源与口径（核心结论，别弄错）
| 报表 | 口径 | 赛狐 OpenAPI | 用途 |
|---|---|---|---|
| 结算中心V2 明细 `…/settlementSummary/detailPage.json` | payout（打款） | ✅ 原生结构化 | 费用/回款率自动化 |
| 结算中心V2 汇总 `…/groupPage.json` | payout | ✅ `accountNetIncome`=截图「净收入」 | 对账截图 |
| 列式 Custom Transaction（紫鸟插件）| **activity/posted**(含 deferred)、原币、列式 | ⚠️ 非原生；`报告中心 getPlugPageList type=3/4` 回取插件已抓文件(ZIP→csv)，**已实测拿通** | 税务报税/明细/科目列直给 |

- **官方 SP-API**：结算=`GET_V2_SETTLEMENT_REPORT_DATA_FLAT_FILE_V2`(payout，不能主动请求/定时)；**列式 Date Range 报告无 API 类型，UI-only**（需紫鸟+赛狐插件）。
- **两表总额不等**——口径不同，别对等。**税净≈0**(Amazon 代收代缴)。off-account 广告不进结算→TACoS 低估。

## 3. 关键结论 / 踩坑
- 明细 **默认 CNY**（赛狐当日汇率）；**`currency` 参数可返回原币**（按币种分别拉）。
- `groupEndStr` **斜杠**日期；`pageSize≤200`；`reportTypeList` 一次一个。
- 赛狐店名 `收款主体-账号别-站点`，账号别是随便填的品牌，**用收款主体→账号族 code + 站点**匹配「和运营部共享/渠道账号（20260521起在此维护）」。已确认：北京熙锦(XJ)=AMZBJXJ、VERCART=AMZVer、Daneey-CA=AMZDANEEYCA、如泱-CA=AMZBJRYECLTDCA、**北京固祥未启用→排除**。
- **别名坑**：`渠道账号别名` 会被 explode+去重作匹配键，必须是**完整账户标识**，**不能含裸地区/品牌 token**（colab cell 1.2/1.2.1）。

## 4. 文件位置
| 角色 | 路径 |
|---|---|
| 共享表（读/写） | 谷歌表「和运营部共享」worksheet「渠道账号（20260521起在此维护）」；SA `D:\Work\赛狐\Cursor\secrets\gsheets-service-account.json`(父仓库 gitignored, gspread) |
| 钉钉定稿（运营提交值，对照） | `D:\Work\王忠于\成本核算\Amazon&新平台成本 …_合并汇率&账号_….xlsx` |
| 脚本 | `sellfox_settlement/reconcile_amazon.py` |
| 交叉表 | `sellfox_settlement/out/storeName_to_account_candidates.csv` |
| 取回数据(生成) | `data/saihu_amazon_202606/`(未入库) |
| 赛狐凭证 | `SELLFOX_PROXY_API_KEY`(或 APP_ID/SECRET) 在父仓库 `.env`；**勿泄露** |

## 5. 运行方式
```bash
uv run python sellfox_settlement/reconcile_amazon.py shops
uv run python sellfox_settlement/reconcile_amazon.py fetch  --start 2026-06-01 --end 2026-07-10 --month 202606 --out data/saihu_amazon_202606 --currency USD
uv run python sellfox_settlement/reconcile_amazon.py fetch-custom --start 2026-04-01 --end 2026-06-30 --month 2026-06 --report-type 3 --out data/saihu_custom_202606
uv run python sellfox_settlement/reconcile_amazon.py reconcile --settlement data/saihu_amazon_202606 --dingtalk "<钉钉定稿xlsx>" --month 202606 --out out/amazon_compare_202606.xlsx
```

## 6. 本次成果(2026-09)
- 调研：背景/可行性/两报表口径/科目映射/风险/短中长期路径（见 research/doc）。
- 实测：赛狐结算中心V2（2026-06: 103 结算 / 16.8k 明细）+ 紫鸟插件列式报表（type=3→ZIP→32 列 csv，Novelledo-US 样例行匹配）均取通。
- 工具：`reconcile_amazon.py`（shops/fetch/fetch-custom/candidates/reconcile，`--currency` 取原币）。
- 交叉表：自动匹配 61 项 + 2 行新账号 + 10 个 VERCART→AMZVer；写入共享表「和运营部共享/渠道账号」新增 `赛狐店铺` 列（在 `渠道账号别名` 右侧）。
- 知识沉淀：`docs/solutions/tooling-decisions/amazon-settlement-autofetch-sellfox.md`；技能 `sellfox-amazon-settlement` 入 `.agents/skills/`。

## 7. 交接清单 / 下一步（后续可交给更强模型继续）
1. **V2 明细→钉钉列 做成表驱动**（放 gsheet 或本地 constants 勿硬编码）；优先用列式 CustomTransaction 列直给核对。
2. **逐账号比对**：join `渠道账号`(赛狐店铺列) 做逐账号差异（赛狐 vs 运营提交，含漏/多/金额出入）。
3. **币种/汇率**：原币 + 财务固定月汇率（colab 用「和财务部共享-汇率」表），避免赛狐当日变动汇率。
4. **时点**：测「4 号前能否取全上月」（Amazon 打款 3-5 天后、赛狐同步再滞后）。
5. **广告**：on-account 在结算；off-account 需另取 Amazon Ads API / SKU Economics。
6. **多平台**：赛狐仅 Temu/TikTok/Walmart/eBay/AliExpress/MercadoLibre/SHEIN/Shopify 有账单；**Wayfair、Home24/Mano/Allegro/Cdiscount/EMAGRO/HOUZZ/Worten/ePrice 无 → 短期仍人工**。

## 8. 需 YB 确认
- 新增 `AMZDANEEYCA`/`AMZBJRYECLTDCA` 两行的 别名/运营分组/运营人员（已按同族填 事业三部/荆春雨、事业二部/刘小菁）；是否补「通途有订单但无赛狐店名」的账号（通途未在手，未做）。

## 9. 数据/报表刷新建议（钉钉导出）
- **两种迟交审计口径都正确、不要混**：
  1. **逐月定稿桶**：`D:\Work\王忠于\成本核算` 各月 `_合并汇率&账号_`（2026-03~08）；仓库外脚本 `_run_账期提交异常分析.py`。
  2. **单文件全量 + 最新审批状态**：用户已于 2026-09-09 下载 `Amazon&新平台成本 20260101-20260908 销售收款确认单-20260909140003.xlsx`；用 `audit_late_submission.py` 跑通（全平台去重 1528 行 / Amazon ~660 行）。数字与规则见 `docs/solutions/workflow-issues/amazon-account-period-late-submission-audit.md`「最新状态·多账期审计」。
- 赛狐取回用 `fetch`/`fetch-custom` 直接拉，不依赖钉钉导出。
- **月结/逐账号对账**时：再从钉钉后台导出**当月**「销售收款确认单」（`发起时间 4号~下月3号`）；过滤 `approval_filter=(审批状态∈[完成,审批中]) & 审批结果≠拒绝`。
- 复现步骤与断言数字 → [docs/reference/how-we-tested-2026-09.md](docs/reference/how-we-tested-2026-09.md)。

## 10. 本次用到的技能/工具（供后续复用）
- **技能**：`okf`（OKF v0.1 文档规范：frontmatter `type`、每目录 index.md、每 bundle log.md）、`ce-compound`（docs/solutions 知识沉淀）、`sellfox-api`（赛狐 OpenAPI 访问/凭证/限流）。**不适用**：category/multi-attr/item-cost 等赛狐 Excel 导入类。
- **库/凭证**：`SELLFOX_API/client.py`(`SellfoxClient`, 代理/直连/限流/重试)、gspread + `secrets/gsheets-service-account.json`(谷歌表)、`tongtool_order_cost.tongtool_order_cost.gsheets`。运行建议用**父仓库 `.venv`**。
- **相关既有模块/技能**：`platform-account-reconciliation`(OSTKUS/账期对账)、`pb-reconciliation`(PB 对账)、`channel_account_sync`(渠道账号命名/同步)、`en-channel-account-gsheet-sync`(渠道账号 gsheet→EN)。

