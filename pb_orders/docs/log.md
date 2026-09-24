---
okf: v0.1
type: Log
title: pb_orders 变更日志
tags: [pb, orders, log]
timestamp: 2026-09-22
---

# 变更日志

## 2026-09-23（第十三轮：库存预检 —— 把「出件前的手工筛选」做进模块）

- **动机**：出件用的 `checked0stock` CSV 不是 SPS 直接给的。每批出件前，要先把当批
  New 订单**全选导出原始 CSV**（`check0stock order x{N} …`），按 `Vendor Style` 对照
  断货清单筛掉缺货明细，再拿它在 SPS 里勾 ASN 明细、给缺货的发新日期通知，
  然后才导出 Packslip PDF。这一步以前全靠人在 Excel 里做。
- **新增** `stock_precheck.py`（步骤 0）+ `run_stock_check.py`（CLI）+ 网页入口。
  上传原始 CSV → `checked0stock …csv` + `SPS库存检查操作表-….xlsx`（7 个 sheet）+ 对账报告。
  硬校验（缺列 / 非 H·D / 明细空值 / 数量非法 / `(PO,Line)` 重复 / Header 不唯一）
  任一不过就**不产出任何产物**。
- **口径按明细行、不按整单**（用户两次纠正后定稿）：部分缺货的 PO **保留 Header、
  只剔缺货明细**，并在操作表里醒目提示「不要整单取消，ASN 只勾有货行」；
  只有全部明细缺货才整组剔除。早期「有一个没货就整单剔」会让 PB 发催单邮件。
- **每个明细表永远并列两个 SKU**（用户明确要求）：对方
  `Buyers Catalog or Stock Keeping #`（在 SPS 里定位明细行）+ 我方 `Vendor Style`
  （内部对照，也是库存匹配的键）。
- **checked CSV 与 SPS 导出的那份字节级一致**：做法是**逐行照搬源文件原文**
  （`_source_lines()`），不重新序列化 —— SPS 的导出是参差的（表头 147 列、
  数据行 146 列、末列无名），经过 pandas 往返会写出字面量 `Unnamed: 146`
  与每行一个尾逗号。实测 2026-09-17 真实批次与历史
  `checked0stock order x19 20260917_0341_630468.csv` **SHA-256 完全相同**
  （`e99a9b78…`，19,363 字节）。行数对不上（字段含换行）时报 `ragged_source` 而不是出个格式不同的文件。
- **网页两入口 + 续出件**：导航「检查 SPS 新订单」与「直接生成发货文件」分开；
  检查任务成功后页面出现「继续生成发货文件」→ **只需再传 Packslip PDF**，
  worker 用 `storage.link_or_copy` 把上次那份 checked CSV 落成新任务的 `order.csv`，
  `source_job_id` 指回检查任务，历史可追溯。
- **数据库**：`jobs` 加 `job_type`（`fulfillment` / `stock_check`），老库启动时
  `ALTER TABLE` 自动补列，已有任务默认 `fulfillment` 不受影响；worker 按类型分发。
- **测试 89 → 132**（新增 43）：预检服务 23、worker 分发 2、仓库迁移 3、Web 15。
  全套通过、2 项跳过（需 Docker 的 Redis/RQ 生命周期用例）。
- **网页版明细表**：任务页直接列出部分缺货 PO / ASN 有货明细 / 缺货明细 / 全部缺货 PO
  四张逐行表（两个 SKU 并列、数量按整数显示），与 xlsx **同一批 DataFrame**；
  超过 300 行截断并在页面上写明。旧任务没有 `tables` 则跳过，不 500。
- **产物名里的 PO 数改为筛完剩下的**：`order x21 …` → `order x18 …`（用户要求），
  源导出的时间戳/流水号保留以便回溯。
- **PR #274 复审修正（Cursor 审出 7 条，全部已修并补回归）**：
  ① 断货 SKU 只按逗号切 → 多行输入被当成一个 SKU、缺货行静默漏掉；两个入口
  改用 `app.parse_sku_list()`（同一个缺陷在出件入口也存在，一起修）；
  ② 回读校验拿**规范化后**的 DataFrame 比逐行照搬的原文 → 源文件里 Record Type
  写成小写 `d` / 字段带空格这类合法输入会误报 `output_verify_failed`；改为比源文件原文；
  ③ 同名产物在 Windows 上 `shutil.move` 直接失败，且先移 CSV 再移 XLSX 会留下
  「新 CSV + 旧 XLSX」；改为先统一探占用（`output_locked`）再 `os.replace` 原子覆盖；
  ④ xlsx 里以 `=` 开头的值会被 openpyxl 写成**公式**（公式注入）；`_excel_safe()` 只给
  xlsx 加 `'` 前缀，checked CSV 保持原始字节；
  ⑤ `report["tables"]` 先把整表转 Python 列表再切片 → 先 `head(limit)`；
  ⑥ 老库升级时 Web 与 worker 会同时 `ALTER TABLE`，输的那个收到 duplicate column name
  → 只放过这一种错误；
  ⑦ 页面写「每个 PO 的 Header 都保留」不准确（整单缺货的 PO 会整组剔除）→ 改成
  「除整单缺货被拿掉的 PO 以外，Header 全部保留」；
  ⑧ **真机上又发现一处**：`open(path,"ab")` 预探**探不出字节区间锁**（Excel 常是这类），
  预探通过后失败发生在 `copy2`，用户看到的是一坨 `PermissionError` 堆栈。改为不做预探，
  在发布函数里捕获 `OSError`、`PermissionError` 翻译成 `output_locked`，并把已发布的**回滚**
  （备份到同卷临时目录 → 全部成功才算数）。用真 `msvcrt.locking` 验过：
  被挡住、两个产物都没动、无残留，解锁后重跑正常覆盖；
  ⑨ 公式转义条件与 openpyxl 源码**逐字对齐**（`len > 1 且以 = 开头`）：实测 `+` / `-` / `@`
  开头 openpyxl 存的是 `t="inlineStr"` 文本单元格（CSV 才需要防那三个），
  顺手加上反而会把 `-1`、`+A1` 这类正常值改坏；
  ⑩ `run_stock_check.py` 模块注释「每个 PO 的 Header 一律保留」不准确，一并改。
- **未做**：尚未部署到 EN 测试服务器。

## 2026-09-23（第十二轮：断货 SKU 列表改为网页上自己维护）
- **动机**：断货清单原先只能改服务器 `.env` + 重启容器，等于每次断货/恢复有货都要
  找人改。使用者要求「有个地方能自己设置」，这次补上。
- **新增**「断货 SKU」设置页（导航进入，`/settings` → POST `/settings/no-stock`）：
  可增删清单、保存后立即影响新建任务的预填，并显示上次修改时间与修改人。
- **存储**：新增 `app_settings` 表（`CREATE TABLE IF NOT EXISTS`，老库自动补表）。
  取值顺序是**页面设过就用页面那份，否则回落到 `.env` 的初始值** —— 所以 `.env`
  降级为「初始值」，README / `.env.example` / AGENT_HANDOFF 都按这个口径改了。
- **解析**：`app.parse_sku_list()` —— 中英文逗号/分号/空格/换行都算分隔，按小写去重
  （保留首次出现的写法），空项丢掉；留空 = 不过滤。
- 顺带修正两处过期陈述：AGENT_HANDOFF §4.1 的「启动时一律把 queued/running 标失败」
  （2026-09-22 起只有 running 会被标失败 + 有队列对账），以及 `app.py` 启动日志里
  「未设白名单 = 任何钉钉用户可登录」（桥 2026-09-23 起按组织成员判定）。
- **测试**：新增 `tests/test_settings.py`（解析规则 7 例 + 页面/保存/清空/CSRF 5 例）
  与 `test_auth.py` 两条「未登录不能看也不能改设置」。全套 89 项通过、2 项跳过
  （另有 Redis/RQ 生命周期用例需本地 Docker，默认跳过）。

## 2026-09-23（第十一轮：桥收口后更正登录措辞 + 把积压改动一起上线）
- **桥已收口，登录措辞更正**：钉钉 OIDC 桥（`new-api-dingtalk-oidc`）2026-09-23 起按
  **组织成员**判定 —— 不在本公司通讯录的人返回 `60121` 直接拒绝。此前桥的 `corpId`
  校验因授权未申请 `corpid` 而**从不生效**，所以「任何钉钉账号都能登录」这句是对的，
  现在不成立了。四处说法一起更正：`README.md`、`AGENT_HANDOFF.md` §10、
  部署文档 11.5/11.6、`docs/solutions/.../dingtalk-oidc-bridge-client-onboarding.md`。
  `PB_ORDERS_ALLOWED_USERS` 从「兜底必需」降级为**可选加码**（留空即信任桥的判定）。
- **上线（本次把积压的改动一起部署）**：此前线上停在第九轮那版（303 修复），
  `a39fcc1`、`#266` 复查修正、`2866ac9` 定期对账都没上。本次一起部署到
  `/opt/pb-orders/pb_orders`（备份 `pb_orders-code.bak-20260923-135501.tar.gz`）。
  - **验证**：未登录访问 `/pb/jobs/new` → 303 + `Set-Cookie: pb_orders_csrf=…`
    （CSRF 中间件确实生效，这是新代码上线的标志）；`/healthz` 正常；
    任务库 2 个成功、**无僵尸任务**；只重建 `pb-orders-web/worker`，
    `new-api` / `sellfox-api-proxy` / 桥 / `nas-mcp` / mysql / redis 全程未动。
  - 部署时代码 `HEAD` 的 `pb_orders` 内容 = `81662db`，故把任务里记录的
    `PB_ORDERS_PIPELINE_VERSION` 从过期的 `pb-web-20260922b` 改为 `pb-web-81662db`
    （该值会写进每条任务记录，属于可追溯性的一部分）。
  - **注意**：解包用 `git archive`（只含跟踪文件），所以服务器上的 `.env`、`runtime/`、
    `data/` 都没被覆盖；`sellfox_shipping/`、`tongtool_order_cost/` 也不在本次包内。

## 2026-09-22（第十轮：重启不再丢队列 / CSRF / 保留清理，及复查修正）
- **重启不再把排队任务当失败**：`queued` 还在 Redis 里、新 worker 会继续跑，
  所以启动时只把仍处于 `running` 的标为中断（条件更新，盖不掉已成功的）。
  同时上传改为固定物理名（`packslip.pdf` / `order.csv`，按槽位校验扩展名）、
  同站 POST 加 CSRF 令牌、已完成任务按 `PB_ORDERS_RETENTION_DAYS`（默认 90 天）清理，
  仍被别的任务引用的产物文件留下。
- **复查修正（代码）**：
  ① `queued` 不再被无条件标失败后，**Redis 丢队列**（`--save 60 1 --appendonly no`，
  快照间隔内重启 / flush）会让任务永远停在「处理中」—— worker 启动时用
  `housekeeping.reconcile_queued` 对账 Redis 侧的 `worker_job_id`，查不到就标失败并允许重跑；
  ② 上传的**原始文件名**不再丢失：磁盘名保持固定，`jobs.input_packslip/input_order`
  重新存用户原始文件名（仅供展示），worker 改为按 `storage` 的固定常量拼路径，
  不再拿数据库字段当路径。
- **复查修正（文档）**：本条这一轮的 4 项改动此前**没进任何文档**，一并补上；
  `AGENT_HANDOFF.md` §7 补坑 17-19、§10 清单更正（测试数、入口 URL、鉴权、保留策略）。
- **共 73 个测试**（新增 2 个：`queued_jobs` 过滤、丢队列对账只动失联任务）。

## 2026-09-23（worker 活着时定期对账）
- Redis 重启：RQ 2.12.0 的 `dequeue_job_and_maintain_ttl` 对 `ConnectionError`
  指数退避重连，**进程不退出**（`TimeoutError, quitting` 那条路径实测没走到）。
  compose 的 `restart: unless-stopped` 因此不会被 Redis 重启触发。
- `FLUSHALL` 同样不断开连接。两种丢失都靠 `start_queue_watch`（默认 60 秒）把库里
  仍 `queued`、Redis 已无 job 的任务标失败。
  新增不依赖 Redis 的对账测试；真 Redis 生命周期用例默认跳过，设 `PB_ORDERS_RQ_DOCKER=1` 才跑。

## 2026-09-22（第九轮：时区修正 + 登录跳转 bug）
- **修复登录后跳错页**（使用者实测发现）：挂在前缀 `/pb/` 下时，`return_to` 记的是
  反代剥掉前缀后的**应用侧路径**（`/`），登录后把浏览器送到 `https://api.vilavi.cn/`
  —— 那是公司的 new-api 大模型路由。现在回写浏览器的 URL 一律补前缀，
  并限制 `return_to` 只能落在 `/pb/` 之下（顺带挡同域跳到隔壁服务）。
- **时区**：容器默认 UTC，页面上「创建/开始/结束」比北京时间少 8 小时，
  标签时间戳与产物文件名里的 `MM.DD` 同理。compose 统一设 `TZ=Asia/Shanghai`；
  已有两条任务记录的 UTC 时间戳一次性纠偏为 `+08:00`。
- **共 65 个测试**（新增一个专测回归本 bug 的用例）。
- **再修一个同类 bug（用户实测发现）**：点「退出」报 `{"detail":"Method Not Allowed"}`。
  `RedirectResponse` 默认 **307 会保留请求方法**，退出是 POST，浏览器就拿 POST 去请求
  只接受 GET 的首页、再被闸门 307 拦到只接受 GET 的登录路由 → 405。
  **退出 / 闸门 / 登录回调统一改 303**；补两条回归用例（断言状态码，不只是 Location）。
  测试数 67。

## 2026-09-22（第八轮：公网 HTTPS + 钉钉登录，修界面问题）
- **诊断出「慢」的真因**：服务器本机 1-3ms、公网 HTTPS 125ms、**Tailscale 20-30 秒**
  （走香港中继 relay "hkg"，`tailscale ping` 超时，TCP 握手就要 12-19 秒）。
  后果是 12MB 标签 PDF 传不完（用户本地留下 `.crdownload`）、表单提交十秒无反馈。
- **改走公网**：`https://api.vilavi.cn/pb/`，前端加钉钉登录；容器只绑 `127.0.0.1`，
  公网 8412 仍拒绝连接。NGINX 只加了一段 `location /pb/`（含
  `client_max_body_size 128m` —— 默认 1m 会 413 掉 11MB 的 PDF），
  改前备份、`nginx -t` 通过才 `systemctl reload`。
- **认证层**：复用公司 OIDC 桥与 `sellfox_shipping.auth_oidc` 的会话签名；
  state 改存 Redis（上游用内存 dict，多 worker 会「Invalid state」）；
  登录后跳回原页面；加可选白名单 `PB_ORDERS_ALLOWED_USERS`。
  **已知风险**：桥的 corpId 校验时灵时不灵，实际上是任何钉钉用户都能登录，
  白名单是补这道口的（当前留空，待确认使用者后填）。
- **修两个界面问题**：①「处理完了左上角还显示处理中」是真 bug ——
  顶部状态标签不在轮询区域内，改为轮询到终态时整页 reload（已用 running→succeeded
  的确定性实验验证）；②提交后加「正在上传，请勿关闭页面」反馈。
- **无货 SKU 做成配置项**：`PB_ORDERS_DEFAULT_NO_STOCK` 预填表单、可随手改，
  改断货情况只需改 .env + `docker compose up -d`。
- **新增 URL 前缀支持**：`PB_ORDERS_URL_PREFIX`，同一份镜像既能挂根路径也能挂 `/pb/`。
- **新增 22 个测试**（共 64 个）：闸门拦截、签名/篡改/过期 cookie、白名单、
  登录回调（state 一次性、return_to）、开放重定向防护、前缀渲染、无货预填。
- **公网验收**：上传 11.2MB 用 0.62 秒；**12MB 标签 PDF 4.7 秒完整下完**（之前下不完）；
  真实批次 50 页 4 秒出件、1:1 通过、对账差全 0；产物与 Colab 等价
  （通途 xlsx 0/5000 单元格差异、标签 PDF 归一化时间戳后 0 像素差异）。
- **既有服务零影响**：6 个既有容器运行时间一字未变、无重启；
  `/`、`/oidc/`、`/sellfox/`、`/nas/mcp` 返回码改动前后完全一致。
- **用户实测发现并已修的 bug**：登录后跳到 `https://api.vilavi.cn/`（域名根路径，
  那是公司的 new-api 大模型路由），而不是 `/pb/`。根因是 `return_to` 记的是
  **反代剥掉前缀后的应用侧路径**（`/`），登录后直接拼成域名根。
  修法：闸门把 `return_to` 补成浏览器可见的完整路径（`/pb/...`），
  `safe_return_to` 同时限制只能回到本前缀之下（顺带挡住跳到同域其它服务）。
  已加回归测试。教训：**前缀化部署下，「应用侧路径」与「浏览器看到的路径」必须分清**。

## 2026-09-22（第七轮：部署到 EN 测试服务器）
- **已部署**：EN 测试服务器（`sh-erpnext-test` / 8.133.254.66）的 `/opt/pb-orders`，
  Compose 项目 `pb-orders`，入口 **`http://100.119.28.72:8412`**（仅 Tailscale）。
  该栈是与 EN 并列的**独立服务**，不是 EN/Frappe Custom App，不接入 bench。
- **构建坑**：服务器上 `pypi.org` 索引可达，但容器内下载包文件（`files.pythonhosted.org`）
  超时；必须 `--build-arg PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple`。
  Docker 守护进程已配 daocloud 镜像源，`python:3.11-slim` 可直接拉取，`redis:7-alpine` 机器上已有。
- **资源限额按实测下调**：真实 50 页批次峰值 RSS ≈ 492MB，而服务器可用内存仅约 1.9Gi，
  故 worker 1g / web 384m / redis 128m（可用环境变量覆盖）。
- **隔离验证**：既有 6 个容器（nas-mcp / new-api 系列 / sellfox-api-proxy）部署前后
  **运行时间一字未变、无重启**；仅新增 `pb-orders-net`；公网 `8.133.254.66:8412` 拒绝连接。
- **远端验收**：脱敏合成样例上传→后台 1.3 秒出件→1:1 通过、对账差全 0、三件产物可下载；
  `docker compose restart` 后三个容器仍 healthy，已成功任务仍可查、下载仍 200。
- **未做**：页面无登录鉴权（只靠 Tailscale 限制）、保留策略无定时清理、未接 NGINX、
  代码版本标记是人工填的 `pb-web-20260922`。

## 2026-09-22（第六轮：Phase 1 网页版 + 隔离 Docker 落地）
- **新增 `service.py`**：把编排从 CLI 抽成结构化服务层（`run_job` / `JobOptions` / `JobResult` /
  `PBJobError`），硬校验失败**不产出任何产物**；`run_pb_orders.py` 退化为薄适配器，
  输出格式与退出码不变。重构后重跑 20260921：通途 xlsx 0/5000 单元格差异、
  背贴 PDF 字节与像素一致、标签 PDF 归一化时间戳后 0 像素差异 —— 与重构前、与 Colab 等价。
- **新增网页版**：FastAPI + Jinja（无 CDN/SPA）+ Redis/RQ worker + SQLite 任务库。
  上传 → 建任务 → 后台处理 → 页面看对账与校验明细 → 逐个下载；关浏览器不影响处理。
- **新增隔离 Docker 栈**：独立 Compose 项目 `pb-orders`、独立网络与 Redis、
  容器名全 `pb-orders-*`、端口默认仅绑回环；不改动任何既有服务。
- **离线原则落地**：worker 强制 `cache_only=True`，缓存缺失直接失败（`cache_missing`），
  绝不在出件路径上访问 Google。
- **修两个真实缺陷**：`--allow-unmatched` 的 NA 穿透（reportlab 画 `nan` 崩溃 +
  背贴 `IntCastingNaNError`）现在补可见占位符与「一页=一件」；无货拆分时
  标签页/背贴页对账总数与分项打架，改为全量口径并按 `total - 各分项` 实算 diff。
- **新增 42 个自动化测试**（合成夹具，不需要 Redis 与客户数据），覆盖服务层、
  存储层、任务库与 Web 全链路。
- **实测**：真实批次（11MB PDF / 50 页）上传后后台 6 秒出件；无货拆分（真实 2 个 SKU）
  得 有货 37 / 无货 13、四条对账差全 0；停 worker 造出中断任务 → 重启 Web 标
  `worker_interrupted` 且可重跑，已成功任务重启后仍可下载；故意用 49 页 PDF 触发 1:1 失败，
  页面只显示可读原因与错误码，0 产物、0 路径泄露。
- **未完成**：本机 Docker Desktop 启动失败（`connect ENOENT \\.\pipe\errorReporter`），
  容器构建与 `docker compose up` 未在本机实测（`docker compose config` 已通过）；
  本地验收改用 WSL 的 Redis + 本机 Python 进程完成。EN 测试服务器尚未部署。

## 2026-09-22（第五轮：EN 测试服务器部署架构调研）
- **新增**: `reference/server-deployment-architecture.md`，对比 Frappe Custom App、同步 FastAPI、FastAPI + Redis/RQ、SPA、Streamlit/Gradio。
- **结论**: 第一阶段采用独立 FastAPI + Jinja/HTMX + Redis/RQ worker；任务、输入、报告和输出持久化，浏览器关闭或 Web 重启不影响已入队任务。
- **离线原则**: 普通 PB 出件只读本地 SKU 名称缓存；Tailscale/OpenWrt 美国出口仅在管理员刷新 Google Sheet 缓存时显式启用，不作为运行依赖。
- **边界**: 暂不做 SPS 自动下载，也不提前建设通用低代码处理平台；第二个同类流程出现后再抽 job/artifact/auth/storage 公共层。
- **依据**: 核查仓库内 `sellfox_shipping` 上传、artifact、OIDC、Docker 模式和 `EN_API/image_upload_app.py`，并对照 FastAPI、Frappe、Tailscale 官方文档；原始 URL 已写入文档。

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
