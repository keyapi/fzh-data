---
okf: v0.1
type: Log
title: pb_orders 变更日志
tags: [pb, orders, log]
timestamp: 2026-09-21
---

# 变更日志

## 2026-09-21
- **初始化**: 创建 OKF bundle（index.md / log.md / reference/ / lessons/）。
- **新增**: `run_pb_orders.py` — 总入口。`--dir` 自动挑当天最新 Packslip PDF 与订单 CSV；
  编排步骤 1-2/3/4/4.2；汇总报告 + 数量对账；1:1 硬校验；`--dry-run` / `--no-stock` /
  `--check-shipment` / `--allow-unmatched` / `--cache-only` / `--out`。
- **新增**: `sps_pb_pdf.py` — 步骤 1-2。PyMuPDF 抽取每页 `Purchase Order Number` 与 `Item Number`，
  派生 `Line` / `Line Count` / `PO Number-Line`；`join_pages_with_orders` 按 (PO, Item Number=Buyer Catalog #) 关联 SKUxQTY。
- **新增**: `pb_tongtu_excel.py` — 步骤 3。SPS 订单 CSV → 通途导入 xlsx：
  组内 ffill → 留 D 行 → 按 Qty 拆行 → 派生 SKUxQTY → 删 31 列 → 砍到 ≤100 列；
  无货 SKU 过滤（默认空 = 不过滤）产出 `PB_0/PB_1/PB_2`。
- **新增**: `pb_label_pdf.py` — 步骤 4。SKUxQTY 叠加页（A4 竖版、文字转 90°、箭头/剪刀/时间戳）→
  逐页 merge → 每页裁成「打包单（rotate+scale 0.732）」与「UPS 标签（rotate）」两页。
- **新增**: `pb_back_label_pdf.py` — 步骤 4.2。读 `US SKU Name` → `SKUName`（重试 + 本地缓存回退），
  中文名去英文后缀（nltk，可降级）、西语名含中文则清空，去重后关联 `Vendor Style`，
  生成 4×2 英寸背贴 PDF（`PO: PO-Line` + Code128 + 中/西品名表）。
- **修复（相对 Colab）**: pandas 3.0 兼容（`ffill` / `groupby.ffill` 丢键 / `fillna(inplace=True)` 静默失效）；
  `copy(page)` 共用 `/Contents` 导致 `scale_by` 污染标签页（改为单次读取 + 自实现缩放 + 共用流断言）；
  凭证改读父仓库 secrets/（支持 worktree 向上查找），不再明文硬编码私钥；
  背贴 QTY 由 `1.0` 修为 `1`；名称表重复键去重 + 告警；
  `PO Line #` 保持字符串（`to_numeric` 会让导出值 `'1'` 变 `1`，与 Colab 不一致）。
- **体积修复**: 先用「两趟处理各写一个中间 PDF」修缩放污染，结果同一张图各存一份 ——
  图片对象 130→260、体积 12.8MB→24MB（超邮件附件限制）；`compress_identical_objects()` 只压到 181。
  改为**同一 reader 单趟读取 + 自实现缩放**后回到 130 个对象 / 13.0MB，且快 25 倍。
- **实测（20260921）**: PDF 50 页 / 唯一 PO 40 / 通途 **50 行 × 100 列** / join 未匹配 **0** /
  标签 PDF **100 页** / 背贴 PDF **50 页**；ASN 核对 50 件全发无缺货。
- **A/B 验收（对比用户当天 16:44 的原 notebook 产物 `Colab处理/`）**:
  通途 xlsx **5000 单元格 0 处不同**；背贴 PDF **渲染像素完全相同**（字节数也一致 65,576）；
  标签 PDF 差异仅剩时间戳竖带（x 382..396）；页面 mediabox/cropbox/rotate 与图片 bbox 完全一致。
  另与 20260917 历史产物同源对照一致。
- **未做**: 原 notebook 步骤 3.x（赛狐导入）、4.3（按仓库分拆，20260831 起停用）、
  无货/部分发货时自动生成「无货子集」PDF（历史为人工操作）。
