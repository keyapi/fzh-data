---
okf: v0.1
type: Log
title: pb_orders 变更日志
tags: [pb, orders, log]
timestamp: 2026-09-21
---

# 变更日志

## 2026-09-22（第四轮：把一致性验证做成可复跑脚本）
- **新增**: `compare_runs.py` —— 一条命令把本工具当天三个产物与 `<dir>/Colab处理/` 的三个逐项对比：
  通途 xlsx **逐单元格**、背贴 PDF 页数/字节数/**逐页像素**、标签 PDF 页数/几何签名/逐页像素，
  并额外做一次「用 Colab 里的时间戳重建标签 PDF 再比」——把「差异只来自生成时刻」从猜测变成证明。
  退出码 0=一致 / 1=有实质差异。
- **背景**: 用户昨天发出的仍是 Colab 版（本工具产物当时尚未验证）。本脚本就是为了让用户
  不必依赖口头结论：下一批两边都生成、跑一次、显示 ✓ 再用。
- **当日结果**: 通途 xlsx 0/5000 单元格不同；背贴 PDF 字节数一致(65,576)且**像素 0 差异**；
  标签 PDF 100 页几何签名一致，像素差异 167,832 全部来自时间戳，**换成 Colab 时间戳重建后 0 差异**。

## 2026-09-21（第三轮：无货拆分）
- **新增**: `--no-stock` 指出无货 SKU 时，按「页 = 包裹」把出件拆成两份，**默认流程不变**：
  - 主标签/背贴 PDF 只含**有货**订单的页（避免误发无货的）
  - 另出 `无货{N单M件}-{MM.DD} …` 子集标签/背贴，给无货那几单单独留着
  - 通途额外出 `PB_1_不可导入_无库存_` / `PB_2_导入_库存有货_`
- **新增**: `--no-stock-note` 自定义无货子集文件名里的描述（历史写法如 `4单6个三角灰97`）。
- **新增**: `pb_label_pdf.extract_pages()` —— 按页序抽出子 PDF。
- **改**: 1:1 硬校验与 join 改为对**全量**订单行做（原先对过滤后的集合，给了 `--no-stock` 会直接中止）；
  join 必须用全量行，否则无货页拿不到 SKUxQTY、标签上会缺 SKU。
- **验证**: 模拟无货（`CENC/LINEN-YELLOW-60` + `CEN1607NLINEN-IVORY-97`）
  → 通途 45 可导入 / 5 无库存；主标签 45×2=90 页、无货标签 5×2=10 页；
  主/无货背贴 `PO: PO-Line` 集合**交集为空、并集 = 全量 50 页**；主标签内**无无货 SKU**。
  回归：不给 `--no-stock` 时输出与改动前**逐页文字一致**（差异仅运行时间戳）。

## 2026-09-21（第二轮：修时间戳位置 + Acrobat 差异定位）
- **修复**: 叠加页时间戳坐标的**单位翻译错误**。notebook 的 `drawString(x5 + 30, y5 + 140)` 里
  `36 * mm` 已是 point，`+ 30 / + 140` 加的是 point；我误按 mm 写成 `(66mm, 215mm)`，
  导致两个时间戳都落到打包单区域、**标签页没有时间戳**（用户肉眼发现）。
  常量区改为按 notebook 变量名一一对应（`X1..X7, Y1..Y7`），不再手工换算单位。
- **验证**: 把时间戳替换成 Colab 那个值重建后逐页 diff —— **100 页 0 个不同像素**，
  与当天真实 Colab 产物像素完全一致（此前只能做到"差异仅在时间戳区域"，无法排除其他偏差）。
- **定位（未改）**: Colab 产物在 Windows Acrobat 打开全白、Chrome 正常；本版两者都正常。
  可验证差异只有：Colab **每页 /Resources 有 2 个内联字体字典**（PyPDF2 `merge_page` 写法），
  今天 200 个 / 09.17 84 个 / 09.14 128 个 —— 长期存在，非当天引入；本版为 0。
  页面几何、图片对象（52 种 / 10.91MB）两版一致，qpdf 对两版均不报错。

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
- **未做**: 原 notebook 步骤 3.x（赛狐导入）、4.3（按仓库分拆，20260831 起停用）。
  （「无货子集」已在 2026-09-21 第三轮实现。）
