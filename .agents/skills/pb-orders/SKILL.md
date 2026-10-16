---
name: pb-orders
description: >
  Pottery Barn (PB) 出件与断货闭环：SPS 库存预检 → 通途导入 xlsx + 标签/背贴 PDF；
  打单后才发现无货时的 invoice 清理惯例、Notion 断货台账登记、通知 Diane 的邮件规律。
  当用户提到「PB」「Pottery Barn」「出件」「库存预检」「标签 PDF」「背贴」「Packslip」
  「无货未发」「断货台账」「通知对接人」「给 Diane 发邮件」「清 invoice」「invoice 总额」
  「楔形枕补货」「PB 补货」时触发。
  不要用于 PB 月度对账 / TM 佣金 / UPS 交付核查（那是 pb-reconciliation）。
metadata:
  module: pb_orders
  docs: pb_orders/docs/reference/stockout-closed-loop.md
  updated: 2026-10-16
---

# PB 出件与断货闭环

完整规范见 [pb_orders/docs/reference/stockout-closed-loop.md](../../pb_orders/docs/reference/stockout-closed-loop.md)
与 [workflow.md](../../pb_orders/docs/reference/workflow.md)。这里是可复跑清单。

## 必须先做

1. 读 `pb_orders/AGENT_HANDOFF.md`（背景 / 文件位置 / 函数表 / 坑）。
2. 数据在**仓库外**：`D:\Work\美国\Tracy Miller\PB orders\<YYYYMMDD>\`。
3. 凭证在**父仓库** `D:\Work\赛狐\Cursor`，worktree 里没有。一律 `uv run python`。
4. 判定「真发」只认 **UPS 取件** —— ASN / 通途 `despatched` / `PBUS-<PO>` 都只等于「建了标」。

## 两条主线

### A. 正常出件（步骤 0 → 4）

```bash
cd pb_orders
uv run python run_stock_check.py --dir "<批次目录>" --no-stock "<断货SKU,…>"   # 步骤 0 预检
uv run python run_pb_orders.py --dir "<批次目录>"                              # 出件（xlsx+标签+背贴）
```

判定单位是**明细行**不是整单（部分缺货只剔缺货行）。逐行照搬源文件 → checked CSV 与 SPS 导出一致。

### B. 打单后才发现无货（本 skill 的重点）

美中仓回话说某 PO 无货时，按顺序做四件事 —— 见 reference 文档 §2：

1. **清 invoice**（月底钉钉提交前必须做）：原 `invoice xNN …csv` + 总额 txt 移进 `invoice/NotUsed/`；
   生成去掉无货 H+D 行的新 csv；**新总额写进新的 0 字节 txt 文件名**，格式
   `<新总额> 已去除无货N单<PO…> 之前是<旧总额>.txt`。
2. **Notion 登记**：库「PB 无货未发（一行一个 PO）」，用 `pb_orders/notion_stockout.py` 算待追加行。
3. **通知 Diane**（`us@mxdeals.com` → PB 采购对接人，地址见历史邮件）：主题 `SKU:<PB买家SKU> out of stock Vendor 5806`，
   **后续新 SKU 回复上一封**（主题滚成 `Re:RE: …`）。
4. **SPS 后台**：重提 IA（`SPS_Selenium_Local/sps_automation.py` 能发 IA）+ 在 PO 上重发 AKN(855)
   —— ⚠️ **AKN 目前无脚本、无步骤记录**。

到货后按 Notion 记录重发，变化同样回写 Notion。

## 铁律

- **`Vendor Style` 大小写不敏感**（`CEN961NLinen-SageGreen-138` ≡ 大写形态）；对齐时统一 `upper()`。
- **别用通途库存判定断货**：通途为标记发货要先「报溢」，可用库存恒 0 是常态。
- **EN 侧不扣减通途库存**（2026-10 确认）→ EN 的 Bin 数量**不能当可用库存**。
- **SO 的「未交量」≠ 在途**：货常常已经出境到目的仓。
- **invoice 的 H 行才带 PO 号**，D 行 PO 为空 —— 删无货单要整块删（H+D），否则留孤儿明细。
- **绝不把邮件口令 / 账号密码写进仓库**；邮件里不出现 Tracy / 中间人 / 5% 佣金。

## 相关经验（docs/solutions）

- `docs/solutions/workflow-issues/pb-stockout-post-shipment-closed-loop.md` —— 打单后才发现无货的闭环：invoice 清理惯例、邮件成链、两套库存不能混用
- `docs/solutions/workflow-issues/pb-replenishment-sizing-from-sales.md` —— 补货量估算：美中 Daneey 口径、通途订单表读法、剔除断货月、交付用 Excel
- `docs/solutions/workflow-issues/pb-out-of-stock-notification-and-zero-stock-orders.md` —— 断货判据 / PO→Tongtool Order 映射 / UPS 才算真发

## 相关 skill

- `pb-reconciliation` —— PB 月度对账 / TM 佣金 / UPS 交付核查（**不是**本 skill）
- `ups-track` —— 判「真发」用
- `tongtu-automation` / `tongtool-api` —— 通途库存与销量
