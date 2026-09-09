---
okf: v0.1
type: Reference
title: 2026-09 试点测试方法与断言数字
description: 可复跑步骤：迟交审计、赛狐 V2 fetch、紫鸟列式 fetch-custom、两表对比、gsheet 交叉表；含输入文件与断言
tags: [sellfox, amazon, settlement, testing, dingtalk, reference]
timestamp: 2026-09-09
resource: sellfox_settlement/reconcile_amazon.py
---

# 2026-09 试点测试方法与断言数字

> 以后照着做。凭证从父仓库 `.env` / `secrets/` 读，**勿提交 Key**。详细调研见 [research/saihu-amazon-settlement-autofetch-2026-09-09.md](../research/saihu-amazon-settlement-autofetch-2026-09-09.md)；踩坑见 [lessons/lessons-learned.md](../lessons/lessons-learned.md)。

## 0. 公共前提

```bash
# 在仓库根（或 worktree 根）
uv run python sellfox_settlement/reconcile_amazon.py --help
uv run python sellfox_settlement/audit_late_submission.py --help
```

- 赛狐：`SELLFOX_PROXY_API_KEY`（或 APP_ID/SECRET）。
- 钉钉定稿/导出路径（本机，未入库）：`D:\Work\王忠于\成本核算\`。
- gsheet SA：`secrets/gsheets-service-account.json`（gitignore）。
- `approval_filter` = `(审批状态∈[完成,审批中]) & 审批结果≠拒绝`。

## 1. 迟交审计（两种口径，勿混）

### 1A 逐月定稿桶（仓库外）

- 输入：各月一个 `_合并汇率&账号_`（2026-03~08）。
- 脚本：`D:\Work\王忠于\成本核算\_run_账期提交异常分析.py`。
- 规则：账期月 Z = `账期日期` 自然月；提交桶 B = `发起时间` 落在 Z 月 4 号~下月 3 号。
- **断言（定稿桶视角）**：8 月桶内账期日期在 7 月 = **40 行**；7 月桶 09-08 再核完成>08-03 = **40**；3 月桶 2025 遗档 = **6**。

### 1B 单文件全量 + 最新审批（仓库内）

```bash
uv run python sellfox_settlement/audit_late_submission.py \
  "D:/Work/王忠于/成本核算/Amazon&新平台成本 20260101-20260908 销售收款确认单-20260909140003.xlsx" \
  --out out/late_submission_audit_all --platform 亚马逊
```

- 去重键：`审批编号 + 账期日期 + 渠道账号 + 应收金额`。
- **断言（2026-09-09 导出）**：全平台去重 **1528** 行；Amazon-only ~**660** 行；迟交集中在 2026-07 / 2026-04（详见 workflow-issues 文档表）。

## 2. 赛狐结算中心 V2（payout）

```bash
uv run python sellfox_settlement/reconcile_amazon.py shops
uv run python sellfox_settlement/reconcile_amazon.py fetch \
  --start 2026-06-01 --end 2026-07-10 --month 202606 \
  --out data/saihu_amazon_202606 --currency USD
```

**复现硬条件**

| 项 | 要求 |
|----|------|
| 汇总 | 必填 `timeType`（如 settlementEndTime） |
| 分页 | `pageNo`/`pageSize` 为**字符串**；`pageSize≤200` |
| 日期 | `groupEndStr` 斜杠 → 先 `replace('/','-')` 再按月过滤 |
| 币种 | 默认明细 CNY；`--currency` 取原币（按币种分别拉） |

**断言（2026-06）**

- Amazon 店约 **90**；汇总归 6 月结算 **103**；明细命中约 **16.8k** 行（全窗口曾拉到 ~38.8k）。
- 未滤 `选择平台==亚马逊` 时钉钉侧销售额会虚高（新平台混入）。

## 3. 紫鸟插件列式 Custom（activity）

```bash
uv run python sellfox_settlement/reconcile_amazon.py fetch-custom \
  --start 2026-04-01 --end 2026-06-30 --month 2026-06 \
  --report-type 3 --out data/saihu_custom_202606
```

**复现硬条件**

- `reportTypeList` **一次一个**（3=Transaction，4=Summary）。
- API **只列已抓文件**，不能生成新 Date Range；需插件先抓。
- `fileUrls` → **ZIP** → `*MonthlyTransaction.csv`，**32 列**（比部分财务手工 CSV 多 `account type`）。
- 财务手工 Custom CSV 常有 preamble，真表头约 **第 9 行**。

**断言**：`reportType=3` 曾见 `totalSize≈53`；Novelledo-US 样例行列与财务 Custom 匹配。

## 4. 两表对比（禁止对总额）

样例店：云途汇德-Novelledo-US，账期月 2026-06。

| 科目 | A=Custom USD | B=赛狐明细 CNY |
|------|--------------|----------------|
| 税 | ≈0 | ≈0 |
| 合计 | **−119.89** | **−7867.45** |

口径不同（activity vs payout）+ 币种不同 → **不要对总额**。方向一致即可：product_sales↔Principal、selling_fees↔Commission、Cost of Advertising↔广告。

官方注意：Settlement Flat File/XML 弃用约 **2026-11-11**。

## 5. storeName ↔ 渠道账号

```bash
uv run python sellfox_settlement/reconcile_amazon.py candidates \
  --detail data/saihu_amazon_202606/detail.csv
# 交叉表产物（已入库样例）
# sellfox_settlement/out/storeName_to_account_candidates.csv
```

**断言 / 计数说明**

- 自动匹配写入共享表「赛狐店铺」列：**61** 项 + 表末新增 **2** 行（`AMZDANEEYCA` / `AMZBJRYECLTDCA`）。
- 「赛狐店铺」列非空约 **73** 行 = 同一落地的另一切面（含 VERCART→AMZVer 等），**不是第二套结果**。
- 别名禁止裸 `CA` / 品牌 token（explode+去重）。

## 6. 与钉钉定稿 reconcile（原型）

```bash
uv run python sellfox_settlement/reconcile_amazon.py reconcile \
  --settlement data/saihu_amazon_202606 \
  --dingtalk "D:/Work/王忠于/成本核算/Amazon&新平台成本 20260604-20260703 销售收款确认单-20260706111631_合并汇率&账号_2026-07-06_11-52-51.xlsx" \
  --month 202606 --out out/amazon_compare_202606.xlsx
```

科目映射仍是试点硬编码；**逐账号三方对平（V2 vs Custom vs 钉钉）尚未产品化**，留给后续。
