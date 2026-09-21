---
okf: v0.1
type: Handoff
title: PB 订单履约文件（标签 PDF + 通途 Excel + 背贴）— 子项目交接
tags: [pb, potterybarn, sps, packslip, ups, label, backlabel, tongtu, handoff]
timestamp: 2026-09-21
---

# PB 订单履约文件本地生成

> 从 SPS 导出的「打包单 + UPS 标签」合并 PDF 和订单 CSV，一条命令产出
> **通途导入 Excel** + **给 WXP 的标签 PDF** + **给 WXP 的背贴 PDF**。
> 原实现是 Google Colab notebook（`1SjFXUYbQf0XwKl5H8B2lRhFBaYbF9d_5`），
> 上传 11MB PDF 受网速影响经常失败，故迁到本地。

> **先读**：[工作流参考](docs/reference/workflow.md)（列映射、坐标表、命名规则、数量对账）。

## 1. 业务背景

- **客户**：Pottery Barn (PB)，走 SPS Commerce 下单/发货，供应商是 Daneey LLC。
- **仓库**：美中仓（USTX / `FZH-DANEEY`）。标签 PDF 命名里的 `FZH-DANEEY` 即此。
- **每批流程**：SPS 导出两个文件 → 本模块出三个文件 → 通途导入 + 把两个 PDF 发给 WXP（皮壳仓库）。
- **下游**：WXP 按标签 PDF 打单发货、按背贴 PDF 贴箱（背贴含中文/西班牙语品名，供仓库与收货方核对）。

## 2. 文件位置（Windows，均在仓库外）

| 角色 | 路径 |
|------|------|
| 输入 Packslip PDF | `D:\Work\美国\Tracy Miller\PB orders\YYYYMMDD\Packslip 美中 x{N} YYYYMMDD.pdf` |
| 输入订单 CSV | `...\YYYYMMDD\checked0stock order x{N} YYYYMMDD_HHMM_SSSSSS.csv` |
| 输入 ASN 发货 CSV（核对用） | `...\YYYYMMDD\shipment x{N} YYYYMMDD_HHMM_SSSSSS.csv` |
| **输出**（默认与输入同目录） | `PB_0_导入_原始_{csv_stem}_on_{ts}.xlsx`<br>`{MM.DD} PotteryBarn label-FZH-DANEEY-Not Prime-第一天.pdf`<br>`{MM.DD} PotteryBarn 背贴-中文西班牙语.pdf` |
| 背贴品名源表 | Google Sheet `US SKU Name` → 工作表 `SKUName`（列：通途SKU / 中文名称 / 西班牙语名称） |
| 凭证 | `D:\Work\赛狐\Cursor\secrets\gsheets-service-account.json`（父仓库；worktree 里没有，模块会自动向上查找） |

## 3. 运行

```bash
cd pb_orders
uv run python run_pb_orders.py --dir "D:\Work\美国\Tracy Miller\PB orders\20260921"
uv run python run_pb_orders.py --dir "..." --dry-run          # 只算不写
uv run python run_pb_orders.py --dir "..." --check-shipment   # 用 ASN 核对实发/缺货
```

| 参数 | 说明 |
|------|------|
| `--dir` | 当天文件夹；自动取最新 `Packslip*.pdf` 与 `checked0stock*.csv`（跳过 `~$`） |
| `--pdf` / `--csv` | 显式指定文件名，覆盖自动挑选 |
| `--no-stock` | 无货 SKU，逗号分隔；**默认空 = 不过滤** |
| `--out` | 输出目录，默认 = `--dir` |
| `--check-shipment` | 只读核对 ASN 实发数量并报缺货，不删行 |
| `--allow-unmatched` | join 未匹配时不中止（默认中止，避免标签印空 SKU） |
| `--cache-only` | 背贴品名表只用本地缓存，不联网 |
| `--dry-run` | 只算不写 |

## 4. 函数表

| 文件 | 函数 | 作用 |
|------|------|------|
| `sps_pb_pdf.py` | `build_page_df(pdf)` | 步骤 1-2：每页抽 PO + Item Number，派生 Line / Line Count / PO Number-Line |
| | `extract_po_number(page)` | 正则 `Purchase Order Number (\d{9,})` 取首个 |
| | `extract_item_number(page)` | 第一个 `Item Number` 表头**下方**第一个纯 7-10 位数字行 |
| | `join_pages_with_orders(df_pdf, df_order)` | 按 (PO, Item Number = Buyer Catalog #) 关联出 SKUxQTY |
| `pb_tongtu_excel.py` | `build_order_df(csv)` | 步骤 3：读 CSV → 组内 ffill → 留 D 行 → 拆数量 → 派生列 → 砍到 ≤100 列 |
| | `split_no_stock(df, skus)` | 按无货 SKU 拆分（大小写不敏感） |
| | `export(...)` | 写 `PB_0/PB_1/PB_2` 导入文件 |
| `pb_label_pdf.py` | `make_sku_overlay_pdf(skus, ...)` | 生成 SKUxQTY 叠加页（A4 竖版、文字转 90°） |
| | `merge_overlay(base, overlay, out)` | 逐页 `merge_page` 到原 PDF |
| | `crop_split_pdf(src, out)` | 每页裁成两页（打包单 / UPS 标签），顺序 单_i, 标签_i |
| | `build_label_pdf(base, skus, out)` | 步骤 4 总入口，返回 (路径, 页数) |
| `pb_back_label_pdf.py` | `load_sku_name(...)` | 读 Google Sheet（重试 + 本地缓存回退） |
| | `load_english_words()` | nltk words 词表（本地缓存优先，不可用则告警跳过） |
| | `prepare_name_table(...)` | 清洗中文/西语名 + 按通途SKU 去重 |
| | `attach_names(df_rows, df_names)` | 按 Vendor Style 关联品名；返回未匹配 SKU |
| | `build_back_label_pdf(...)` | 步骤 4.2 总入口，返回 (路径, 页数, 未匹配) |
| `run_pb_orders.py` | `run(args)` | 编排 + 数量对账 + 1:1 硬校验 |
| | `check_shipment(dir, df)` | ASN 实发 vs 订单数量核对 |

## 5. 关键常量（改版式只动这里）

| 常量 | 值 | 位置 |
|------|-----|------|
| 通途列数上限 | `MAX_COLS = 100` | `pb_tongtu_excel.py` |
| 固定删除列 | `COLS_TO_DROP`（31 列） | `pb_tongtu_excel.py` |
| 叠加页坐标 | `ARROW_1/2`、`ARROW_LEFT`、`SKU_POS_1/2`、`SCISSOR_1/2`、`TS_MM/TS_PT` | `pb_label_pdf.py` |
| 裁切框 | `SLIP_LL/UR`、`LABEL_LL/UR`、`LABEL_CROP_LL/UR`、`SLIP_SCALE=0.732` | `pb_label_pdf.py` |
| 背贴页尺寸 | `PAGE_W/H = 288/144`、`COL_WIDTHS` | `pb_back_label_pdf.py` |
| 输出文件名 | `LABEL_PDF_NAME`、`BACK_LABEL_PDF_NAME` | 两个 PDF 模块 |

## 6. 踩过的坑（改代码前必读）

1. **pandas 3.0 不兼容 Colab 写法**：`fillna(method='ffill')` 已删除；`groupby().apply(..., include_groups=True)` 已禁用；
   `groupby.ffill()` 会**丢掉分组键**，需用 `pd.concat([po_keys, ffilled], axis=1)` 拼回（直接赋值会触发 `PerformanceWarning`）。
2. **`copy(page)` 不隔离 `/Contents`**：pypdf 的 `copy(page)` 只复制页字典，`/Contents` 仍是同一个间接对象，
   在一份拷贝上 `scale_by(0.732)` 会**污染另一份**（实测标签页被缩成 0.732 倍）。绕路试过两个错方向，别再踩：
   - 「两趟处理各写一个中间 PDF」→ 结果对但**同一张图各存一份**：图片对象 130→260、体积 12.8MB→24MB（邮件发不出去）。
   - 「把克隆的 `/Contents` 挂到 writer 再 `scale_by`」→ pypdf 报 `Cannot update PdfReader with external object`。
   - ✅ 正解：**同一个 `PdfReader` 只读一遍**，两份拷贝只改页字典；缩放自己实现
     （`_scale_boxes_about_origin` 缩放各 box + `_prepend_scale_matrix` 往内容前置 `cm` 矩阵），
     图片等资源仍共享。实测 130 个图片对象 / 13.0MB，与 Colab 一致。
3. **坐标原点**：pypdf/PyPDF2 左下角，PyMuPDF 左上角。裁切坐标**逐字照搬** notebook，不要用 PyMuPDF 重写。
4. **`PO Line #` 必须保持字符串**（读 CSV 时已在 `DTYPE_STR` 里声明为 str）。
   若为了排序做 `pd.to_numeric`，导出列会从 `'1'` 变成 `1`（实测 50 个单元格与 Colab 不一致）。
   notebook 本来就按字典序排序，保持字符串即可。
5. **Colab 的「无货 SKU」是死代码**：参数是字符串，`for sku in zero_stock_skus` 迭代的是**单个字符**，
   `isin()` 永不命中，所以过滤从未生效（历史文件夹里只有 `PB_0_导入_原始_`）。本版做成真正可用，默认留空。
6. **notebook cell 29 明文硬编码服务账号私钥**。本版改读 `secrets/gsheets-service-account.json`，
   并支持 worktree 场景向上查找父仓库（见 `_find_service_account`）。
7. **`US SKU Name` 表有重复 `通途SKU` 键**：不去重会让背贴多出页，已加去重 + 告警。
8. **背贴 QTY 会印成 `1.0`**：CSV 的 `Qty Ordered` 因含 NaN 是 float，必须 `astype(int)`（本版 `_qty` 列）。
9. **`'✂'` 用 Helvetica 画不出**（U+2702 缺字形），保持原字符串以与 Colab 输出一致。
10. **打包单/标签页是侧向的**：`/Rotate=90` 是为了把源 PDF 里预转 90° 的 UPS 标签转正，
   同页的打包单因此侧向 —— 这是 notebook 长期行为，历史输出一致，**不要"修正"**。

## 7. 数量对账口径

- 订单 CSV 原始 `N` 行 → 留 `Record Type == 'D'` → 按 `Qty Ordered` 拆行 → **行数必须等于 PDF 页数**（1:1 硬校验）。
- 无货过滤时：`通途总行 = 可导入 + 无库存`，差必须为 0。
- 输出页数：标签 PDF = 输入页数 × 2；背贴 PDF = 订单行数。

## 8. 本会话成果（2026-09-21）

- 从 Colab notebook 迁移步骤 1、2、3（跳过 3.x 赛狐导入）、4、4.2 到本地，新建本子项目。
- 20260921 实测：PDF 50 页 / 唯一 PO 40 / 通途 **50 行 × 100 列** / join 未匹配 **0** /
  标签 PDF **100 页** / 背贴 PDF **50 页**；ASN 核对 50 件全发、无缺货。
- **与当天真实 Colab 产物逐项对齐**（`20260921/Colab处理/`，用户当天 16:44 跑的）：

| 产物 | 对比结果 |
|------|---------|
| 通途 xlsx | 形状 50×100、列名一致、**5000 个单元格 0 处不同** |
| 背贴 PDF | 页数一致、文件字节数一致（65,576）、**渲染像素完全相同**（200dpi 抽 3 页，0 差异） |
| 标签 PDF | 页数一致、体积 13.0MB vs 12.8MB；**差异仅在 x=382..396 一条竖带 = 时间戳文字**（两次绘制、两个 y 带），即我的运行时间 17:2x 与 Colab 的 16:44 不同 |
| 页面几何 | mediabox / cropbox / `/Rotate` 与图片 bbox **完全一致**（`(-38,-446)-(437,-417)`、`(3,3)-(428,286)`） |

- 也用 20260917 的历史产物做了同源对照，几何与版式一致。

## 9. 交接清单

- [x] 步骤 1-2/3/4/4.2 本地可跑通，端到端实测通过
- [x] 与历史产物几何/版式对齐
- [x] 凭证不落仓库（读父仓库 secrets/）
- [x] OKF 文档 + 根索引同步
- [ ] 无货/部分发货时自动生成「无货子集」PDF（历史是人工做，见 `20250821/缺货/`）—— 本轮未做
- [ ] 原 notebook 步骤 3.x（赛狐导入）、4.3（按仓库分拆，20260831 起停用）—— 本轮未迁
