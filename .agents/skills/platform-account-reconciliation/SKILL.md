---
name: platform-account-reconciliation
description: >
  平台账期对账，两条线路：
  (A) Overstock/OSTKUS —— 解析财务给的 Payment Summary + Detail 账期 xlsx；
  (B) **Walmart/WM —— 赛狐 API 直拉账期结算行**（`walmartReport/queryStatementDetail`），不依赖手工导出。
  两者都与 EN 生产系统 Tongtool Order 做订单/费用级核对，识别拆单、重复主单与跨期退单。
  当用户提到"账期对账"、"OSTKUS"、"OSTK"、"Overstock账期"、"WFUS"、"Wayfair账期"、
  "Walmart账期"、"沃尔玛账期"、"WM账期"、"Walmart结算"、"platform_fee"、"平台费"、"营销扣点"、
  "Payment Summary"、"Tongtool Order"、"账期费用核对"时触发。
  注意：Wayfair/WFUS **无赛狐数据源**（赛狐无任何 Wayfair 财务端点），只能走财务手工文件。
  不用于库存初始值、采购成本、商品重尺或图片上传。
---

# 平台账期对账

## Read First

1. `platform_account_reconciliation/AGENT_HANDOFF.md` — 当前状态、字段口径、拆单规则与脚本用法（§10 是 Walmart）。
2. `platform_account_reconciliation/docs/reference/field-mapping.md` — 账期字段与 EN 字段映射。
3. `platform_account_reconciliation/docs/lessons/lessons-learned.md` — 对账踩坑清单。
4. Walmart 线路另读 `docs/research/2026-09-21-sellfox-walmart-settlement-api.md`（端点、账期节奏、口径结论）。

不要只凭账期文件里的原始 `OS Order #` 精确查 EN；先处理后缀 `_1/_2/_3`、`-1` 和 `OSFD-` 前缀。

## 标准流程

1. 确认输入是账期文件（含 `Payment Summary` + `Detail`）还是平台订单导出；两者日期可能不同期。
2. 解析 Payment Summary 与 Detail，按退货/调整/费用分类建立可对账合计。
3. 读取 `EN_API/.env` 生产凭证，通过 EN REST 只读拉取 `Tongtool Order`。
4. 识别拆单子单与重复主单；重复主单（无后缀主单金额=后缀子单合计）在汇总中排除。
5. 按 `基础OS订单号 + Supplier SKU + Quantity + order_amount + 仓库 + 发货时间` 核对。
6. 生成财务工作簿，未匹配行保留并说明原因。

### Walmart 线路差异（重要）

- 账期数据来自**赛狐 API**，不是手工文件：`probe_walmart_settlement.py --discover-periods` 摸账期，`--pull-period` 按账期取数。
- Walmart 是**双周账期（14 天）**。**必须按账期取数并跨账期合并比对** —— 同一 PO 的销售行与退货/费用行常落在相邻账期，按单账期聚合必错位。
- 连接键：赛狐 `purchaseOrder` == EN `platform_order_id`（`platform_code=walmart_api`，`name=WM-{po}`）。
- 平台费口径**已结案**：`赛狐佣金 = (商品价 + 沃尔玛补贴) × 15%`，`EN platform_fee = 商品价 × 15%`。差额 = 补贴 × 15%，**EN 漏算基数**。不要再当未解问题排查。

## 入口

```bash
# OSTKUS
uv run python platform_account_reconciliation/scripts/reconcile_ostkus.py \
  --account "D:/Work/尹/OSTKUS-2026-07-01.xlsx" \
  --account "D:/Work/尹/OSTKUS-2026-07-16.xlsx"

# Walmart：先按账期取数（赛狐），再勾稽
uv run python SELLFOX_API/probe_walmart_settlement.py \
  --shop-id 598030 --pull-period 2026-08-08:2026-09-05
uv run python platform_account_reconciliation/scripts/reconcile_walmart.py \
  --sellfox-json "<repo_root>/out/sellfox_walmart_probe/period_598030_*.json" \
  --out "Walmart账期勾稽.xlsx"
```

## 完成关口

- 账期订单覆盖率为 100% 或列出全部未匹配原因。
- 销售金额差异为 0，或逐单列出差异。
- 重复主单已排除，金额没有双算。
- 输出 xlsx 不提交 git，原始 PII 不入仓。
- PR 前运行凭证扫描和 `git diff --check`。
