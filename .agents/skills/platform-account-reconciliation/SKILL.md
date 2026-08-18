---
name: platform-account-reconciliation
description: >
  平台账期对账（Overstock/OSTKUS，未来 Wayfair/WFUS）：解析 Payment Summary + Detail，
  与 EN 生产系统 Tongtool Order 做订单/费用级核对，识别拆单、重复主单与跨期退单。
  当用户提到"账期对账"、"OSTKUS"、"OSTK"、"Overstock账期"、"WFUS"、"Wayfair账期"、
  "Payment Summary"、"Tongtool Order"、"账期费用核对"、"平台费"、"营销扣点"时触发。
  不用于库存初始值、采购成本、商品重尺或图片上传。
---

# 平台账期对账

## Read First

1. `platform_account_reconciliation/AGENT_HANDOFF.md` — 当前状态、字段口径、拆单规则与脚本用法。
2. `platform_account_reconciliation/docs/reference/field-mapping.md` — 账期字段与 EN 字段映射。
3. `platform_account_reconciliation/docs/lessons/lessons-learned.md` — 对账踩坑清单。

不要只凭账期文件里的原始 `OS Order #` 精确查 EN；先处理后缀 `_1/_2/_3`、`-1` 和 `OSFD-` 前缀。

## 标准流程

1. 确认输入是账期文件（含 `Payment Summary` + `Detail`）还是平台订单导出；两者日期可能不同期。
2. 解析 Payment Summary 与 Detail，按退货/调整/费用分类建立可对账合计。
3. 读取 `EN_API/.env` 生产凭证，通过 EN REST 只读拉取 `Tongtool Order`。
4. 识别拆单子单与重复主单；重复主单（无后缀主单金额=后缀子单合计）在汇总中排除。
5. 按 `基础OS订单号 + Supplier SKU + Quantity + order_amount + 仓库 + 发货时间` 核对。
6. 生成财务工作簿，未匹配行保留并说明原因。

## 入口

```bash
uv run python platform_account_reconciliation/scripts/reconcile_ostkus.py \
  --account "D:/Work/尹/OSTKUS-2026-07-01.xlsx" \
  --account "D:/Work/尹/OSTKUS-2026-07-16.xlsx"
```

## 完成关口

- 账期订单覆盖率为 100% 或列出全部未匹配原因。
- 销售金额差异为 0，或逐单列出差异。
- 重复主单已排除，金额没有双算。
- 输出 xlsx 不提交 git，原始 PII 不入仓。
- PR 前运行凭证扫描和 `git diff --check`。
