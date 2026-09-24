---
okf: v0.1
type: Handoff
title: PB 订单履约文件（标签 PDF + 通途 Excel + 背贴）— 子项目交接
tags: [pb, potterybarn, sps, packslip, ups, label, backlabel, tongtu, handoff]
timestamp: 2026-09-22
---

# PB 订单履约文件本地生成

> 从 SPS 导出的「打包单 + UPS 标签」合并 PDF 和订单 CSV，一条命令产出
> **通途导入 Excel** + **给 WXP 的标签 PDF** + **给 WXP 的背贴 PDF**。
> 出件之前还有一步**库存预检**（SPS 原始 New 订单 CSV → checked CSV + SPS 操作表），
> 也做进本模块了（`stock_precheck.py`）。
> 也有网页版：上传 → 后台排队 → 页面看报告与下载（见第 4 节）。
> 原实现是 Google Colab notebook（`1SjFXUYbQf0XwKl5H8B2lRhFBaYbF9d_5`），
> 上传 11MB PDF 受网速影响经常失败，故迁到本地。

> **先读**：[工作流参考](docs/reference/workflow.md)（列映射、坐标表、命名规则、数量对账、
> §9 库存预检口径）。

## 1. 业务背景

- **客户**：Pottery Barn (PB)，走 SPS Commerce 下单/发货，供应商是 Daneey LLC。
- **仓库**：美中仓（USTX / `FZH-DANEEY`）。标签 PDF 命名里的 `FZH-DANEEY` 即此。
- **每批流程**：SPS 导出两个文件 → 本模块出三个文件 → 通途导入 + 把两个 PDF 发给 WXP（皮壳仓库）。
- **出件前必须先筛库存**（重要，2026-09-23 补记）：SPS 的 New 订单要先全选导出原始
  CSV（`check0stock order x{N} …`），按 `Vendor Style` 对照断货清单筛成
  `checked0stock …`，再拿它在 SPS 里勾 ASN 明细、给缺货行发新日期通知，然后才导出
  Packslip PDF。**判定单位是明细行，不是整单** —— 详见坑 21 与 workflow.md §9。
- **下游**：WXP 按标签 PDF 打单发货、按背贴 PDF 贴箱（背贴含中文/西班牙语品名，供仓库与收货方核对）。

## 2. 文件位置（Windows，均在仓库外）

| 角色 | 路径 |
|------|------|
| 输入 Packslip PDF | `D:\Work\美国\Tracy Miller\PB orders\YYYYMMDD\Packslip 美中 x{N} YYYYMMDD.pdf` |
| 输入**原始**订单 CSV（预检用） | `...\YYYYMMDD\check0stock order x{N} YYYYMMDD_HHMM_SSSSSS.csv`（可能在 `NotUsed/` 子目录） |
| 输入订单 CSV（出件用） | `...\YYYYMMDD\checked0stock order x{N} YYYYMMDD_HHMM_SSSSSS.csv` |
| 输入 ASN 发货 CSV（核对用） | `...\YYYYMMDD\shipment x{N} YYYYMMDD_HHMM_SSSSSS.csv` |
| **输出**（默认与输入同目录） | `PB_0_导入_原始_{csv_stem}_on_{ts}.xlsx`<br>`{MM.DD} PotteryBarn label-FZH-DANEEY-Not Prime-第一天.pdf`<br>`{MM.DD} PotteryBarn 背贴-中文西班牙语.pdf`<br>（给了 `--no-stock` 时另有 `无货{N单M件}-…` 子集标签/背贴 + `PB_1`/`PB_2`） |
| **预检输出** | `checked0stock order x{N} YYYYMMDD_HHMM_SSSSSS.csv`<br>`SPS库存检查操作表-order x{N} ….xlsx` |
| 背贴品名源表 | Google Sheet `US SKU Name` → 工作表 `SKUName`（列：通途SKU / 中文名称 / 西班牙语名称） |
| 凭证 | `D:\Work\赛狐\Cursor\secrets\gsheets-service-account.json`（父仓库；worktree 里没有，模块会自动向上查找） |

## 3. 运行

```bash
cd pb_orders
uv run python run_stock_check.py --dir "D:\Work\美国\Tracy Miller\PB orders\20260921" \
    --no-stock "SKU-A,SKU-B"                                  # 步骤 0：库存预检
uv run python run_pb_orders.py --dir "D:\Work\美国\Tracy Miller\PB orders\20260921"
uv run python run_pb_orders.py --dir "..." --dry-run          # 只算不写
uv run python run_pb_orders.py --dir "..." --check-shipment   # 用 ASN 核对实发/缺货
uv run python compare_runs.py --dir "..."                    # 与 <dir>/Colab处理 逐项对比
```

### 3.1 `run_stock_check.py`（步骤 0，薄适配器）

| 参数 | 说明 |
|------|------|
| `--dir` | 当天文件夹；自动取最新 `check0stock*.csv`（跳过 `~$`） |
| `--csv` | 显式指定原始 CSV |
| `--no-stock` | 断货 SKU，逗号分隔；**留空 = 不筛**（等于原样照抄一份） |
| `--out` | 输出目录，默认 = `--dir` |
| `--dry-run` | 走完整流程（含产物自校验）但落在临时目录、不写 `--dir` |

产物：`checked0stock {stem}.csv` + `SPS库存检查操作表-{stem}.xlsx`。
`{stem}` = 原始文件名去掉开头的 `check0stock`（免得叠成 `checked0stock check0stock …`）、
洗掉不合法字符、**再把里面的 `x{N}` 换成筛完剩下的 PO 数**（`order x21 …` → `order x18 …`，
照 SPS 自己的命名口径）；为空回落 `orders`。见 `stock_precheck._with_po_count`。

### 3.2 `run_pb_orders.py`

| 参数 | 说明 |
|------|------|
| `--dir` | 当天文件夹；自动取最新 `Packslip*.pdf` 与 `checked0stock*.csv`（跳过 `~$`） |
| `--pdf` / `--csv` | 显式指定文件名，覆盖自动挑选 |
| `--no-stock` | 无货 SKU，逗号分隔；**默认空 = 不过滤**。给了就按页拆成「有货主文件 + 无货子集」|
| `--no-stock-note` | 无货子集文件名里的描述，默认自动 `{N}单{M}件`，例 `4单6个三角灰97` |
| `--out` | 输出目录，默认 = `--dir` |
| `--check-shipment` | 只读核对 ASN 实发数量并报缺货，不删行 |
| `--allow-unmatched` | join 未匹配时不中止（默认中止，避免标签印空 SKU） |
| `--cache-only` | 背贴品名表只用本地缓存，不联网 |
| `--dry-run` | 只算不写 |

## 4. 网页版服务（FastAPI + Redis/RQ + SQLite）

命令行是薄适配器，真正的编排在 **`service.py`**；网页和队列复用同一层，
所以「命令行产物 = 网页产物」不是承诺而是结构保证。

```
浏览器 ── HTTP ──> pb-orders-web (FastAPI + Jinja)
                      │ 上传分块落盘 → 建 job → 投 RQ
                      ▼
                 pb-orders-redis (独立实例，不映射宿主端口)
                      │
                      ▼
                 pb-orders-worker (python -m web.tasks)
                      │ 调 service.run_job()，cache_only=True
                      ▼
                 runtime/artifacts/<hash 前2位>/<hash 前16位>.<ext>
```

| 文件 | 职责 |
|------|------|
| `service.py` | `run_job()` / `JobOptions` / `JobResult` / `PBJobError`；硬校验与数量对账都在这 |
| `stock_precheck.py` | 步骤 0：`run_stock_check()` / `StockCheckError` / `StockCheckResult` |
| `run_pb_orders.py` | 出件 CLI 薄适配器：把结构化报告打印回原来的控制台格式，退出码不变 |
| `run_stock_check.py` | 预检 CLI 薄适配器 |
| `web/config.py` | 全部配置走环境变量（`PB_ORDERS_*`），本机 fallback 读 `pb_orders/.env` |
| `web/app.py` | 路由：`/`、`/jobs/new`、`/checks/new`、`/jobs/{id}/fulfill`、`/settings`、`/settings/no-stock`、`/jobs/{id}`、`/jobs/{id}/status`、`/jobs/{id}/retry`、`/artifacts/{id}/download`、`/healthz` |
| `web/repository.py` | SQLite：`jobs`（含 `job_type`）/ `artifacts` 两张表 + `app_settings` + 状态机 + 中断恢复；老库启动时自动补 `job_type` 列 |
| `web/storage.py` | 分块上传、SHA-256、内容寻址发布、路径越界防护、`link_or_copy`（checked CSV 复用成出件输入） |
| `web/tasks.py` | worker 入口；**按 `job_type` 分发**（`_RUNNERS`：`fulfillment` / `stock_check`）；异常翻译成用户可读的失败报告 |
| `web/auth.py` | 钉钉 OIDC 登录：闸门中间件、Redis state、可选白名单、URL 前缀 |
| `web/healthcheck.py` | `python -m web.healthcheck web\|worker` |

### 4.1 状态机与恢复

`uploaded → queued → running → succeeded / failed`（终态不再变）。

启动时的恢复**分三种情况**（2026-09-22 起，别再按「一律标失败」理解）：

- 仍处于 `running`：worker 被杀时任务不会自己继续，**标失败** `worker_interrupted`
  （条件更新，盖不掉已成功的），页面给出「用相同输入重新处理」。
- `queued`：**不动**。那条任务还在 Redis 里，新 worker 起来会继续跑。
- `queued` 但 Redis 里已经没有（快照间隔内重启、`FLUSHALL`）：worker 启动时对一次账、
  运行期间每 `PB_ORDERS_QUEUE_WATCH_SECONDS` 秒再对（默认 60），标 `queue_lost` 并可重跑。
  见坑 19。

重跑会**新建 job** 并记 `source_job_id`，输入文件从原 job 目录硬链接过来，
不覆盖历史结果。

### 4.2 离线边界（重要）

- worker 一律 `cache_only=True`，**普通出件绝不访问 Google**。
- 背贴缓存路径由 `PB_ORDERS_SKU_CACHE` / `PB_ORDERS_NLTK_DIR` 指定，
  容器里把 `pb_orders/data` 只读挂到 `/data`。
- 缓存缺失时任务**直接失败**（`cache_missing`），不静默产出 —— 宁可不出件，
  也不能印出没有品名的背贴。
- 刷新缓存是独立管理动作（临时开海外出口 → 导出 → 关掉），不在出件路径上。

### 4.3 隔离边界（对应「不能影响现有服务」）

独立 Compose 项目 `pb-orders`、独立网络 `pb-orders-net`（**不** `external`、
**不**加入 `shipping-net`）、独立 Redis（不映射宿主端口）、容器名全 `pb-orders-*`。
服务器上 Web 绑 **`127.0.0.1`**，公网只能经 NGINX 的 `/pb/` 进来（要过钉钉登录）。

对 NGINX 的改动只有一处：在 `/etc/nginx/conf.d/new-api.conf`（`api.vilavi.cn` 的
server 块，里面本来就同时挂着 `/oidc/`、`/sellfox/`、`/nas/mcp`）里加 `location /pb/`。
改前先备份、`nginx -t` 通过才 `systemctl reload`（**reload 不是 restart**）。

### 4.4 安全边界

- artifact 目录**不做静态目录**，下载只走 `/artifacts/{id}/download`；
- 下载前用 `resolve_artifact_path` 复查绝对路径仍在 artifacts 根之下；
- 上传物理名由服务器生成，用户文件名只用于显示（`safe_display_name` 去掉目录成分）；
- 只接受 `.pdf` / `.csv`；体积在中间件层按 `Content-Length` 提前拒绝，落盘时再按块计数兜底；
- 失败报告只给用户可读文字 + 错误码，堆栈只进容器日志，页面不出现服务器路径。

### 4.5 本机跑测试

```bash
cd pb_orders
uv run pytest tests/ -q
```

137 个用例通过、2 个跳过，**不需要 Redis**：`tests/conftest.py` 用 reportlab 现画一个结构同构的
3 页 Packslip PDF + 5 行订单 CSV + 3 行名称缓存，跑真实流程；Web 用例把
`web.app.enqueue_job` 换成同步执行，从而覆盖「Web 建任务 + worker 处理 + 页面 + 下载」整链。
另有 Redis/RQ 生命周期用例需本地 Docker，设 `PB_ORDERS_RQ_DOCKER=1` 才跑（默认跳过）。

## 5. 函数表

| 文件 | 函数 | 作用 |
|------|------|------|
| `stock_precheck.py` | `run_stock_check(csv, skus, out, progress, name_stem)` | **步骤 0 总入口**：SPS 原始订单 CSV → checked CSV + 操作 Excel + 报告 |
| | `StockCheckError` | 业务失败（`message` / `hint` / `code`），失败时**不产出任何产物** |
| | `_normalized_skus(values)` | 断货清单去重（按小写）并冻结原始写法 → `(snapshot, wanted)` |
| | `_validate(df)` | 必需列 / 只接受 H·D / 明细非空 / 数量正整数 / `(PO, Line)` 唯一 / 每 PO 恰好 1 个 Header |
| | `_classify(work, wanted)` | 明细级判定 + 派生 PO 状态（全部有货 / 部分缺货 / 全部缺货） |
| | `_checked_rows(classified, po_status)` | 保留 Header + 有货明细；整单缺货的 PO 整组剔除 |
| | `_output_stem(raw)` | 输出词干：剥 `check0stock` 前缀 + 洗非法字符 |
| | `_with_po_count(stem, count)` | 把 `x{N}` 换成筛完剩下的 PO 数（SPS 同款命名口径） |
| | `_source_lines(path, rows)` | 按行取源原文（**逐行照搬**用）；行数对不上则报 `ragged_source` |
| | `_build_tables(...)` | 操作表 7 个 sheet；`_detail_table()` 永远并列两个 SKU、数量按整数显示 |
| | `_tables_payload(tables, limit)` | 同一批表转成 `report["tables"]`，供网页渲染；先 `head(limit)`，超限标 `truncated` |
| | `_excel_safe(table)` | 只给 xlsx：转义会被 openpyxl 写成公式的值（条件与 openpyxl 对齐） |
| | `_publish_all(pairs, backup_dir)` | 成对发布：先备份、`os.replace` 覆盖；失败**回滚**并把占用翻译成 `output_locked` |
| | `_verify_checked(...)` | 回读 checked CSV：列序 + 逐单元格 + Header/Detail 对账 |
| | `_style_workbook(path)` | 表头配色、冻结首行、筛选、有货绿/缺货红、部分缺货黄 |
| `run_stock_check.py` | `run(args)` | CLI 薄适配器：调 `stock_precheck.run_stock_check` 后按控制台格式打印 |
| `service.py` | `run_job(pdf, csv, options, output_dir, progress, shipment_csv)` | **编排总入口**（CLI 与 worker 共用），返回 `JobResult(report, artifacts)` |
| | `JobOptions` | `no_stock` / `no_stock_note` / `allow_unmatched` / `cache_only` / `validate_only` / `timestamp` / `sku_cache_path` |
| | `sku_overlay_texts(df)` | 取 SKUxQTY 做叠加文字，NA 换可见占位符（`？？未匹配`） |
| | `shipment_report(csv, df)` | ASN 实发 vs 订购，返回结构化缺货表（不 print） |
| | `scan_dir(dir, ...)` | 自动挑最新输入后调 `run_job` |
| | `PBJobError` | 业务失败（`message` / `hint` / `code`），失败时**不产出任何产物** |
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
| | `extract_pages(src, indices, out)` | 按页序抽出子 PDF（无货子集用） |
| | `build_label_pdf(base, skus, out, page_indices=…)` | 步骤 4 总入口，返回 (路径, 页数)；给 `page_indices` 则只出这些页 |
| `pb_back_label_pdf.py` | `load_sku_name(...)` | 读 Google Sheet（重试 + 本地缓存回退） |
| | `load_english_words()` | nltk words 词表（本地缓存优先，不可用则告警跳过） |
| | `prepare_name_table(...)` | 清洗中文/西语名 + 按通途SKU 去重 |
| | `attach_names(df_rows, df_names)` | 按 Vendor Style 关联品名；返回未匹配 SKU |
| | `build_back_label_pdf(...)` | 步骤 4.2 总入口，返回 (路径, 页数, 未匹配) |
| `run_pb_orders.py` | `run(args)` | CLI 薄适配器：调 `service.run_job` 后按原格式打印 |
| `compare_runs.py` | `compare_xlsx(a, b)` | 通途 xlsx 逐单元格对比 |
| | `compare_pdf(a, b)` | 页数 + 几何签名 + 逐页渲染像素 + 时间戳归一后的文字 |
| | `rebuild_label_with_colab_ts(...)` | 用 Colab 产物里的时间戳重建标签 PDF，再比一次（应 0 差异） |

## 6. 关键常量（改版式只动这里）

| 常量 | 值 | 位置 |
|------|-----|------|
| 通途列数上限 | `MAX_COLS = 100` | `pb_tongtu_excel.py` |
| 固定删除列 | `COLS_TO_DROP`（31 列） | `pb_tongtu_excel.py` |
| 叠加页坐标 | `X1..X7` / `Y1..Y7`（与 notebook 变量一一对应）、`TS_1`、`TS_2` | `pb_label_pdf.py` |
| 裁切框 | `SLIP_LL/UR`、`LABEL_LL/UR`、`LABEL_CROP_LL/UR`、`SLIP_SCALE=0.732` | `pb_label_pdf.py` |
| 背贴页尺寸 | `PAGE_W/H = 288/144`、`COL_WIDTHS` | `pb_back_label_pdf.py` |
| 输出文件名 | `LABEL_PDF_NAME`、`BACK_LABEL_PDF_NAME`、`NO_STOCK_LABEL_PDF_NAME`、`NO_STOCK_BACK_LABEL_PDF_NAME` | 两个 PDF 模块 |

## 7. 踩过的坑（改代码前必读）

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
   给了 `--no-stock` 时的拆页规则：**1:1 校验对全量订单行**（不是过滤后的），
   再按 `Vendor Style` 把「页」分成有货/无货两组 —— join 必须用**全量行**做，
   否则无货页拿不到 SKUxQTY（标签上会缺 SKU）。
6. **notebook cell 29 明文硬编码服务账号私钥**。本版改读 `secrets/gsheets-service-account.json`，
   并支持 worktree 场景向上查找父仓库（见 `_find_service_account`）。
7. **`US SKU Name` 表有重复 `通途SKU` 键**：不去重会让背贴多出页，已加去重 + 告警。
8. **背贴 QTY 会印成 `1.0`**：CSV 的 `Qty Ordered` 因含 NaN 是 float，必须 `astype(int)`（本版 `_qty` 列）。
9. **`'✂'` 用 Helvetica 画不出**（U+2702 缺字形），保持原字符串以与 Colab 输出一致。
10. **打包单/标签页是侧向的**：`/Rotate=90` 是为了把源 PDF 里预转 90° 的 UPS 标签转正，
   同页的打包单因此侧向 —— 这是 notebook 长期行为，历史输出一致，**不要"修正"**。
11. **叠加页坐标的单位陷阱（真踩过）**：reportlab 单位是 point，`36 * mm` 已经是 point；
   notebook 里 `x5 + 30`、`y5 + 140` 加的是 **30/140 point**，不是 mm。
   曾把时间戳 #1 写成 `(66mm, 215mm)`，结果两个时间戳都落到打包单区域、**标签页没有时间戳**。
   叠加元素按裁切框分区：y∈[435,830] 出现在打包单页、y∈[77,367] 出现在标签页 ——
   **改任何叠加坐标后，两页都要检查**。
   常量区已按 notebook 变量名（`X1..X7, Y1..Y7`）一一对应重写，就是为了避免再翻译出单位错误。
12. **`--allow-unmatched` 曾经是「一按就崩」**：未匹配页的 `SKUxQTY` / `Vendor Style` /
   `Qty Ordered` 都是 NA，直接进下游会**连崩两处**——reportlab 画 `nan` 报
   `'float' object has no attribute 'decode'`，背贴 `astype(float).astype(int)` 报
   `IntCastingNaNError`。现在在 `service.run_job` 的 join 之后统一补：
   未匹配行的 `Vendor Style` 填 `？？未匹配`、`Qty Ordered` 按「一页 = 一包裹 = 一件」填 1。
   **不要再把 NA 透传给下游模块**。
13. **对账表要自洽**：拆分时「标签页 / 背贴页」的**总数必须是全量**（`PDF 页数×2` / `订单行数`），
   不能写成有货那份的页数 —— 否则总数 74 而拆分列写 100，自己跟自己打架。
   `reconciliation` 的 `diff` 都由 `total - 各分项` 实算，不再硬编码 0。
14. **前缀化部署下「应用侧路径 ≠ 浏览器可见路径」（真踩过，用户发现）**：
    服务挂在 `/pb/` 下、NGINX 用 `proxy_pass .../` 剥掉前缀，所以应用里
    `request.url.path` 是 `/jobs/x`，而浏览器地址栏是 `/pb/jobs/x`。
    闸门一开始拿 `request.url.path` 当 `return_to`，结果**登录成功后跳到
    `https://api.vilavi.cn/`（域名根路径）** —— 那是公司的 new-api 大模型路由，不是本服务。
    规则：**凡是回写给浏览器的 URL 都必须带 `PB_ORDERS_URL_PREFIX`**
    （重定向、cookie `path`、模板 `href`/`action`、OIDC `redirect_uri`、`return_to`）。
    `safe_return_to` 另外要求落点必须在 `/pb/` 之下，免得在同域里跳到隔壁服务。
    测试要用 `tests/conftest.py` 里的 `StripPrefix` 中间件模拟反代 ——
    直接请求应用侧路径测，等于把 bug 写进断言。
15. **容器默认 UTC，页面时间会少 8 小时**：compose 里统一设 `TZ=Asia/Shanghai`。
    这个变量同时影响**页面上的创建/开始/结束时间**、**标签 PDF 上盖的时间戳**、
    以及**产物文件名里的 `MM.DD`**。老记录是按 UTC 存的，需要一次性纠偏。
16. **「跳页面」的重定向必须用 303，别用框架默认值（真踩过，用户发现）**：
    Starlette `RedirectResponse` 默认 **307**，而 307 会**保留请求方法**。
    退出登录是 POST → 浏览器拿 POST 去请求只接受 GET 的首页 → 闸门又用 307 拦到
    只接受 GET 的 `/oidc-login` → 用户看到 `{"detail":"Method Not Allowed"}`。
    凡是**可能被 POST 触发**的重定向（退出、表单提交后跳转、「重新处理」）一律
    显式 `status_code=303`。**测试要断言状态码本身** —— 只断言 `Location` 的用例
    地址是对的，抓不到这个"方法错了"的 bug。
17. **同站其它服务能带着 cookie 向本服务 POST，所以需要 CSRF 令牌**：
    `api.vilavi.cn` 上还挂着 `/oidc/`、`/sellfox/`、`/nas/mcp`，同域之间
    `SameSite=Lax` 不算跨站，表单 POST 会带上本服务的会话 cookie。
    所以新建任务 / 重新处理 / 退出都必须带 `web/csrf.py` 的令牌
    （`httponly`、Path 限定在本服务前缀下），光靠 SameSite 挡不住。
18. **上传文件的磁盘名固定，数据库里那两列只用于展示**：磁盘一律是
    `inputs/<job-id>/packslip.pdf` / `order.csv`（按槽位校验扩展名），
    不用用户文件名做路径。`jobs.input_packslip` / `input_order` 存的是
    **用户原始文件名**，只给页面显示用 —— 要拼磁盘路径请用
    `storage.PACKSLIP_NAME` / `storage.ORDER_NAME`，拿数据库字段拼会 FileNotFoundError。
19. **重启时别把 `queued` 一律标失败，但也不能不管它**：`queued` 还在 Redis 里，
    重启后 worker 会继续跑，所以只把 `running` 标为中断。但 Redis 也可能整个
    丢队列（compose 是 `--save 60 1 --appendonly no`，快照间隔内重启 / flush 就没了），
    那时数据库里的 `queued` 会永远停在「处理中」。worker 启动时用
    `housekeeping.reconcile_queued` 拿 Redis 侧的 `worker_job_id`
    （`rq.Job.fetch`）对账，查不到就标失败并允许「用相同输入重新处理」。
    启动后再按 `PB_ORDERS_QUEUE_WATCH_SECONDS`（默认 60）对账。RQ 2.12.0 遇到
    Redis `ConnectionError` 是重连而不是退出，所以不能指望容器重启来触发启动对账；
    `FLUSHALL` 同样不断开连接。
20. **`.env` 里的 `PB_ORDERS_DEFAULT_NO_STOCK` 只是初始值，日常维护走页面**：
    断货清单存在 `app_settings` 表（键 `default_no_stock`），网页「断货 SKU」页可改，
    改完**立即生效、不用重启**；只有「从没在页面里设过」时才回落到 `.env`。
    所以看到断货清单不对，先看页面里是不是已经设过 —— 改 `.env` 可能根本没作用。
    解析与去重规则见 `app.parse_sku_list()`（中英文逗号/分号/空格/换行都算分隔，
    按小写去重并保留首次写法），任务页里那份仍然可临时改、只影响当次。
21. **库存判定按「明细行」，不按整单**（真踩过，用户纠正）：
    早期设计是「PO 里只要有一个 SKU 没货就整单剔除」。**这是错的** ——
    PB 会以为整单不发，回头发催单邮件。正确口径：
    ① 全部明细有货 → 原样保留；② **部分缺货 → Header 保留、只剔缺货明细**，
    并在操作表里醒目提示「不要整单取消，ASN 只勾有货明细行」；
    ③ 全部明细缺货 → 整组剔除。`_classify()` 派生 PO 状态、`_checked_rows()` 按行筛。
    已加回归用例 `test_detail_level_filter_keeps_header_for_mixed_po`。
22. **checked CSV 必须与 SPS 导出**逐字节**同构，不能重新序列化**（真踩过）：
    SPS 的导出是**参差**的 —— 表头 147 列、数据行 146 列、**最后一个列名是空的**。
    读进 pandas 再 `to_csv` 写回去会得到：空列名写成字面量 `Unnamed: 146`、
    数据行被补齐到 147 列（每行多一个尾逗号）、还可能带 BOM。
    正解：`_source_lines()` 取原文行，按保留行的索引**逐行照搬**；UTF-8 **不带 BOM**、LF。
    实测 2026-09-17 真实批次与历史 `checked0stock order x19 …csv`
    **SHA-256 完全相同**（`e99a9b78…`，19,363 字节）。
    字段里含换行时按行切分不成立 → 报 `ragged_source`，宁可不出件也不出格式不同的文件。
    锁定用例：`test_checked_csv_is_byte_identical_to_a_sps_style_export`。
23. **操作表的每个明细表都要并列两个 SKU**（用户明确要求，别"精简"掉）：
    `Buyers Catalog or Stock Keeping #`（**对方** SKU，用来在 SPS 界面里定位明细行）
    与 `Vendor Style`（**我方** SKU，内部对照 + 库存匹配的键）缺一不可。
    用户原话：「ASN 有货明细表 缺货明细表 等等 永远！需要我们自己的 SKU！」
    —— 别把「SPS 界面里只显示对方 SKU」理解成「报表里不用给我方 SKU」。
24. **网页版续出件不要人再传一遍 checked CSV**：检查任务成功后走
    `GET/POST /jobs/{job_id}/fulfill`，只需传 Packslip PDF；worker 侧用
    `storage.link_or_copy` 把已发布的 `checked_order` 产物落成新任务的 `order.csv`。
    新任务 `job_type=fulfillment`、`source_job_id` 指向检查任务、**`no_stock` 留空**
    （checked CSV 已经剔过缺货明细，再传一遍断货清单是多此一举）。
    别用数据库里的展示文件名去拼路径（坑 18）。
25. **明细表要在网页上也能看，且与 xlsx 同源**（用户追问「网页版明细表为啥没做」）：
    操作表只构建**一次**（`tables = _build_tables(...)`），xlsx 与
    `report["tables"] = _tables_payload(tables, WEB_TABLE_LIMIT)` 都从它来 ——
    别在模板里另算一遍，否则网页和操作表迟早对不上。
    超过 300 行截断并**在页面上写明**「只显示前 N 行 / 共 M 行，完整看 xlsx」。
    旧任务（改版前的 `report_json`）没有 `tables`，模板整段跳过，不能 500。
26. **产物名里的 `x{N}` 是筛完剩下的 PO 数**（用户要求）：`order x21 …` → `order x18 …`。
    照 SPS 自己的命名口径（它重导时数字会变），文件名的数字应当等于里面装了几个 PO。
    源导出里的时间戳/流水号**保留**，还能对回是哪一次导出 —— 本地做不了 SPS 那一步重导，
    所以不要试图连流水号一起"修正"。见 `_with_po_count()`。
27. **断货 SKU 的输入解析必须走 `app.parse_sku_list()`，不能 `split(",")`**（Cursor 复审发现）：
    两个入口的 textarea 都写着「逗号或换行分隔」，只按逗号切会把多行输入当成**一个** SKU，
    结果缺货行被静默保留 —— 看起来"跑通了"，实际筛漏了。`/checks/new` 与 `/jobs/new`
    两处都改过来了（同一个缺陷）。测试：`test_newline_separated_no_stock_is_split`、
    `test_fulfillment_route_also_splits_newlines`。
28. **回读校验要比「源文件原文」，不能比规范化后的 DataFrame**（Cursor 复审发现）：
    `_validate()` 会去空格、把 Record Type 转大写，而输出是**逐行照搬原文**的。
    早先 `_verify_checked` 拿规范化后的 `checked` 去比回读结果，导致源文件里
    Record Type 写成小写 `d`、或字段两侧带空格这种**合法输入**误报 `output_verify_failed`
    （内容其实没写错）。正解：比 `source.loc[checked.index]`（原文）；
    Header/Detail 对账那条则先 `strip().upper()` 再判。
29. **同名产物要能覆盖，且必须整体发布**（Cursor 复审发现）：
    CLI 默认输出到输入目录，同一批重跑会撞同名 —— Windows 上 `shutil.move`（内部 `os.rename`）
    直接失败；更糟的是原来先移 CSV 再移 XLSX，第二个失败就留下「新 CSV + 旧 XLSX」。
    现在 `_publish_all()` 先把将被覆盖的旧文件备份到同卷临时目录，再 `os.replace()` 原子覆盖，
    **中途任何一步失败都回滚**（还原旧的、或删掉刚放上去的），`report["replaced"]` 记下被覆盖的文件名。
30. **别用 `open(path, "ab")` 预探「文件是否被占用」**（实测踩到）：
    想「先探一遍再发布」，实测**探不出字节区间锁**（`msvcrt.locking` / Excel 常是这一类）——
    预探通过、真正的失败出现在后面 `copy2` / `os.replace` 上，用户看到的是一坨 `PermissionError`
    堆栈（CLI 只捕获 `StockCheckError`）。
    正解：不做预探，**在 `_publish_all()` 里动手时捕获 `OSError`**，`PermissionError` 翻译成
    `output_locked` + 「可能正在 Excel 里打开，请关闭后重跑」，并回滚已发布的。
    只有真动手时才知道能不能动。锁定用例：`test_locked_output_is_refused_without_publishing_anything`、
    `test_permission_error_during_replace_is_readable_and_rolls_back`、
    `test_partial_publish_failure_rolls_back`。
31. **写 xlsx 前要转义公式，但只转义 `=`**（Cursor 复审发现 + 实测定界）：
    操作表里的 PO/SKU 来自外部 CSV，openpyxl 会把以 `=` 开头的字符串写成 `<f>` **公式**
    （`=cmd|…` 在 Excel 里会执行）。`_excel_safe()` 给这类值加 `'` 前缀，**只作用于 xlsx**；
    checked CSV 仍是逐行照搬的原始字节。
    条件与 openpyxl 内部**逐字对齐**（`len(value) > 1 and startswith("=")`，实测 3.1.5 源码）。
    **不要顺手把 `+` / `-` / `@` 也加进来**：实测这三个开头的值 openpyxl 存的是
    `t="inlineStr"` 文本单元格，Excel 不会把 xlsx 里的文本单元格再当公式解析
    （那是 CSV 的注入面）；加了反而会把 `-1`、`+A1` 这类正常值改坏。
32. **`report["tables"]` 要 `head(limit)` 再转列表**（Cursor 复审发现）：
    先把整表 `astype(str).values.tolist()` 再切片，会为每一行都建 Python 对象；大表在 1G 的
    worker 里没必要地吃内存。现在先 `head(limit)`，总数单用 `len(table)`。
33. **SQLite 加列要容忍 duplicate column 竞争**（Cursor 复审发现）：
    Web 与 worker 同时启动、同时看到旧库缺 `job_type`，就会同时 `ALTER TABLE`，
    输的那个收到 `duplicate column name`。SQLite 没有 `ADD COLUMN IF NOT EXISTS`，
    而那一刻「列已经在了」正是想要的结果，所以只放过这一种 `OperationalError`
    （别的 SQLite 错误照旧抛）。测试：`test_migration_tolerates_losing_the_alter_race` +
    `test_migration_does_not_swallow_other_sqlite_errors`。

## 8. 数量对账口径

### 8.1 库存预检（步骤 0）

- `PO 总数 = 全有货 + 部分缺货 + 全部缺货`。
- `Detail 总数 = 有货 + 缺货`，`diff` 必须 0（`_classify` 的分类互斥完备）。
- `数量总数 = 有货 + 缺货`，`diff` 必须 0。
- checked CSV 回读校验：列名与列序与源文件一致、**逐单元格**等于分类结果、
  每个 PO 恰好 1 行 Header、Header 集合 == Detail 集合。
- 部分缺货 PO：Header 在、缺货 Detail 不在。

### 8.2 出件（步骤 1-2 / 3 / 4）

- 订单 CSV 原始 `N` 行 → 留 `Record Type == 'D'` → 按 `Qty Ordered` 拆行 → **行数必须等于 PDF 页数**（1:1 硬校验）。
- 无货过滤时：`通途总行 = 可导入 + 无库存`，差必须为 0。
- 拆页时：`PDF 总页数 = 有货页 + 无货页`，差必须为 0；两个子集文件的页**不重不漏**
  （主/无货背贴的 `PO: PO-Line` 集合交集为空、并集等于全量）。
- 输出页数：标签 PDF = 输入页数 × 2；背贴 PDF = 订单行数。

## 9. 本会话成果

### 2026-09-23（库存预检：把「出件前那一天的手工筛选」也做进本模块）

- **动机**：出件用的 `checked0stock` CSV 不是 SPS 直接给的 —— 得先把当批 New 订单
  全选导出原始 CSV，按 `Vendor Style` 对照断货清单筛掉缺货明细，再在 SPS 里勾 ASN。
  这一步以前靠人在 Excel 里做。用户要求「上传原始 CSV → 出台账 → checked CSV 能直接
  接着出件，且不用重传」。
- **新增 `stock_precheck.py`（步骤 0）** + `run_stock_check.py`（CLI）：
  `run_stock_check(csv, skus, out, progress, name_stem)` → checked CSV + 操作 Excel + 报告。
  硬校验：必需列、只接受 H/D、明细非空、数量正整数、`(PO, Line)` 唯一、
  每个 PO 恰好 1 个 Header、无孤儿 Header。**通过校验前不产出任何产物**。
- **口径（用户纠正两次才定下）**：
  - 判定单位是**明细行**（坑 21）：部分缺货的 PO 保留 Header、只剔缺货明细；
    只有全部明细缺货才整组剔除。早期「有一个没货就整单剔」是错的，会让 PB 发催单邮件。
  - 每个明细表**永远并列两个 SKU**（坑 23）：对方 `Buyers Catalog or Stock Keeping #`
    （在 SPS 里定位行）+ 我方 `Vendor Style`（对照与匹配）。
- **checked CSV 与 SPS 导出的那份**字节级一致**（坑 22，本批最硬的验收）**：
  2026-09-17 真实批次（`check0stock order x21 20260917_0338_456788.csv`，21 PO / 23 明细，
  断货只填 `CEN961NLINEN-SAGEGREEN-138`）→ 与历史
  `checked0stock order x19 20260917_0341_630468.csv` **SHA-256 完全相同**
  （`e99a9b78…`，19,363 字节）。做法是**逐行照搬源文件原文**而不是重新序列化
  （SPS 导出是参差的：表头 147 列、数据行 146 列、末列无名）。
- **操作 Excel 7 个 sheet**：操作总览 / 部分缺货PO-逐行操作 / ASN有货明细 / 缺货明细 /
  全部缺货PO / 检查报告 / 原始剔除行；有货绿、缺货红、部分缺货黄、冻结首行 + 筛选。
- **网页两入口 + 续出件**（坑 24）+ **网页版明细表**（坑 25）：
  导航「检查 SPS 新订单」（`/checks/new`）与「直接生成发货文件」（`/jobs/new`）分开；
  检查任务成功后任务页出现「继续生成发货文件」（`/jobs/{id}/fulfill`），
  **只需再传 Packslip PDF**，worker 用 `storage.link_or_copy` 把上次那份 checked CSV
  落成新任务的 `order.csv`，`source_job_id` 指向检查任务。
  任务页同时列出部分缺货 PO / ASN 有货明细 / 缺货明细 / 全部缺货 PO 四张逐行表，
  与 xlsx 同源（同一批 DataFrame），两个 SKU 并列、数量按整数显示。
- **产物名里的 PO 数**（坑 26）：`x{N}` 换成筛完剩下的数量（`order x21 …` → `order x18 …`），
  源导出里的时间戳/流水号保留以便回溯。
- **数据库**：`jobs` 表加 `job_type`（`fulfillment` / `stock_check`），
  老库启动时 `ALTER TABLE` 自动补列（默认 `fulfillment`）—— 已有任务不会丢。
  worker 按 `job_type` 走 `_RUNNERS` 分发，两种流程共用同一套「跑完发布产物」外壳。
- **产物类型**：新增 `checked_order` / `stock_operations` 两个 artifact kind 与中文标签。
- **测试 89 → 137**（新增 48）：预检服务 23 例（含字节级一致、参差形状、含换行拒绝、
  命名与 PO 数、网页表负载与截断、重跑覆盖、占用拒绝与回滚、公式转义、冗余空白）、
  worker 分发 2 例、仓库迁移 3 例、Web 两入口 / 续出件 / 网页明细表 / 旧任务兼容 15 例、
  出件产物命名与缺列提示 5 例。

### 2026-09-21（从 Colab 迁到本地）

- 从 Colab notebook 迁移步骤 1、2、3（跳过 3.x 赛狐导入）、4、4.2 到本地，新建本子项目。
- 20260921 实测：PDF 50 页 / 唯一 PO 40 / 通途 **50 行 × 100 列** / join 未匹配 **0** /
  标签 PDF **100 页** / 背贴 PDF **50 页**；ASN 核对 50 件全发、无缺货。
- **与当天真实 Colab 产物逐项对齐**（`20260921/Colab处理/`，用户当天 16:44 跑的）：

| 产物 | 对比结果 |
|------|---------|
| 通途 xlsx | 形状 50×100、列名一致、**5000 个单元格 0 处不同** |
| 背贴 PDF | 页数一致、文件字节数一致（65,576）、**渲染像素完全相同**（200dpi 抽 3 页，0 差异） |
| 标签 PDF | 100 页；差异只剩**时间戳的数字**（我的运行时刻 vs Colab 的 16:44）。**把时间戳替换成 Colab 的值重建后，100 页 0 个不同像素** |
| 页面几何 | 100 页的 mediabox / cropbox / `/Rotate` 签名**完全一致**；图片 bbox 完全一致 |
| 叠加元素 | 打包单页时间戳、标签页时间戳、箭头、SKUxQTY 的 bbox **完全一致** |

- 也用 20260917 的历史产物做了同源对照，几何与版式一致。
- **可复现**：以上结论固化成 `compare_runs.py`（同一批数据、`--dir` 一条命令），
  用户可自行复跑；退出码 0/1，便于以后每批先比再决定用不用。

### 2026-09-22（网页版 + 隔离部署 + 上机 EN 测试服务器 + 公网 HTTPS/钉钉登录）

- **抽出 `service.py`**：CLI 与队列共用同一编排层、同一套硬校验和数量对账。
  重构后重跑 20260921 真实批次：通途 xlsx **0/5000 单元格差异**、
  背贴 PDF **字节数与像素完全一致**、标签 PDF 归一化时间戳后 **0 像素差异** ——
  与重构前、与 Colab 都等价。
- **网页版上线**：FastAPI + Jinja（无 CDN、无 SPA）+ Redis/RQ + SQLite。
  真实批次实测：上传 11MB PDF → 后台 6 秒出件 → 页面展示对账与校验明细 → 逐个下载，
  下载回来的产物与命令行产物 **50 页 0 像素差异**。
- **无货拆分走通网页**：真实 SKU `CENC/LINEN-IVORY-60` + `CEN1607NLINEN-IVORY-138`
  → 有货 37 页 / 无货 13 页（自动命名 `无货9单13件`），4 条对账口径差全为 0，
  7 个产物分类正确（主件只含有货、无货子集独立）。
- **重启验收**：停 worker → 任务停在 `queued` → 重启 Web，该任务被标
  `worker_interrupted` 且可「用相同输入重新处理」；已成功任务仍可查询、**下载仍 200**。
- **失败路径验收**：故意用 49 页 PDF 触发 1:1 失败 → 页面给出可读原因 + 导出提示 + 错误码，
  **0 个可下载产物、0 处服务器路径泄露**。
- **补齐 42 个自动化测试**（合成夹具，无需 Redis/客户数据），并修掉两个真实缺陷：
  `--allow-unmatched` 的 NA 崩溃（坑 12）、拆分时对账表总数与分项打架（坑 13）。
- **本机 Docker Desktop 启动失败**（`connect ENOENT \\.\pipe\errorReporter`，后台服务异常退出），
  容器构建与 `docker compose up` 未能在本机实测（Compose 配置已过 `docker compose config`）。
  本地验收改用 WSL 里的 Redis + 本机 Python 进程完成；**容器链路直接在 EN 测试服务器上验证**。
- **已上机 EN 测试服务器**（`sh-erpnext-test` / 8.133.254.66 → `/opt/pb-orders`）：
  三个容器 healthy，入口 `http://100.119.28.72:8412`（**仅 Tailscale**，公网 8412 拒绝连接）。
  构建**必须**带 `--build-arg PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple`
  —— 服务器上 PyPI 索引可达但包文件下载超时；Docker 镜像源已配 daocloud，基础镜像不用管。
  限额按实测 492MB 峰值定为 worker 1g / web 384m / redis 128m（服务器可用内存仅约 1.9Gi）。
  既有 6 个容器部署前后**运行时间一字未变**；脱敏样例端到端跑通，整栈 restart 后任务仍可查可下。
  细节见 `docs/reference/server-deployment-architecture.md` 第 11.4 节。

#### 附：Colab 产物在 Acrobat 里全白（已定位差异，未影响本版）

用户反馈：Colab 生成的标签 PDF 在 Windows Acrobat 里**全白**，Chrome 正常；本版产物 Acrobat 正常。
可验证的差异只有一处 —— **每页 /Resources 里有 2 个内联字体字典**（PyPDF2 `merge_page` 的写法）：

| 文件 | 内联字体字典 | UUID 资源名 | 内容流超长浮点 |
|------|------------|------------|---------------|
| 本版（今天） | **0** | 0 | 0 |
| Colab（今天，100 页） | 200 | 200 | 100 |
| Colab（20260917，42 页） | 84 | 84 | 42 |
| Colab（20260914，64 页） | 128 | 128 | 64 |

即 **每个 Colab 产物都是 2 个/页**，是长期存在的写法，不是今天才有的。
页面几何、图片对象（52 种 / 10.91MB）两版完全一致，qpdf（`pikepdf.Pdf.open(attempt_recovery=False)`）
对两版都不报错，所以不是结构性损坏。本机无 Acrobat 可测，
**推断**是内联字体字典触发 Acrobat 的严格渲染路径；本版全部是规范间接引用。
历史那些 Colab PDF 若在 Acrobat 打不开，可重跑本工具再生成一份。

## 10. 交接清单

- [x] 步骤 1-2/3/4/4.2 本地可跑通，端到端实测通过
- [x] 与历史产物几何/版式对齐
- [x] 凭证不落仓库（读父仓库 secrets/）
- [x] OKF 文档 + 根索引同步
- [x] 无货时自动拆「有货主文件 + 无货子集」（标签 + 背贴各两份，`--no-stock` 触发）
- [x] 网页版：FastAPI + Redis/RQ + SQLite，任务可后台跑、可追溯、可重下（2026-09-22）
- [x] 独立 Docker Compose 栈，不碰既有服务（2026-09-22）
- [x] 137 个自动化测试（另有 Redis/RQ 生命周期用例，默认跳过），不需要 Redis 也能跑
- [x] 已部署到 EN 测试服务器（`/opt/pb-orders`）。入口 **<https://api.vilavi.cn/pb/>**
      （公网 HTTPS + 钉钉登录，容器只绑 `127.0.0.1`）；Tailscale 那条路径已弃用（走香港中继太慢）
- [x] 公网入口有钉钉登录闸门（`web/auth.py`）。**登录范围由桥把关**：2026-09-23 起桥按
      组织成员判定（查本公司通讯录），只有本公司员工能进；`PB_ORDERS_ALLOWED_USERS`
      留空即可，只在需要再窄一层时才填
- [x] 队列对账：`queued` 不再被重启一刀切标失败之后，worker 启动对一次、运行期间每 60 秒再对一次
      （`PB_ORDERS_QUEUE_WATCH_SECONDS`，0 = 关）。Redis 丢队列时任务会被标 `queue_lost` 并可重跑
- [x] 保留策略：启动时按 `PB_ORDERS_RETENTION_DAYS`（默认 90 天）清理已完成任务与无人引用的产物。
      **只在服务/worker 启动时跑，不是定时任务**
- [x] 同站 POST 带 CSRF 令牌（`web/csrf.py`）；上传磁盘名固定，原始文件名只用于展示
- [x] 断货 SKU 列表可在**网页上自己维护**（导航「断货 SKU」→ `app_settings` 表），
      改完立即影响新建任务的预填，不用改服务器 `.env`、不用重启（2026-09-23）
- [x] 库存预检（步骤 0）：上传 SPS 原始订单 CSV → checked CSV + SPS 操作表；
      判定按明细行、部分缺货 PO 保留 Header；checked CSV 与 SPS 导出的那份**字节级一致**
      （2026-09-23，见坑 21-23 与 workflow.md §9）
- [x] 网页两入口分开（「检查 SPS 新订单」/「直接生成发货文件」）；
      检查成功后「继续生成发货文件」**只需再传 Packslip PDF**，checked CSV 自动复用（2026-09-23）
- [ ] 部分发货的一单跨两份 PDF 时，仍需人工确认哪些页给谁（目前按 SKU 自动拆）
- [ ] 原 notebook 步骤 3.x（赛狐导入）、4.3（按仓库分拆，20260831 起停用）—— 未迁
- [x] 库存预检**已部署到 EN 测试服务器**（2026-09-24，代码 `598baae`，`PB_ORDERS_PIPELINE_VERSION=pb-web-598baae`）；公网入口真机端到端验收通过：147 列宽表上传 → checked CSV（列/参差形状原样）→ 续出件只传 PDF → 1:1 通过、三件产物可下载。见 docs/log.md 第十四轮
- [ ] **待修**：网页出件的通途 xlsx 名是 `…_order_on_…`（磁盘名固定 `order.csv` 导致），看不出是哪一批；命令行无此问题。修法：把 `job["input_order"]` 的 stem 传进 `service.run_job` 用于命名
- [ ] EN 测试服务器上留了 4 条 `actor=验收测试` 的任务，需要时清理
