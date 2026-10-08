# pb_orders — PB 订单履约文件本地生成

把 Pottery Barn（PB）经 SPS Commerce 导出的**打包单 + UPS 标签合并 PDF** 和**订单 CSV**，
变成发货要用的三份文件：

1. **通途导入 Excel** —— 拆好数量、砍到 100 列、可直接导入通途
2. **标签 PDF** —— 每页拆成「打包单」和「UPS 标签」两页，并在标签上打上 SKU 与数量
3. **背贴 PDF** —— 4×2 英寸标签，含包裹号、条形码、中文与西班牙语品名

原来这套流程跑在 Google Colab 上，每次要先把 11MB 的 PDF 传上去，网速一慢就传不动。
数据本来就在本地，所以改成一条命令本地出件。

**出件之前还有一步**：SPS 的 New 订单要先按当前断货清单筛一遍，去掉没货的明细行，
才能拿去出件。这一步以前靠人在 Excel 里手工筛，现在也做进本模块了
（见下面「先筛库存，再出件」）。

## 两个步骤，别搞混

```
① 检查 SPS 新订单（筛库存）      ② 出件（生成发货文件）
   SPS 原始订单 CSV                  Packslip PDF + checked CSV
        ↓                                  ↓
   checked0stock CSV                 通途 xlsx + 标签 PDF + 背贴 PDF
   SPS 库存检查操作表 xlsx
```

**已经手工筛过 checked CSV 的**，直接做第 ② 步就行，不必再筛一遍。

## 怎么用（命令行）

### ① 先筛库存（可选）

```bash
cd pb_orders
uv run python run_stock_check.py --dir "D:\Work\美国\Tracy Miller\PB orders\20260917" \
    --no-stock "CENKZ1325-Yellow-97,CENC/LINEN-IVORY-60"
```

会自动挑目录里最新的 `check0stock*.csv`，产出两个文件：

```
checked0stock order x18 20260917_0338_456788.csv      <- 给下一步出件
SPS库存检查操作表-order x18 20260917_0338_456788.xlsx  <- 照着它在 SPS 里勾
```

文件名里的 `x18` 是**筛完剩下**的 PO 数（源导出是 `x21`，砍掉 3 个整单缺货的）。
时间戳沿用源导出的，方便对回是哪一次。

**最关键的一条口径**：判定单位是**明细行**，不是整单。

| 这个 PO 的明细 | 怎么处理 |
|---|---|
| 全部有货 | 正常出 ASN |
| **部分缺货** | **不要整单取消**；checked CSV 保留 Header，只剔掉缺货明细；SPS 里只勾有货的那些行 |
| 全部缺货 | 整单剔除，不出 ASN，发新日期通知 |

网页任务页会把这四类明细**逐行列出来**（部分缺货 PO / ASN 有货明细 / 缺货明细 /
全部缺货 PO），每个表都同时给出**对方 SKU**（`Buyers Catalog or Stock Keeping #`，
用来在 SPS 界面里找行）和**我方 SKU**（`Vendor Style`，内部对照用）——
不用先下 xlsx 才看得见。

### ② 出件

```bash
uv run python run_pb_orders.py --dir "D:\Work\美国\Tracy Miller\PB orders\20260921"
```

跑完会在同一个文件夹里生成三个文件：

```
PB_0_导入_原始_checked0stock order x40 20260921_0159_334423_on_2026-09-21_17-15-01.xlsx
09.21 PotteryBarn label-FZH-DANEEY-Not Prime-第一天.pdf
09.21 PotteryBarn 背贴-中文西班牙语.pdf
```

拿到后：第一个导入通途，后两个发给 WXP。

## 网页版（日常用这个）

命令行适合在自己电脑上跑；**人不在电脑前**（比如休假）或者不想记参数时，用网页版：

1. 浏览器打开服务地址（默认本机 <http://127.0.0.1:8412>）
2. 按下面的入口分两条路走
3. 页面立刻跳到任务页，**处理在后台继续，可以关掉浏览器**
4. 处理完在同一个页面逐个下载产物

| 入口 | 什么时候用 |
|------|-----------|
| 导航**「检查 SPS 新订单」** | 还没筛过。传 SPS 原始订单 CSV（`check0stock*.csv`），拿 checked CSV + 操作表 |
| 导航**「直接生成发货文件」** | 已经手工筛好。直接传 Packslip PDF + checked CSV |

筛完之后**不用再传 checked CSV**：在检查任务页底部点「继续生成发货文件」，
只需再传 Packslip PDF，系统直接复用上一次生成的 checked CSV。

和命令行的区别：

| | 命令行 | 网页版 |
|---|---|---|
| 处理时能不能关电脑 | 不能，进程断了就没了 | 能，任务在服务器上跑 |
| 历史记录 | 没有 | 有，按状态筛选、可重新下载 |
| 重跑同一批 | 再敲一遍命令 | 点「用相同输入重新处理」 |
| 出错的提示 | 控制台文字 | 页面上写清原因和处理建议 |
| 会不会联网 | 默认会（可用 `--cache-only` 关掉） | **永远不联网**，只读本地 SKU 缓存 |
| 谁能用 | 有命令行环境的人 | 本公司钉钉员工（公网实例） |

网页版把每次任务都记进任务库：任务编号、类型（库存预检 / 出件）、操作者、耗时、
代码版本、输入文件（原始文件名）、每个产物的 SHA-256 都能追溯。

**上传的输入也能下载核对**：就在任务页顶部**「输入」那一行**（跟上传同一个位置），
每个输入旁边有「下载」+ SHA-256 —— 想确认「我到底传了什么」「传上去的和本地是不是同一份」时用得上。
页面下方不再另裂一块。（续出件任务里显示的，就是被复用的那份 checked CSV。）

> ✅ **登录范围**：由公司钉钉 OIDC 桥把关 —— 2026-09-23 起桥按**组织成员**判定
> （查本公司通讯录），只有本公司员工能登录，外部钉钉账号会被挡下并看到提示页面。
> 桥改动前这里需要自己填白名单兜底，现在不需要了；`PB_ORDERS_ALLOWED_USERS`
> 留着只作**可选加码**（要再窄一层时才填）。
> 细节见 `AGENT_HANDOFF.md` 与 `docs/reference/server-deployment-architecture.md` 11.5。

### 网页版怎么用（公网实例）

1. 打开 <https://api.vilavi.cn/pb/>
2. 没登录会自动跳到**钉钉登录**，登录后回到你原本想打开的页面
3. 按入口分两条路：
   - **「检查 SPS 新订单」**：传 SPS 原始订单 CSV → 拿 checked CSV + 操作表；
     任务页底部点「继续生成发货文件」→ 只传 Packslip PDF
   - **「直接生成发货文件」**：传 Packslip PDF + 已经筛好的 checked CSV
4. 无货 SKU 已按当前断货情况预填，**可直接改**
   （要改「以后每次的预填值」，点导航里的**「断货 SKU」**去维护那份清单）
5. 提交后页面立刻跳到任务页；**处理在后台跑，可以关浏览器**
6. 处理完左上角状态会自动变成「成功」，下面出现可下载的产物

右上角显示当前登录的钉钉账号，点「退出」注销（会话 8 小时）。

### 首次准备：SKU 名称缓存

网页版**不联网**，背贴的中文/西班牙语品名只读本地缓存。所以部署时要把缓存准备好：

```
pb_orders/data/us_sku_name_cache.csv    # 从 Google Sheet「US SKU Name / SKUName」导出
pb_orders/data/nltk_data/               # nltk 英文词表（可选，缺了会告警并跳过清洗）
```

缓存不存在时，任务会直接失败并提示管理员准备缓存 —— 这是故意的：
宁可不出件，也不能印出没有品名的背贴。

缓存刷新是**独立的管理动作**（需要时临时开海外出口、导出、再关掉），
不是日常出件流程的一部分。

### 已部署的实例

EN 测试服务器上已经跑了一份（**不是** EN 的 App，是并列的独立服务）：

| | |
|---|---|
| 入口 | **<https://api.vilavi.cn/pb/>** —— 需要**钉钉登录** |
| 部署目录 | 服务器 `/opt/pb-orders`，compose 入口 `pb_orders/docker-compose.yml` |
| 运维 | `docker compose ps` / `logs -f pb-orders-worker` / `restart` |

**为什么不用 Tailscale**：实测服务器本机 1-3ms、公网 HTTPS 125ms、
Tailscale 走香港中继要 **20-30 秒**（12MB 的标签 PDF 根本下不完）。
所以走公网 HTTPS + 钉钉登录，不再走 Tailscale，也不再直接暴露 8412 端口
（容器只监听 `127.0.0.1`，公网只能经 NGINX 的 `/pb/`）。

**改无货 SKU 预填**：直接在网页上改 —— 点顶部导航的**「断货 SKU」**，
加新的断货 SKU、删掉已恢复有货的，保存即可。下次新建任务就按这份清单预填，
还能看到上次是谁什么时候改的。**不用改代码，也不用动服务器。**

（服务器 `.env` 里的 `PB_ORDERS_DEFAULT_NO_STOCK=` 只是**初始值**：
页面里改过之后就不再起作用。要回到「页面没设过」的状态，把
`app_settings` 表里 `default_no_stock` 那行删掉即可。）

**要更新代码**：把新的 `pb_orders/` 覆盖上去，然后
`docker compose build --build-arg PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple && docker compose up -d`。
（服务器上直连 PyPI 下载包会超时，**必须**带这个 build-arg；Docker 镜像源已配好 daocloud，基础镜像不用管。）

### 用 Docker 跑（本机 / 新机器）

服务由三个容器组成：`pb-orders-web`（页面）、`pb-orders-worker`（干活的）、
`pb-orders-redis`（队列）。三者是**独立的 Compose 项目**，不碰机器上任何既有服务。

```bash
cd pb_orders
docker compose up -d --build
docker compose ps          # 三个都该是 healthy
```

- 默认只绑本机回环（`127.0.0.1:8412`）。要给别人访问，改 `.env` 里的 `PB_ORDERS_BIND`
  为服务器内网 / Tailscale 地址。
- 运行数据在 `pb_orders/runtime/`（任务库、上传、产物），`pb_orders/data/` 只读挂载。
- 停服务：`docker compose down`（加 `-v` 会连数据一起删，别乱加）。

国内/受限网络构建时：

```bash
docker compose build --build-arg PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple
```

### 开发：不用 Docker 直接跑

需要一个 Redis（本机没有的话，WSL 里 `redis-server --port 6390 --daemonize yes` 也行）：

```bash
cd pb_orders
uv run uvicorn --app-dir . web.app:app --host 127.0.0.1 --port 8412   # 终端 1
uv run python -m web.tasks                                            # 终端 2（worker）
```

配置从 `pb_orders/.env` 读（参考 `.env.example`）。改完代码要**同时重启 web 和 worker**，
worker 是长驻进程，不重启就还在跑旧代码。

## 常用选项

### 库存预检 `run_stock_check.py`

| 想做什么 | 加这个参数 |
|----------|-----------|
| 先看看会剔掉什么，不写文件 | `--dry-run` |
| 指定断货 SKU（必填，否则等于不筛） | `--no-stock "SKU-A,SKU-B"` |
| 显式指定原始 CSV | `--csv "check0stock order x21 ….csv"` |
| 输出到别的文件夹 | `--out "D:\...\out"` |

默认自动挑目录里最新的 `check0stock*.csv`。

### 出件 `run_pb_orders.py`

| 想做什么 | 加这个参数 |
|----------|-----------|
| 先看看会产出什么，不写文件 | `--dry-run` |
| 某些 SKU 没货，主文件只发有货的 | `--no-stock "SKU-A,SKU-B"` |
| 给无货子集文件名加个说明 | `--no-stock-note "4单6个三角灰97"` |
| 核对这批到底发齐没有 | `--check-shipment` |
| 断网/网慢，背贴品名走本地缓存 | `--cache-only` |
| 输出到别的文件夹 | `--out "D:\...\out"` |

正常情况只需要 `--dir` 一个参数：脚本会自动挑当天最新的 Packslip PDF 和订单 CSV。

## 怎么确认「筛出来的等于 SPS 那份」

库存预检的 checked CSV 是**逐行照搬** SPS 原文的（不重新序列化单元格），
所以和 SPS 自己导出的是同一种格式：空列名、参差的列数、行尾都一样。

想自己确认：拿同一份原始 CSV + 同一份断货清单跑一次，和历史那份
`checked0stock ….csv` 比 SHA-256 即可 —— 实测 2026-09-17 批次**字节级完全相同**。

## 怎么确认「本工具的结果 == 原先 Colab 的结果」

不用信口头结论，自己跑一遍就行：

```bash
cd pb_orders
uv run python compare_runs.py --dir "D:\Work\美国\Tracy Miller\PB orders\20260921"
```

它会把当天的三个产物和 `<当天文件夹>\Colab处理\` 里的三个逐项比：

| 比什么 | 比到什么程度 |
|--------|-------------|
| 通途 xlsx | **逐单元格**（形状 / 列名 / 每个值） |
| 背贴 PDF | 页数、字节数、**逐页渲染像素**（150dpi） |
| 标签 PDF | 页数、每页 mediabox/cropbox/rotate、逐页渲染像素，**再额外做一次「把时间戳换成 Colab 那个值重建」的对照** |

时间戳是「生成时刻」，两边必然不同，所以最后那一步是把「差异只来自时间戳」从猜测变成证明
（期望 0 个不同像素）。结论一行，退出码 0 = 一致、1 = 有实质差异。

**建议的稳妥用法**：下一批先两边都生成，跑一次这个脚本；显示 ✓ 之后再用本工具的产物。

## 有货缺货要分开发的时候

用 `--no-stock` 点出没货的 SKU，脚本会把这批**按页拆成两份**（页 = 包裹）：

| 文件 | 内容 |
|------|------|
| 通途 `PB_2_导入_库存有货_…xlsx` | 只有货的行，直接导通途 |
| 通途 `PB_1_不可导入_无库存_…xlsx` | 没货的行，留着对账 |
| 通途 `PB_0_不可导入_原始_…xlsx` | 全量留存 |
| `09.21 PotteryBarn label-…pdf` | **只有货**的包裹标签 |
| `无货4单6件-09.21 PotteryBarn label-…pdf` | 只有无货包裹的标签 |
| `09.21 PotteryBarn 背贴-中文西班牙语.pdf` | **只有货**的背贴 |
| `无货4单6件-09.21 PotteryBarn 背贴-中文西班牙语.pdf` | 只有无货包裹的背贴 |

两个文件的页**不重不漏**：有货页数 + 无货页数 = PDF 总页数，脚本会打印对账。
不给 `--no-stock` 时行为完全不变（全量出件）。

## 跑之前会自动检查什么

- **PDF 页数 = 订单行数**：不相等就**拒绝生成**，因为一页错位整批标签就贴错箱子。
  真遇到不相等，多半是 SPS 导出时 `Qty per Carton` 有不是 1 的。
- **每个 PDF 页都能匹配到 SKU**：匹配不上会中止（避免标签上印空 SKU）。
- **通途列数 ≤ 100**：通途导入的上限，超了会导入失败。
- **数量对账**：`总行数 = 可导入 + 无库存`，差数必须为 0。

## 出错了看哪里

| 现象 | 原因 / 处理 |
|------|------------|
| `找不到 Packslip PDF` | `--dir` 指错文件夹，或用 `--pdf` 显式指定 |
| `目录里没找到 check0stock*.csv` | 先去 SPS 的 New 订单列表导出原始 CSV，再跑库存预检 |
| `缺少必需列：…` | 传的 CSV 不是 SPS 订单导出（或已被 Excel 另存坏） |
| `源 CSV 的行数与解析出的记录数对不上` | 某字段里含换行。请在 SPS 重新导出一次 |
| PDF 页数 != 订单行数 | 看 SPS 导出设置（`Qty per Carton`）；若确实有缺货，需人工把无货订单的页从 PDF 里去掉 |
| 警告「名称表有重复 通途SKU」 | `US SKU Name` 表里有重复行，脚本保留最后一行，可去表里清理 |
| 警告「nltk 英文词表不可用」 | 首次要联网下载一次词表；离线时会跳过中文名里的英文后缀清理 |
| 提示找不到服务账号 JSON | 确认 `D:\Work\赛狐\Cursor\secrets\gsheets-service-account.json` 存在 |
| 网页版任务一直「排队中」 | worker 没起来，或 Redis 不通。`docker compose ps` 看 worker 状态 |
| 网页版任务「worker 在处理中重启」 | 处理到一半 worker 被重启了。点「用相同输入重新处理」即可，不会覆盖原记录 |
| 网页版任务失败「缺少本地 SKU 名称缓存」 | 按上面「首次准备」把缓存放进 `pb_orders/data/` |
| 点「继续生成发货文件」说 checked CSV 不可用 | 那个检查任务没成功、或产物已被保留策略清理。重跑一次库存预检 |

## 不做的事

- **不导入赛狐**（原 notebook 步骤 3.x）——目前不需要
- **不按仓库分拆**（原 4.3）——2026-08-31 起不再区分仓库
- **不自动下载 SPS 文件、不在 SPS 里替人点选**——筛选结果给网页明细表 + 操作表，
  SPS 里的勾选仍由人做
- **不读邮件、不做月度对账**——那是隔壁 `pb_reconciliation/` 的活
