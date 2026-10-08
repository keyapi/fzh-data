---
okf: v0.1
type: Research
title: PB 订单处理部署到 EN 测试服务器 — 前端与任务架构选型
tags: [pb, orders, deployment, fastapi, frappe, rq, tailscale, offline]
timestamp: 2026-09-22
---

# PB 订单处理部署到 EN 测试服务器 — 前端与任务架构选型

> **落地状态（2026-09-22）**：第 4 节的推荐架构**已实现并已部署**到 EN 测试服务器 ——
> 作为**独立 Docker 服务**运行，**不是** EN/Frappe Custom App，也不接入 EN bench。
> 入口 **<https://api.vilavi.cn/pb/>**（公网 HTTPS + 钉钉登录；Tailscale 实测走香港中继太慢已弃用）。
> 代码见 `service.py` + `web/`（含 `web/auth.py` 认证层），
> 容器见 `pb_orders/Dockerfile` 与 `pb_orders/docker-compose.yml`，
> 落地实现、隔离验证与部署记录见第 11 节。

## 1. 结论

第一阶段建议把 `pb_orders` 部署为 **EN 测试服务器上的独立 FastAPI 服务**，而不是直接做成 Frappe Custom App：

- 浏览器上传 Packslip PDF 与 SPS 订单 CSV；可填无货 SKU 和备注。
- Web 进程只负责接收文件、建任务、展示状态和下载结果。
- Redis + RQ worker 在独立进程调用现有 `pb_orders` Python 函数。
- 任务、输入、报告、输出均持久化；刷新页面或重启 Web 服务不丢任务。
- 正常出件只读服务器本地的 SKU 名称缓存，**不依赖 Google、Tailscale 或美国出口**。
- Google Sheet 缓存刷新是独立维护动作；需要时才显式启用 OpenWrt 美国出口。
- 先服务 PB；等第二个同类文件处理流程出现后，再抽取通用“文件处理门户”。

不建议第一阶段做 SPS 自动下载。当前无 SPS API，Selenium 又有大量异常分支，继续采用“人工从 SPS 导出 → 网页上传 → 半自动处理”更可靠。

## 2. 已确认的现状与边界

### 2.1 PB 运行特征

- 通常每周一、周四处理，低并发，但单次包含约 11 MB PDF、Excel/PDF 生成和像素/结构校验。
- 用户假期离开时，本地电脑不能作为唯一运行节点。
- 核心处理已拆成可调用的 Python 模块，不需要浏览器自动化。
- 背贴品名已有本地 CSV 缓存；普通任务可以完全离线运行。
- 输入与输出涉及订单、客户和物流信息，应使用私有存储，不应暴露为公开静态文件。

### 2.2 仓库内可复用实现

| 现有实现 | 可复用部分 | 不应照搬的部分 |
|---|---|---|
| `sellfox_shipping/templates/tongtool_upload.html` | 服务端渲染的多文件上传、数量汇总、未匹配原因表 | 请求内同步处理，并提示用户 1–3 分钟不要关闭页面 |
| `sellfox_shipping/app.py` | `UploadFile`、临时文件、`FileResponse`、按 artifact id 下载 | `await file.read()` 会把完整 PDF 放进内存；任务生命周期依附 HTTP 请求 |
| `sellfox_shipping/package_repository.py` | content hash、逻辑产物记录、物理文件去重、私有文件目录 | 不必直接耦合包裹业务表 |
| `sellfox_shipping/auth_oidc.py` | 钉钉 OIDC、签名会话 cookie | state 存内存，只适合单进程；多实例需改 Redis/数据库 |
| `sellfox_shipping/docker-compose.yml` | bind mount 持久化、容器自动重启、反向代理接入 | PB 需要额外 worker 与 Redis |
| `EN_API/image_upload_app.py` | Colab 式多文件上传体验、一次提交多个参数 | 上传和输出全放内存、同步返回、无历史任务和重下载 |

仓库中没有找到可直接核验的 EN/Frappe “Tongtool Cost Review”完整 Custom App 源码，因此对它的比较只采用 Frappe 官方能力和用户描述，不把未知实现细节当成事实。

## 3. 三类方案比较

| 方案 | 优点 | 主要问题 | 结论 |
|---|---|---|---|
| Frappe Custom App | 现成登录、角色、DocType、附件、RQ worker、实时通知、审计 | 与 EN bench 升级/迁移耦合；开发部署更重；文件权限和页面定制更复杂；PB 故障可能影响 EN 测试站 | 能做，但不适合第一阶段 |
| 单页同步 FastAPI | 实现最快；接近 Colab；现有页面可大量复用 | 断网/刷新/重启可能丢结果；CPU/PDF 工作占住 Web worker；无历史任务；大文件易被全量读入内存 | 只适合原型，不适合假期无人值守 |
| FastAPI + Redis/RQ worker | UI 简单；处理与 Web 隔离；任务可重试、可追踪；可持久化产物；独立于 EN bench | 多一个 Redis/worker；要设计任务和产物表 | **推荐 —— 已实现（第 11 节）** |
| React/Vue SPA + API | 交互最自由，适合复杂实时界面 | 对当前两文件上传属于过度建设；前后端构建部署增加维护面 | 暂不采用 |
| Streamlit/Gradio | 快速做内部工具 | 长任务、权限、私有文件、任务历史和精细下载控制不如常规 Web 架构 | 适合演示，不适合正式出件 |

## 4. 推荐架构

```text
浏览器
  │ HTTPS / 登录
  ▼
NGINX
  ▼
FastAPI Web
  ├─ 保存上传文件（流式复制，不调用 await file.read() 读完整 PDF）
  ├─ 建立 job / artifact 记录
  ├─ 投递 RQ job
  ├─ 展示校验、数量对账、失败原因
  └─ 鉴权后 FileResponse 下载
          │
          ▼
       Redis/RQ
          │
          ▼
PB Worker（独立进程）
  ├─ 调用 pb_orders 现有模块
  ├─ 读取本地 SKU 名称缓存
  ├─ 写进度与结构化报告
  └─ 原子移动成品到私有 artifact 目录

持久卷
  ├─ jobs.sqlite（或现有 PostgreSQL）
  ├─ inputs/<job-id>/
  ├─ work/<job-id>/
  ├─ artifacts/<content-hash>/
  └─ cache/us_sku_name_cache.csv
```

### 4.1 为什么不是 FastAPI `BackgroundTasks`

FastAPI 官方把 `BackgroundTasks` 定位为响应后执行的小型同进程任务，并明确指出重计算或需要多进程/多服务器的任务更适合 Celery 等队列。PB 包含 PDF 合并、裁切、渲染和 Excel 处理，且要求服务重启后任务仍可追踪，因此不应绑定 Web 进程。

本项目并发低，任务是本地 Python 函数，RQ 比 Celery 更小、更容易运维；若服务器已有 Frappe Redis/RQ，也仍建议为 PB 使用独立队列名和 worker，避免占用 EN 的 `short/default/long` 队列。

### 4.2 数据模型

最小 `job` 字段：

- `id`
- `status`: `uploaded / queued / running / succeeded / failed`
- `created_by`
- `created_at / started_at / finished_at`
- `no_stock_skus / no_stock_note`
- `progress_step / progress_message`
- `report_json`
- `error_summary`
- `worker_job_id`
- `pipeline_version`（Git commit 或应用版本）

最小 `artifact` 字段：

- `id / job_id`
- `kind`: `input_packslip / input_order / tongtool / label / back_label / no_stock_* / report`
- `original_name / download_name`
- `path`
- `content_hash`
- `size_bytes`
- `mime_type`
- `created_at`

使用 SHA-256 登记输入和输出，可以识别重复上传、证明下载文件未变化，并复用 `sellfox_shipping` 已验证的 content-hash 存储思路。

### 4.3 文件生命周期

1. 上传时把 `UploadFile.file` 分块复制到任务私有目录；限制扩展名和最大大小。
2. 保存成功后计算 hash，再投递任务；不要在数据库事务提交前启动 worker。
3. worker 只在该任务的 `work/` 目录生成临时文件。
4. 全部硬校验通过后，把成品原子移动到 `artifacts/` 并把任务标为成功。
5. 失败时保留输入、结构化报告和错误摘要；不把半成品列为可下载正式产物。
6. 设定保留策略，例如输入和输出保留 90 天；删除动作应有管理员确认和审计。

## 5. 第一阶段页面

不需要 SPA，Jinja/HTMX 即可：

### 5.1 新建任务页

- Packslip PDF：单文件、必填。
- SPS order CSV：单文件、必填。
- 无货 SKU：可选，多行或逗号分隔。
- 无货备注：可选。
- “仅校验”与“正式生成”二选一；默认正式生成前先执行同一套硬校验。
- 提交后立即跳到任务详情页，不让浏览器请求一直等待。

### 5.2 任务详情页

持续轮询或用 SSE/HTMX 刷新：

- 当前步骤和状态。
- 输入文件名、大小、hash。
- PDF 页数、订单拆行数、1:1 校验。
- join 未匹配记录及原因。
- 通途总行、有货、无货、差数。
- 标签/背贴页数。
- 失败时显示可操作的错误，不显示堆栈或服务器路径。
- 成功后逐个下载，也可下载 ZIP 包；ZIP 是附加便利，不替代独立产物记录。

### 5.3 历史任务页

按日期、状态、操作者筛选，支持重新下载和“用相同输入重新处理”。重新处理应创建新任务并记录来源任务，不覆盖历史结果。

## 6. Google 缓存与海外出口

### 6.1 正常运行

PB worker 只读取本地 `us_sku_name_cache.csv`：

- 文件不存在：拒绝正式生成并提示管理员刷新。
- 缓存过旧：页面告警，但是否硬阻断由明确阈值决定；建议先设 30 天告警，不自动联网。
- 报告记录缓存更新时间、hash 和命中/未命中 SKU。

### 6.2 缓存刷新

建议新增独立管理员动作或 CLI（拟定命令）：

```bash
uv run python pb_orders/refresh_sku_name_cache.py
```

刷新流程：

1. 管理员显式开启 EN 服务器的 Tailscale/OpenWrt 美国出口。
2. 测试 Google 连接和服务账号读取。
3. 下载到临时文件并做列验证、行数报告、重复键报告。
4. 校验通过后原子替换正式缓存；失败时保留旧缓存。
5. 记录刷新时间、行数、hash、操作者和结果。
6. 关闭出口或取消该客户端的 exit-node 选择。

Tailscale exit node 会把该客户端的非 Tailscale 流量全部经出口设备转发，所以它应是显式维护窗口，不应成为 PB 容器的永久默认路由。部署拉镜像/依赖也应尽量使用预构建镜像或服务器可达镜像源，不把美国出口当日常依赖。

## 7. Frappe 方案的适用条件与限制

如果后续决定原生集成 EN，可建：

- `PB Processing Job` DocType。
- 两个输入 File 附件。
- 输出 File 子表。
- `frappe.enqueue(..., queue="long")` 或 PB 专用 queue。
- `frappe.publish_realtime` 推进度。
- Role Permission 限制 PB 操作者和管理员。

但应先满足：

1. 确认 EN test bench 的 Frappe 版本、部署方式和 Custom App 发布流程。
2. 确认附件大小、NGINX `client_max_body_size`、请求超时和站点私有文件备份。
3. 为 PB 配独立 worker/queue；Frappe 默认 `short/default` 超时均为 300 秒，`long` 为 1500 秒，不能假设默认队列永远足够。
4. 不在 Web request 内直接运行 PDF 处理。
5. 不让 PB Python 依赖污染现有 EN app 环境。

因此 Frappe 更适合作为第二阶段的统一入口或任务目录，而不是第一阶段直接承载处理引擎。

## 8. 认证和网络暴露

按优先级：

1. 服务仅在 Tailscale/内网可访问，并由 NGINX 限制来源。
2. 若需要普通公网访问，接入仓库已有的钉钉 OIDC 模式。
3. OIDC state 和 session 在单实例可先使用签名 cookie；若横向扩容，state/session 必须移到 Redis/数据库。
4. 下载端点按 job/artifact 权限检查后再用 `FileResponse`，不得直接暴露 artifact 目录。
5. 上传文件名只作为显示信息，物理路径使用服务器生成的 job id 和安全文件名，防止路径穿越。

## 9. 分阶段路线

### Phase 0：部署前准备

- 把 CLI 编排抽成稳定的 `run_job(input, options, output_dir) -> report` 调用接口。
- 固化一套脱敏测试夹具和 Colab 等价性回归。
- 构建包含字体、PyMuPDF、pypdf、reportlab、LibreOffice 非必需依赖的镜像。
- 把 SKU 名称缓存随部署持久卷准备好。

### Phase 1：PB 专用服务（推荐当前实施）

- FastAPI + Jinja/HTMX。
- Redis/RQ 单 worker。
- SQLite job/artifact 元数据；私有 bind mount 存文件。
- 上传、任务详情、历史、下载。
- 可选钉钉 OIDC。
- 手工刷新 Google 缓存。

### Phase 2：运维加固

- 失败重试仅允许对幂等步骤执行。
- 定时备份数据库、缓存与 artifact 元数据。
- 任务超时、磁盘容量和缓存过期告警。
- 一键下载 ZIP、保留策略和管理员清理。
- 根据实际运行时间决定是否增加 worker；同一 PB 批次保持串行。

### Phase 3：第二个流程出现后再抽通用平台

只有当另一个文件处理服务也需要“上传 → 排队 → 报告 → 下载”时，再抽取：

- 通用 job/artifact/auth/storage 层。
- 每个流程以 processor 插件注册输入 schema、参数 schema、执行函数和报告 renderer。
- 前端根据 schema 生成上传字段，但业务校验与报告仍由 processor 定义。

不要现在就做低代码工作流引擎、动态 DAG 或通用表单设计器；PB 一个流程不足以证明这些抽象。

## 10. 验收标准

- 上传完成后可关闭浏览器，任务仍继续。
- Web/worker 容器重启后，已成功任务仍可查询和下载；运行中任务有明确恢复/失败状态。
- 服务器断开海外出口时，普通 PB 出件仍成功。
- 输入不匹配时不生成可误发的正式标签，并完整展示未匹配记录。
- `PDF 总页数 = 有货页 + 无货页`，差数为 0。
- 输出继续通过 `compare_runs.py` 的既有等价性验证。
- 非授权用户不能查看任务或下载订单文件。
- 任务报告能追溯代码版本、缓存版本、输入 hash 和输出 hash。

## 11. 落地实现与实测（2026-09-22）

### 11.1 实现对照

| 本节建议 | 落地位置 |
|---|---|
| CLI 编排抽成稳定调用接口 | `service.py`：`run_job(pdf, csv, options, output_dir, progress) -> JobResult` |
| FastAPI + Jinja/HTMX | `web/app.py` + `web/templates/`（用内联 JS 轮询 `/jobs/{id}/status` 替代 HTMX，少一个前端依赖） |
| Redis/RQ 单 worker，PB 专用队列 | `web/tasks.py`，队列名 `pb-orders`，独立 Redis 实例 |
| SQLite job/artifact 元数据 | `web/repository.py`（`jobs` / `artifacts` 两表 + 状态机） |
| 私有 bind mount 存文件 | `pb_orders/runtime/`（compose 挂到 `/runtime`），产物按内容哈希存放 |
| 流式上传、不 `await file.read()` | `web/storage.save_upload_stream()` 按 1MB 分块落盘并同步算 SHA-256 |
| 鉴权后 `FileResponse` 下载 | `/artifacts/{id}/download` + `resolve_artifact_path` 越界复查 |
| 普通出件只读本地缓存 | worker 强制 `cache_only=True`；缓存缺失即失败（`cache_missing`） |
| 手工刷新 Google 缓存 | 仍是独立动作，未纳入出件路径（`refresh_sku_name_cache.py` 仍未写） |

### 11.2 相对原建议的偏差（都是有意的）

1. **不引入 HTMX**：轮询片段用一个几十行的内联脚本即可，且服务在无外网的内网里也能用。
2. **不引入 ORM**：两张表的状态转换用标准库 `sqlite3` 更小、更好审。
3. **依赖不装整个仓库**：`pb_orders/requirements.txt` 只列 PB 真正 import 到的包，
   避开 lightgbm / scikit-learn / tencentcloud 等与出件无关的重依赖。
4. **不自动重试任务**：PDF/Excel 流程不是逐步事务，隐式重跑可能产出重复产物；
   改为页面「用相同输入重新处理」，由人决定。
5. **保留输入文件**：原建议写「输入与输出保留 90 天」，实现上输入**不随出件删除**，
   否则「重新处理」无源可依；清理交给保留策略。

### 11.3 实测（本机，非容器）

用真实批次 `20260921`（11MB PDF / 50 页 / 50 订单行）验证：

| 项 | 结果 |
|---|---|
| 上传 → 后台处理 | 6 秒完成，浏览器关闭不影响 |
| 数量对账 | 订单行 50 = 50+0；PDF 页 50 = 50+0；差全 0 |
| 与 Colab 产物的等价性 | 通途 xlsx 0/5000 单元格差异；标签 PDF 归一化时间戳后 0 像素差异 |
| 网页产物 vs 命令行产物 | 背贴 PDF 50 页 0 渲染像素差异（字节差异仅来自内嵌时间戳/ID 元数据） |
| 无货拆分 | 有货 37 页 / 无货 13 页，7 个产物分类正确，对账差全 0 |
| Web 重启 | 中断任务标 `worker_interrupted` 且可重跑；已成功任务仍可查询、下载仍 200 |
| 失败路径 | 49 页 PDF 触发 1:1 失败 → 只显示可读原因与错误码，0 产物、0 路径泄露 |
| 自动化测试 | 42 个用例通过（合成夹具，不需要 Redis） |

### 11.4 部署记录：EN 测试服务器（2026-09-22）

| 项 | 值 |
|---|---|
| 主机 | `sh-erpnext-test`（阿里云上海），EN 测试站所在机 |
| 访问入口 | **<https://api.vilavi.cn/pb/>**（公网 HTTPS + 钉钉登录） |
| 部署目录 | `/opt/pb-orders`（`pb_orders/docker-compose.yml` 为 compose 入口） |
| Compose 项目 | `pb-orders`（独立于既有的 `new-api` 项目） |
| 镜像 | `pb-orders:local`，**用清华镜像构建**（见下） |
| 容器 | `pb-orders-web` / `pb-orders-worker` / `pb-orders-redis` 三个，均 healthy |
| 绑定 | Web 绑 **`127.0.0.1:8412`**，公网 8412 拒绝连接，只能经 NGINX 的 `/pb/` |

**为什么放弃 Tailscale 改走公网**（实测，2026-09-22）：

| 访问路径 | 耗时 |
|---|---|
| 服务器本机 | 1-3 ms |
| 公网 HTTPS（`api.vilavi.cn`） | **125-152 ms** |
| Tailscale（`100.119.28.72`） | **20-30 秒** |

`tailscale status` 显示两台机器之间走的是 **relay "hkg"（香港中继）**，
`tailscale ping` 直接超时；TCP 握手本身就要 12-19 秒。
后果不是"有点慢"而是**不可用**：12MB 的标签 PDF 传不完（客户端留下 `.crdownload`），
表单提交后十秒无反馈，任务详情页要等十几秒。

把个人笔记本加进 Tailscale **解决不了**这个问题——瓶颈是中继路径而不是账号，
而且新增的是另一个 tailnet，要共享只能靠节点分享。公网 HTTPS 快约 200 倍，
所以直接走公网，前端加钉钉登录。Tailscale 路径随之弃用（未开 UDP 41641）。

**构建注意**：服务器上 `pypi.org` 的索引可达，但容器内下载包文件
（`files.pythonhosted.org`）会 `ReadTimeoutError`。必须走镜像：

```bash
cd /opt/pb-orders/pb_orders
docker compose build --build-arg PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple
docker compose up -d
```

Docker 守护进程已配好 `docker.m.daocloud.io` 镜像源，`python:3.11-slim` 可直接拉取；
`redis:7-alpine` 服务器上本来就有。

**反向代理**：在 `/etc/nginx/conf.d/new-api.conf`（`api.vilavi.cn` 的 server 块，
本来就同时挂 `/oidc/`、`/sellfox/`、`/nas/mcp`）里加一段：

```nginx
location = /pb { return 301 /pb/; }

location /pb/ {
    proxy_pass http://127.0.0.1:8412/;      # 末尾斜杠剥掉 /pb 前缀
    proxy_http_version 1.1;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
    client_max_body_size 128m;              # ★ nginx 默认只有 1m，会 413 掉 11MB 的 PDF
    proxy_read_timeout 300s;
    proxy_connect_timeout 30s;
}
```

改前备份、`nginx -t` 通过才 `systemctl reload nginx`（reload 不断既有连接）。

**资源限额**（按真实批次实测峰值 492MB 定的，服务器可用内存只有约 1.8Gi）：

| 容器 | 内存上限 | CPU | 依据 |
|---|---|---|---|
| `pb-orders-worker` | `1g` | 1.5 | 50 页真实批次峰值 RSS ≈ 492MB，留一倍余量 |
| `pb-orders-web` | `384m` | 0.5 | 只做上传/展示，不做 PDF 处理 |
| `pb-orders-redis` | `128m` | 0.25 | 单队列、低并发 |

可用 `PB_ORDERS_WORKER_MEM` / `PB_ORDERS_WEB_MEM` / `PB_ORDERS_REDIS_MEM` 覆盖。

**隔离验证**（对应「不能影响现有服务」）：

| 检查 | 结果 |
|---|---|
| 既有 6 个容器 | `nas-mcp` / `new-api-dingtalk-oidc` / `new-api-mysql` / `new-api-redis` / `new-api` / `sellfox-api-proxy` —— 部署与改 NGINX 前后**运行时间一字未变，无重启** |
| 既有端点 | `/`(200)、`/oidc/.well-known/openid-configuration`(200)、`/sellfox/`(404)、`/nas/mcp`(401) —— 改动前后**返回码完全一致** |
| Docker 网络 | 仅新增 `pb-orders-net`，既有网络未改动 |
| 端口 | 新增仅 `127.0.0.1:8412`（容器侧）；公网 8412 **拒绝连接** |
| Redis | 独立容器，不映射宿主端口，未复用 `new-api-redis` |
| 内存占用 | PB 三个容器合计约 190MB；服务器可观测量无明显变化 |
| 服务器内存大头（不是 PB） | 宿主 MariaDB `mariadbd` 1149MB；`frappe-bench` python ×5 ≈1050MB；`new-api-mysql` 容器内 mysqld ≈600MB；Cursor server ≈500MB |
| 勘误 | 早先这里还列过一条「LXD 的 mysqld 590MB」——**是错的**：`lxd` 在那个 `ps` 输出里是**用户名**不是 LXD 产品，该进程父进程为 `containerd-shim`，就是上面那个 `new-api-mysql`，等于重复计了一次。`lxc list` 为空，本机没有 LXD 实例 |

### 11.5 认证接入（钉钉 OIDC）

复用公司既有 OIDC 桥（`new-api-dingtalk-oidc`，`https://api.vilavi.cn/oidc`），
**不改钉钉后台**：桥会透传使用方的 `redirect_uri`。

- 会话签名复用 `sellfox_shipping/auth_oidc.py` 的 `make_session_token` /
  `parse_session_token`（HMAC-SHA256 签名 cookie，无状态、重启不丢，TTL 8h）。
- **state 存 Redis**（`pb-orders-redis`）——上游模块用进程内 dict，
  多 worker / 重启后回调会报 `Invalid state`。
- 闸门写在应用中间件里，**不用 nginx `auth_request`**：桥没有 `/verify` 端点，
  公司里其它服务（sellfox-api-proxy 等）也是这么做的。
- 登录后跳回用户原本想去的页面（`return_to` 只接受本站相对路径，挡开放重定向）。

**登录范围由桥负责（2026-09-23 起）**：桥的授权请求只带 `scope=openid`，钉钉不回
`corpId`，原先「返回了才比」的比对等于从不生效 —— 任何钉钉账号都能登录。
桥已改为按**组织成员**判定（`topapi/user/getbyunionid`，本公司应用凭证）：
不在本公司通讯录的人返回 `60121` → 拒绝，判定不了也拒绝。生产实测真实员工放行、
伪造账号拒绝，并留下日志 `登录校验 union_id=… 显示名=… corp_id=(未返回) 公司成员=True`。

因此 PB 侧**不需要**再自己拦「谁算公司人」。`PB_ORDERS_ALLOWED_USERS`
（逗号分隔，匹配钉钉显示名或 `sub`）保留为**可选加码**，只在需要再窄一层时才填：

- 留空 = 信任桥的判定（默认，也就是按本公司员工放行）
- 填了就只放白名单里的，其余 403

登录后页头会显示钉钉显示名。

### 11.6 未完成事项

- **保留策略在启动时执行**（`PB_ORDERS_RETENTION_DAYS`，默认 90 天），**不是定时任务**：
  长期不重启的服务/worker 不会触发清理。要真正常态化清理得加调度。
- **队列丢失**：RQ 2.12.0 在 Redis 断连时**重连而不退出**（`ConnectionError` 指数退避），
  所以不能指望 worker 被 `restart: unless-stopped` 拉起来再对账。
  `FLUSHALL` 同样不断开连接。worker 启动时对一次账，之后每
  `PB_ORDERS_QUEUE_WATCH_SECONDS` 秒再对（默认 60；设 0 关掉）。
- **未接域名根路径**：目前挂在 `api.vilavi.cn/pb/` 路径前缀下；
  若以后要独立子域名（如 `pb.vilavi.cn`），需要加 DNS 记录与证书。
- **代码版本标记是人工填的** `pb-web-20260922b`；PR 合并后应改为 commit SHA。

## 12. 来源

### 项目内实现

- `sellfox_shipping/templates/tongtool_upload.html`
- `sellfox_shipping/app.py`
- `sellfox_shipping/package_repository.py`
- `sellfox_shipping/auth_oidc.py`
- `sellfox_shipping/docker-compose.yml`
- `sellfox_shipping/Dockerfile`
- `EN_API/image_upload_app.py`

### 官方资料

- FastAPI 文件上传：<https://fastapi.tiangolo.com/tutorial/request-files/>
- FastAPI 后台任务：<https://fastapi.tiangolo.com/tutorial/background-tasks/>
- FastAPI `FileResponse`：<https://fastapi.tiangolo.com/advanced/custom-response/#fileresponse>
- Frappe 基础能力：<https://docs.frappe.io/framework/user/en/basics>
- Frappe 后台任务与队列：<https://docs.frappe.io/framework-copy/user/en/api/background_jobs>
- Frappe 架构：<https://docs.frappe.io/framework-copy/user/en/basics/architecture>
- Frappe Bench 生产部署：<https://docs.frappe.io/framework-copy/user/en/bench/guides/setup-production>
- Tailscale exit nodes：<https://tailscale.com/docs/features/exit-nodes>
- Tailscale exit node 设置：<https://tailscale.com/docs/features/exit-nodes/how-to/setup?tab=linux>
