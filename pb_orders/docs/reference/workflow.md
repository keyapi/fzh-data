---
okf: v0.1
type: Reference
title: PB 订单履约工作流参考 — 五步流程、列映射、坐标表、命名规则
tags: [pb, orders, workflow, column-mapping, coordinates, tongtu]
timestamp: 2026-09-21
---

# 工作流参考

> 来源：Colab notebook `PotteryBarn/SPS 合并装箱单+UPS PDF 添加 SKU 1拆2 20230721`
>（file id `1SjFXUYbQf0XwKl5H8B2lRhFBaYbF9d_5`），cell 0-31。
> 本文件记录「照搬了什么、为什么这么写、哪些地方改了」。

## 0. 整体数据流

```
SPS New 订单全量导出 ─ 步骤0 库存预检 ─> checked0stock order.csv ─┬─ 步骤3 拆行 + 派生 SKUxQTY ─┐
   (check0stock…csv)   (§9)                                      │                            │
                                                                 │                            ├─ 步骤4   标签 PDF
Packslip 美中 x50.pdf ─── 步骤1-2 抽每页 PO + Item Number ────────┴─ join ─> SKUxQTY 列表 ────┤
                                                                                              └─ 步骤4.2 背贴 PDF
                          US SKU Name 表（中/西语名） ─────────────────────────────────────────┘
```

**步骤 0 是履约的前置动作**（详见 §9）：出件用的 `checked0stock order.csv` 必须是
「按当前断货清单筛过」的那份，而不是 SPS 导出的原始 New 订单。以前这一步靠人在
Excel 里筛，现在由 `stock_precheck.py` 做，产物与 SPS 自己导出的那份**字节级一致**。

## 1. 步骤 1-2：从 PDF 抽 PO 与 Item Number

SPS 导出的合并 PDF 每页 = 一个包裹 = 一个 Item，页序与订单 CSV 拆行后的行序**一一对应**。
每页固定结构：

```
Customer Order Number: 362632154021
Purchase Order Number 137943090      <- PO 号（9 位以上）
...
Item Number                          <- 表头
Component / Item Ratio / Description / Ship Qty / Unit Price
1069914                              <- Item Number 值（7-10 位）
Inventive Sleep: Down Alternative: Personal Wedge Pillow: Ivory
```

抽取规则：

| 字段 | 规则 |
|------|------|
| `PO Number` | 正则 `Purchase Order Number (\d{9,})`，取**第一个** |
| `Item Number` | 找到**第一个**文本为 `Item Number` 的表头，取其**下方**第一个纯 7-10 位数字行 |

> ⚠️ 原 notebook 用 pdfminer，y 轴向上，判据是 `bbox[3] < 表头 bbox[1] - 10`；
> 本版用 PyMuPDF，y 轴向下，判据相应改为 `bbox[1] > 表头 bbox[3] - 1`（方向相反）。

派生列（同 PO 多件时用）：

| 列 | 规则 |
|----|------|
| `Line Count` | 同 PO 出现次数 |
| `Line` | 组内序号，从 1 开始（`cumcount()+1`） |
| `PO Number-Line` | `Line Count == 1` 时为 `PO`，否则 `PO-Line` |

## 2. 步骤 3：订单 CSV → 通途导入 Excel

处理顺序（**顺序不能变**）：

1. 读 CSV：`PO Number` / `PO Line #` / `Retailers PO` / `Customer Order #` / 两个 Zip / 电话 等强制为字符串
   （否则前导 0 丢失、长数字变科学计数法）；`PO Date` / `Requested Delivery Date` / `Ship Dates` 解析为日期
2. 按 `PO Number` **组内前向填充**（订单头 H 行的地址等字段下发给明细 D 行）
3. 只保留 `Record Type == 'D'`
4. 按 `(PO Number 升序, PO Line # 降序)` 排序（PDF 页序与 Line 号相反）
5. `Qty Ordered > 1` 的行**拆成多行**（每行 1 件，对应 PDF 一页一包裹）
6. 派生列：

| 列 | 规则 |
|----|------|
| `Line #` | 组内倒序编号（`cumcount(ascending=False)+1`），转字符串 |
| `Line Count` | 同 PO 行数 |
| `PO Number-Line` | 同上 |
| `PO Date` | 格式化为 `%Y-%m-%d %H:%M:%S` |
| `Ship To Country` | `USA` → `US`（通途只认二字码） |
| `Unit Price x Qty Ordered` | `Unit Price * Qty Ordered` |
| `x Qty Ordered` | 数量；不等于 1 时追加 ` ! ! !`（提醒一页多件） |
| `SKUxQTY` | `Vendor Style + ' x' + x Qty Ordered`，例 `CENKZ1325-YELLOW-153 x1` |

7. 删除 31 个通途不认的列（`COLS_TO_DROP`）
8. 若列数仍 > 100，**从右往左**删整列空值列直到 100 列

通途 Excel 的**表头就是 SPS 原始列名**，不是通途模板列名；通途按列名识别。

### 无货 SKU 过滤

- `--no-stock` 非空且命中时：写 `PB_0_不可导入_原始_`（全量）+ `PB_1_不可导入_无库存_` + `PB_2_导入_库存有货_`，
  后续步骤只用「库存有货」集合。
- 为空时：只写 `PB_0_导入_原始_`（全量），不过滤。

> ⚠️ Colab 里这段是**死代码**：参数是字符串 `"['A','B']"`，`for sku in zero_stock_skus` 迭代的是单个字符，
> `isin()` 永不命中，所以过滤从未生效（历史文件夹只见 `PB_0_导入_原始_`）。本版做成真正可用。

## 3. join：让每页拿到 SKUxQTY

```
df_pdf[PO Number, Item Number]
   ⨝ df_order[PO Number, Buyers Catalog or Stock Keeping #, SKUxQTY, Line #, Vendor Style, Qty Ordered]
   on (PO Number, Item Number == Buyers Catalog or Stock Keeping #)
```

- 订单侧先按 `-` 截断 `PO Number`（人工加过 `-2` 后缀时会导致匹配不上），并
  `drop_duplicates(subset=[PO Number, Buyer Catalog #], keep='last')`
- join 前有**硬校验**：`PDF 页数 == 订单行数`，不等直接中止
- 有未匹配行时默认中止（避免标签印空 SKU），确认无害可加 `--allow-unmatched`

## 4. 步骤 4：标签 PDF

### 4.1 叠加页（`SKUxQTY_only.pdf`，A4 竖版）

每页把该页的 `SKUxQTY` 文字**转 90°** 画两次，另加箭头、剪刀与时间戳：

| 元素 | 坐标 | 说明 |
|------|------|------|
| SKUxQTY #1 | 旋转后在 (205mm, 190mm) → 落在**打包单**页 | `X1,Y1` |
| SKUxQTY #2 | 旋转后在 (170mm, 50mm) → 落在**标签**页 | `X2,Y2` |
| `---→` ×2 | (195mm,165mm)、(195mm,280mm) | `X3,Y3` / `X4,Y4`，均在打包单页 |
| `←---` | (36mm,75mm) | `X5,Y5`，在标签页 |
| 时间戳 #1 | **(36mm+30, 75mm+140) = (132.05, 352.60) pt** | 落在**标签**页 |
| 时间戳 #2 | (20+400, 815) = **(420, 815) pt** | 落在**打包单**页 |
| `✂` ×2 | (815, -20)、(440, -20)（旋转后） | `Y6,-X6` / `Y7,-X7`，均在打包单页 |

> ⚠️ **单位陷阱**：reportlab 的单位是 point，`36 * mm` 已经是 point 值，
> 所以 notebook 里 `x5 + 30`、`y5 + 140` 加的是 **30/140 point**，不是 30/140 mm。
> 曾经把时间戳 #1 误写成 `(66mm, 215mm)`，结果它跑到打包单区域（两个时间戳叠在一起），
> **标签页反而没有时间戳** —— 用户一眼就看出来了。
> 每个叠加元素只会出现在两页中的一页（按裁切框分区），改坐标后两个页都要看。

实现细节：`canvas.rotate(90)` 后 `drawString(y, -x, text)` 等价于在 (x, y) 处画 90° 文字。
`merge_page` 后，位于 y∈[435,830] 的叠加元素出现在打包单页，y∈[77,367] 的出现在标签页。

### 4.2 合并 + 裁切拆分

1. 逐页 `base.merge_page(overlay)`（**不加旋转/平移**，与 notebook 一致）
2. 每页复制两份并裁切（pypdf 左下角原点）：

| 输出页 | 裁切框 mediabox/trimbox | cropbox | 变换 |
|--------|------------------------|---------|------|
| 打包单 | (10,435)-(590,830) | 同 mediabox | `rotate(90)` + 按 0.732 缩放 |
| UPS 标签 | (98,77)-(530,367) | (97,76)-(529,366) | `rotate(90)` |

输出顺序：`单_0, 标签_0, 单_1, 标签_1, ...`，50 页输入 → 100 页输出。

**实现注意**（踩过坑，别改回去）：

- notebook 的 `scale_by(0.732)` 等价于「各 box 坐标 ×0.732」+「内容前置 `0.732 0 0 0.732 0 0 cm`」。
  本版不再调 `page.scale_by()`，因为它在 pypdf 里走 `replace_contents` → `_replace_object`，
  只能改归属该 reader 的对象，页交给 writer 后会报 `Cannot update PdfReader with external object`。
- **必须同一个 `PdfReader` 只读一遍**：`copy(page)` 只复制页字典、`/Contents` 是同一个间接对象，
  所以两份拷贝必须各自拿到独立的内容（本版给打包单单独挂一条新流）。
  若改成「两趟处理各写一个中间 PDF」，同一张图会在成品里存两份：图片对象 130→260、
  体积 12.8MB→24MB（超出邮件附件限制）。
- `merge_overlay` 前会断言各页 `/Contents` 不共用（共用时 `merge_page` 会叠加多次）。

> `SLIP_SCALE = 0.732` 由 notebook 固定值；连带效果是打包单与标签都被 /Rotate=90 转正后，
> **打包单是侧向显示的** —— 这是长期行为，历史输出一致，不要"修正"。

## 5. 步骤 4.2：背贴 PDF

4×2 英寸（288×144 pt），每行一页：

| 元素 | 规格 |
|------|------|
| 左上行 | `PO: {PO Number}-{Line #}`，Helvetica 8 |
| 条形码 | `code128.Code128(pack_id, barHeight=8, fontSize=6, barWidth=0.65)` @ (margin+100, y+5) |
| 右上 | `{MM.DD}`（STSong-Light 5）+ `{idx} / {total}` |
| 表头 | `['#', 'SKU', 'QTY', 'Name Chinese', 'Nombres en español']` |
| 列宽 | `[0.4, 2.35, 0.7, 3.25, 3.35] cm` |
| 正文字号 | 10 / leading 9（note: leading < fontSize，是 notebook 原值） |
| 中文渲染 | `UnicodeCIDFont("STSong-Light")` |

品名来源与清洗：

1. 读 Google Sheet `US SKU Name` → `SKUName`（924 行；**有 2 个重复 `通途SKU` 键**，去重 + 告警）
2. `中文名称`：去掉第一个英文单词及其之后的内容（nltk `words` 词表判断；词表不可用则告警跳过）
3. `西班牙语名称`：若含中文字符则**清空**（原 notebook 规则）
4. 按 `Vendor Style`（大写）关联；匹配不到的 SKU 告警并留空
5. `QTY` 必须 `astype(int)`，否则印成 `1.0`

> 复用 `sellfox_shipping.sku_label.pdf_generator` 的 `build_mixed_xml` / `is_chinese`
> （同一套 Colab 逻辑的另一份落地），PB 参数不同故未复用其 `generate_sku_label_pdf`：
> PB 用 `PO: ` 前缀（非 `Package Number: `）、条码 8/6/0.65（非 10/8/1.2）、列宽 2.35cm（非 2.55cm）、固定字号（无收缩循环）。

## 6. 命名规则

| 文件 | 模板 |
|------|------|
| 通途导入（无无货） | `PB_0_导入_原始_{csv_stem}_on_{YYYY-MM-DD_HH-MM-SS}.xlsx` |
| 通途（有 `--no-stock` 命中） | `PB_0_不可导入_原始_...` / `PB_1_不可导入_无库存_...` / `PB_2_导入_库存有货_...` |
| 标签 PDF（有货） | `{MM.DD} PotteryBarn label-FZH-DANEEY-Not Prime-第一天.pdf` |
| 背贴 PDF（有货） | `{MM.DD} PotteryBarn 背贴-中文西班牙语.pdf` |
| 标签 PDF（无货子集） | `无货{note}-{MM.DD} PotteryBarn label-FZH-DANEEY-Not Prime-第一天.pdf` |
| 背贴 PDF（无货子集） | `无货{note}-{MM.DD} PotteryBarn 背贴-中文西班牙语.pdf` |

`note` 默认 `{订单数}单{件数}件`（例 `4单6件`），可用 `--no-stock-note` 覆盖成历史那种描述
（历史实例：`无货 4单6个三角灰97-08.21 PotteryBarn label-...pdf`、`无货蓝97-09.11 ...`）。

### 无货拆分（`--no-stock` 非空且命中时）

按「页 = 包裹」拆成两组，**不重不漏**：

1. 1:1 校验仍对**全量**订单行做（PDF 页数 == 全部拆行后的行数）
2. join 也用**全量行**做（否则无货页拿不到 SKUxQTY，标签上会缺 SKU）
3. 按 `Vendor Style` 是否在无货清单里，把页索引分成 `ok_idx` / `ns_idx`
4. 主文件（标签 + 背贴）只出 `ok_idx`，无货子集只出 `ns_idx`
5. 对账打印：`PDF 总页数 = 有货页 + 无货页`，差必须为 0

> 与历史做法的差别：历史是主文件含全量、再手工做一份无货子集（还出现过「撤回」）。
> 现在主文件直接只发有货的，避免误发。

`csv_stem` = 订单 CSV 去掉扩展名的完整文件名（含时间戳后缀）。

## 7. 数量对账

| 检查 | 期望 |
|------|------|
| PDF 页数 vs 订单行数 | 相等（硬门槛，不等中止） |
| join 未匹配数 | 0 |
| 通途列数 | ≤ 100 |
| 通途总行 = 可导入 + 无库存 | 差 0 |
| 标签 PDF 页数 | 输入页数 × 2 |
| 背贴 PDF 页数 | 订单行数 |
| ASN 实发 vs 订单数量（`--check-shipment`） | 逐 SKU 相等；不足即缺货 |

## 8. 与 Colab / 历史产物对齐的验收证据

用户当天 16:44 用原 notebook 跑过同一批（`20260921/Colab处理/`），据此做 A/B：

| 产物 | 对比结果 |
|------|---------|
| 通途 xlsx | 形状 50×100、列名一致、**5000 单元格 0 处不同** |
| 背贴 PDF | 页数一致、字节数一致（65,576）、**渲染像素完全相同**（200dpi 抽 3 页 0 差异） |
| 标签 PDF | 100 页；差异仅**时间戳的数字**（我的运行时刻 vs Colab 的 16:44）。把时间戳也改成 Colab 的值重建后 → **100 页 0 个不同像素** |
| 页面几何 | mediabox / cropbox / `/Rotate`（100 页签名完全一致）、图片 bbox **完全一致** |
| 叠加元素位置 | 打包单页时间戳 (300.1, 0.0, 396.4, 14.1)、标签页时间戳 (34.0, -1.6, 165.6, 17.7)、箭头与 SKUxQTY bbox **完全一致** |

另与 20260917 历史产物同源对照：几何、版式、`PO: PO-Line` 与 QTY 显示一致。

## 9. 步骤 0：SPS New 订单库存预检（履约前置）

### 9.1 为什么有这一步

出件用的 `checked0stock` CSV 不是 SPS 直接导出的原始文件 —— 出件前要先在 SPS 里
**把当批 New 订单全选导出**（`check0stock order x{N} YYYYMMDD_HHMM_SSSSSS.csv`），
按 `Vendor Style` 对照当前断货清单，剔掉缺货明细，得到 `checked0stock …`，
再拿它在 SPS 界面里勾 ASN 明细、给缺货的行发新日期通知。

以前这一步靠人在 Excel 里手工筛。现在 `stock_precheck.py` 做，产出两个文件：

| 文件 | 用途 |
|------|------|
| `checked0stock {stem}.csv` | 给下一步出件（以及留档） |
| `SPS库存检查操作表-{stem}.xlsx` | 人在 SPS 里照着勾，7 个 sheet，见 §9.4 |

### 9.2 分类口径：按**明细行**，不按整单（重要）

SPS 订单是 H（Header）/ D（Detail）两段结构。**判定单位是 Detail 行**：

| 该 PO 的 Detail 情况 | Header | Detail | SPS 侧动作 |
|---|---|---|---|
| 全部有货 | 保留 | 全留 | 正常出 ASN |
| **部分缺货** | **保留** | **只留有货的** | **不要整单取消**；ASN 只勾有货明细行；缺货行另发新日期通知 |
| 全部缺货 | 剔除 | 全剔除 | 不生成 ASN；发新日期通知 |

> ⚠️ 早期设计是「PO 里只要有一个 SKU 没货就整单剔除」，这是**错的**：PB 会以为整单不发，
> 回头发催单邮件。用户在 2026-09-23 明确纠正 —— 部分缺货的 PO 该发的部分要发。
>
> `Vendor Style` 匹配大小写不敏感（`CENKZ1325-YELLOW-138` 与 `CENKZ1325-Yellow-138` 同一条），
> 但**冻结的是用户原始写法**（任务报告里的 `no_stock_snapshot` 就是当次那份）。

### 9.3 checked CSV 必须与 SPS 导出一致（踩过的坑）

SPS 导出的 CSV 是**参差**的：表头 147 列、数据行 146 列、且**最后一个列名是空的**。

如果读进 pandas 再 `to_csv` 写回去，会得到：

- 空列名被写成字面量 `Unnamed: 146`；
- 数据行被补齐到 147 列 → 每行多一个尾逗号。

所以本版**逐行照搬源文件原文**（`_source_lines()` + 按保留行的索引取行），
而**不是**重新序列化。这样 checked CSV 与 SPS 自己导出的那份同构。

实测：2026-09-17 真实批次（`check0stock order x21 20260917_0338_456788.csv`，
断货只填 `CEN961NLINEN-SAGEGREEN-138`）生成的 checked CSV 与历史
`checked0stock order x19 20260917_0341_630468.csv` **SHA-256 完全相同**
（`e99a9b78…`，19,363 字节）。

另有两条配套约束：

- 编码对齐 SPS：**UTF-8 不带 BOM、LF**（带 BOM 就不再是同一格式）。
- 字段里含换行时按行照搬不成立 → 直接报错 `ragged_source`，宁可不出件也不出格式不同的文件。
  校验方式：`源文件行数 == 解析出的记录数 + 1`。

### 9.4 操作表：xlsx 7 个 sheet + **网页同一批明细表**

`SPS库存检查操作表-{stem}.xlsx`：

| sheet | 内容 |
|------|------|
| 操作总览 | 项目 / 数量 / 操作说明 |
| 部分缺货PO-逐行操作 | 部分缺货 PO 的明细，含「不要整单取消，只勾有货行」提示 |
| ASN有货明细 | 该勾的行 |
| 缺货明细 | 不该勾的行（发新日期通知） |
| 全部缺货PO | 整单不出 ASN |
| 检查报告 | PO / Detail / 数量 三口径对账 |
| 原始剔除行 | 已从 checked CSV 剔除的行 |

**网页上也有同样的明细表**（任务页，改版后新建的任务都有）：部分缺货 PO / ASN 有货明细 /
缺货明细 / 全部缺货 PO 四张表直接列出来，不用先下 xlsx 再看。
网页表与 xlsx 是**同一批 DataFrame**（`report["tables"]` 由 `_tables_payload()` 从
`_build_tables()` 的结果生成），所以两边不会各说各话。
超过 `WEB_TABLE_LIMIT`（300 行）会截断并在页面上**明确写出**「只显示前 N 行 / 共 M 行，
完整看 xlsx」—— 不静默丢。

改版前建的旧任务 `report` 里没有 `tables`，页面跳过这一段（不会 500）。

**每个明细表永远并列两个 SKU**（用户明确要求，2026-09-23）：

| 列 | 谁用 |
|----|------|
| `Buyers Catalog or Stock Keeping #` | **对方** SKU —— 在 SPS 界面里定位明细行 |
| `Vendor Style` | **我方** SKU —— 对照内部货品，也是库存匹配的键 |

> 用户原话：「ASN 有货明细表 缺货明细表 等等 永远！需要我们自己的 SKU！」
> 「我之前说在 SPS 后台明细表里我只看到对方的 SKU，不等于说我们自己不需要
> 自己的 SKU `Vendor Style` 用来对照」。

`Qty Ordered` 在网页表与 xlsx 里都**按整数显示**（源 CSV 里是 `1.0` 这种 float 字面量，
给人看的表不该照抄成 `1.0`；checked CSV 本身仍是逐行照搬的原文，不动）。

### 9.5 数量对账口径

| 检查 | 期望 |
|------|------|
| PO：总数 = 全有货 + 部分缺货 + 全部缺货 | 相等 |
| Detail：总数 = 有货 + 缺货 | 相等（`diff` 必须 0） |
| 数量：总数 = 有货 + 缺货 | 相等（`diff` 必须 0） |
| checked CSV 回读 | 列名与列序与源文件一致、逐单元格等于分类结果 |
| checked CSV 里每个 PO | 恰好 1 行 Header，且 Header 集合 == Detail 集合 |
| 部分缺货 PO | Header 在、缺货 Detail 不在 |

### 9.6 命名规则（含 PO 数）

`checked0stock {stem}.csv` + `SPS库存检查操作表-{stem}.xlsx`，两边用同一个 `stem`：

1. 取源文件名去掉开头的 `check0stock`（免得叠成 `checked0stock check0stock …`）；
2. 洗掉 Windows 非法字符（`\ / : * ? " < > |`）；
3. **把里面的 `x{N}` 换成筛完剩下的 PO 数**（`order x21 …` → `order x18 …`）。

第 3 条是照 SPS 自己的命名口径来的：它重导一次，文件名里的数字跟流水号一起变。
所以文件名里的数字应当等于里面装了几个 PO。源文件的时间戳/流水号原样保留，
还能对回是哪一次导出。没有 `x{N}` 记号时原样返回（不猜用户想叫它什么）。
见 `stock_precheck._with_po_count()`。

> 与历史的差异：历史 `checked0stock order x19 20260917_0341_630468.csv` 的
> `0341_630468` 是 SPS 重导时生成的新流水号 —— 那一步（在 SPS 界面里点导出）
> 本地做不了，所以本工具保留源导出的流水号。

### 9.7 两个入口（Web）

| 从哪进 | 什么时候用 |
|--------|-----------|
| 导航「检查 SPS 新订单」→ `/checks/new` | 还没筛过：传 SPS 原始 CSV，拿 checked CSV + 操作表 |
| 导航「直接生成发货文件」→ `/jobs/new` | 已经手工筛好：直接传 Packslip PDF + checked CSV |

检查任务成功后，任务页底部有「继续生成发货文件」按钮 → `/jobs/{id}/fulfill`：
**只需再传 Packslip PDF**，系统把上次那份 checked CSV 直接落成新任务的 `order.csv`
（`storage.link_or_copy`），出件范围与预检结果严格一致，人也少传一遍文件。
新任务的 `source_job_id` 指向检查任务，可追溯。
