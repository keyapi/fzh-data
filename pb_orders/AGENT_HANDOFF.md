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
> 也有网页版：上传 → 后台排队 → 页面看报告与下载（见第 4 节）。
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
| **输出**（默认与输入同目录） | `PB_0_导入_原始_{csv_stem}_on_{ts}.xlsx`<br>`{MM.DD} PotteryBarn label-FZH-DANEEY-Not Prime-第一天.pdf`<br>`{MM.DD} PotteryBarn 背贴-中文西班牙语.pdf`<br>（给了 `--no-stock` 时另有 `无货{N单M件}-…` 子集标签/背贴 + `PB_1`/`PB_2`） |
| 背贴品名源表 | Google Sheet `US SKU Name` → 工作表 `SKUName`（列：通途SKU / 中文名称 / 西班牙语名称） |
| 凭证 | `D:\Work\赛狐\Cursor\secrets\gsheets-service-account.json`（父仓库；worktree 里没有，模块会自动向上查找） |

## 3. 运行

```bash
cd pb_orders
uv run python run_pb_orders.py --dir "D:\Work\美国\Tracy Miller\PB orders\20260921"
uv run python run_pb_orders.py --dir "..." --dry-run          # 只算不写
uv run python run_pb_orders.py --dir "..." --check-shipment   # 用 ASN 核对实发/缺货
uv run python compare_runs.py --dir "..."                    # 与 <dir>/Colab处理 逐项对比
```

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
| `run_pb_orders.py` | CLI 薄适配器：把结构化报告打印回原来的控制台格式，退出码不变 |
| `web/config.py` | 全部配置走环境变量（`PB_ORDERS_*`），本机 fallback 读 `pb_orders/.env` |
| `web/app.py` | 路由：`/`、`/jobs/new`、`/jobs/{id}`、`/jobs/{id}/status`、`/jobs/{id}/retry`、`/artifacts/{id}/download`、`/healthz` |
| `web/repository.py` | SQLite：`jobs` / `artifacts` 两张表 + 状态机 + 中断恢复 |
| `web/storage.py` | 分块上传、SHA-256、内容寻址发布、路径越界防护 |
| `web/tasks.py` | worker 入口；异常翻译成用户可读的失败报告 |
| `web/auth.py` | 钉钉 OIDC 登录：闸门中间件、Redis state、可选白名单、URL 前缀 |
| `web/healthcheck.py` | `python -m web.healthcheck web\|worker` |

### 4.1 状态机与恢复

`uploaded → queued → running → succeeded / failed`（终态不再变）。

Web 与 worker **启动时都会**把遗留的 `queued`/`running` 标成 `failed`
（`worker_interrupted`）：worker 被容器重启杀掉时任务不会自己继续，
留一个永远 running 的僵尸比明确失败更糟。页面因此给出「用相同输入重新处理」。

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

42 个用例，**不需要 Redis**：`tests/conftest.py` 用 reportlab 现画一个结构同构的
3 页 Packslip PDF + 5 行订单 CSV + 3 行名称缓存，跑真实流程；Web 用例把
`web.app.enqueue_job` 换成同步执行，从而覆盖「Web 建任务 + worker 处理 + 页面 + 下载」整链。

## 5. 函数表

| 文件 | 函数 | 作用 |
|------|------|------|
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

## 8. 数量对账口径

- 订单 CSV 原始 `N` 行 → 留 `Record Type == 'D'` → 按 `Qty Ordered` 拆行 → **行数必须等于 PDF 页数**（1:1 硬校验）。
- 无货过滤时：`通途总行 = 可导入 + 无库存`，差必须为 0。
- 拆页时：`PDF 总页数 = 有货页 + 无货页`，差必须为 0；两个子集文件的页**不重不漏**
  （主/无货背贴的 `PO: PO-Line` 集合交集为空、并集等于全量）。
- 输出页数：标签 PDF = 输入页数 × 2；背贴 PDF = 订单行数。

## 9. 本会话成果

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
- [x] 75 个自动化测试（另有 Redis/RQ 生命周期用例，默认跳过），不需要 Redis 也能跑
- [x] 已部署到 EN 测试服务器（`/opt/pb-orders`）。入口 **<https://api.vilavi.cn/pb/>**
      （公网 HTTPS + 钉钉登录，容器只绑 `127.0.0.1`）；Tailscale 那条路径已弃用（走香港中继太慢）
- [x] 公网入口有钉钉登录闸门（`web/auth.py`）。**但白名单留空 = 任何钉钉账号都能登录**
      —— 桥的 corpId 校验实际不生效，见部署文档 11.5 与 `docs/solutions/.../dingtalk-sso-new-api-oidc-bridge.md`
- [x] 保留策略：启动时按 `PB_ORDERS_RETENTION_DAYS`（默认 90 天）清理已完成任务与无人引用的产物。
      **只在服务/worker 启动时跑，不是定时任务**
- [ ] 部分发货的一单跨两份 PDF 时，仍需人工确认哪些页给谁（目前按 SKU 自动拆）
- [ ] 原 notebook 步骤 3.x（赛狐导入）、4.3（按仓库分拆，20260831 起停用）—— 未迁
