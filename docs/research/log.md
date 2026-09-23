---
okf: v0.1
type: Log
title: 调研记录变更日志
description: docs/research 目录变更历史
---

# 变更日志

## 2026-09-21

- **新增**: [2026-09-21-sellfox-amazon-settlement-reports.md](2026-09-21-sellfox-amazon-settlement-reports.md) — 赛狐 API 拉 Amazon 账期报表的可行性与覆盖度实测。起点是「财务报税要各账号 Amazon 账期报表，现在只能拿 PDF 自己算」。结论：**能拉，但只有「插件获取报告」一条路，且 API 不可触发抓取**。赛狐侧三条路径实测分工：①`亚马逊原报告`（`report/center/add.json`）是**赛狐服务端生成**，报告类型枚举里**没有账期/结算**；②`自定义报表`（`custom/report/*`）是赛狐自建分析表，非 Amazon 结算文件；③`插件获取报告`（`report/center/task/getPlugPageList.json`）**唯一含账期**，靠浏览器插件在账号登录态下抓回存 COS，接口是**纯读**。旁证：`创建报告任务` 的 `reportType` 只支持 `PRODUCT_SALE_REPORT` 一个值 ⇒ 抓取只能在 UI 侧发生。
- **覆盖度实测**：90 家 Amazon 店，**只有 39 店有数据，完全没抓过 51 店**（9 个店群：Centrade-WOWMAX(2)、TOODDLY-Daneey(2)、VERCART(12)、北京固祥-US(4)、北京如森-Rucener(12)、北京如泱-BJRYECLTD(2)、北京熙锦-Jalnoddsa(2)、方州汇绍兴-Xalviortex(3)、百纳-BNCKTRD(12)），另 25 店缺部分月份。**只有 2026-06 / 2026-07 两个月，8/9 月一条都没有**。只有 reportType 3(Transaction) 与 4(Summary) 存在。覆盖呈**整店群**式 ⇒ 人工按品牌逐个执行，非周期性任务。
- **下载约束（关键）**：`fileUrls` 是 **1 小时有效的腾讯 COS 预签名 URL**（含 `q-sign-time`）⇒ **不能存链接**，必须「拿新 URL → 立刻下载落盘」。
- **新增脚本**: `SELLFOX_API/fetch_amazon_settlement.py`（下载归档，实测 **79 文件 / 0 失败 / 34MB**；产出 `_manifest.csv`、`_gaps.csv`、`_failures.csv`；判扩展名按**魔数** `PK\x03\x04`→zip、`%PDF`→pdf）与 `SELLFOX_API/probe_amazon_reports.py`（覆盖度矩阵快查）。
- **内容抽验**：最小 zip(758B, IE/06) 解出 10 行 CSV（仅表头，当月该站点确无交易，**非错误页**）；最大 zip(44KB, US/06) 722 行交易；PDF 用 pypdf 读出 1 页文字含 `Seller fulfilled selling fees` —— 均为真报表。
- **口径结论**：用户明确**只要 Amazon 官方报表、不要赛狐自算口径**（怕不准）⇒ 插件是唯一路径，51 店需运营补抓。曾评估并被否决的替代方案（`monthProfit/shopSummary` 服务端销售额、覆盖全店但属赛狐口径）已留档，以免将来重复提议。
- **新增**: [2026-09-21-sellfox-walmart-settlement-api.md](2026-09-21-sellfox-walmart-settlement-api.md) — 赛狐 Walmart 账期（结算明细）API 实测可行性。起点是「platform-account-reconciliation 的账期数据源一直是财务手工 xlsx，能否走 API」。结论：**能**。`POST /api/financial/walmartReport/queryStatementDetail.json`（公开 OpenAPI，非私有接口），App 权限已开通 `code=0`，**`periodStartDate`/`periodEndDate` 实测 200/200 行非空**；实测窗口 `2026-08-01→09-21`、店铺 `598030 Centrade US` 共 263 行（200+63），窗口内仅 1 个账期 `2026-08-08→2026-09-05`。EN 侧 `platform_code=walmart_api`、`name=WM-{po}`、`sale_account=WM-CtrdUS`，赛狐 `purchaseOrder` == EN `platform_order_id` **匹配 44/44 = 100%**，`partnerItemId` == EN `Item.platform_sku`。
- **纠偏**: 现有设计文档计划扩展的 **Wayfair WFUS 拿不到赛狐数据源** —— `多平台利润报表` 的 `platformTypes` 枚举无 `WAYFAIR`，赛狐无任何 Wayfair 财务端点；Overstock 在赛狐平台枚举里也不存在。即「Walmart 走得通、Wayfair 走不通」，与既有假设相反。
- **实证坑**: ①`data` 只返回 `rows`，**无 `totalSize`/`totalPage`**，必须翻到短页为止；②代理限流除 `code=40019` 外还有 HTTP 层 `{"detail":"Global rate limited. Retry after Xs"}`（无 `code` 字段），`client.py:114 is_rate_limited_response()` 不认这种；③EN 侧 `requests.Session()` 复用会**静默返回空**（44 个 PO 查 0 条，换裸 `requests.get` 立刻 44/44）；④EN 拆单同 OSTKUS：459 条 WM 单 / 442 个唯一 PO，9 个 PO 有 `{po}`+`{po}_1`+`{po}_2` 多条，2 个只有 `_N` 无裸单；⑤`Tongtool Order Item` 直接查列表 403，item 级只能从父单 detail 读。
- **新增脚本**: `SELLFOX_API/probe_walmart_settlement.py`（只读探针，复用 `client.py` + `repo_root.find_main_root()`；`raw_post()` 绕开 `signed_post()` 的异常包装以保留错误码，并处理两种限流形态）。
- **补测：账期勾稽 + 平台费口径结案**。摸清 **Walmart 是双周账期（14 天）**，2026 年 15 段（`08-08→09-05` 异常为 28 天，疑两期合并，待确认）。拉最近 3 个账期（384 行 / 78 单）：**销售额三个账期全部分毫不差**（1317.28 / 1511.75 / 4346.60，差异均 0.00），订单级 73/77 精确一致（4 单为跨期，销售行在更早账期）。**平台费之谜解开**：`赛狐 Commission on Product = (商品价 + Total Walmart Funded Savings) × 15%`，而 `EN platform_fee = 商品价 × 15%` —— 差额恰为「沃尔玛补贴 × 15%」，逐单 64/64 命中、汇总 28.28 vs 28.32。**结论：赛狐对，EN `platform_fee` 漏算了补贴基数**；之前的「15%~17% 费率飘忽」是基数差异造成的假象。已给 OSTKUS 未结案的 `platform_fee` 差额（-25.73/-36.52）留下复查线索。
- **新增脚本**: `platform_account_reconciliation/scripts/reconcile_walmart.py` — Walmart 账期勾稽（跨账期合并 + 口径判定），输出 `账期总览/订单级勾稽/账期费用分类/账期明细` 四个 sheet。`AGENT_HANDOFF.md` 增补 §10 Walmart 章节。
- **顺带修复**: `reconcile_ostkus.py` 的 `ENV_FILE` 原写死仓库根，**在 git worktree 里因凭证只在主仓库而跑不起来**；改为向上搜索 `EN_API/.env`（`_resolve_env_file()`）。全量测试 629 passed。
- **新增**: [2026-09-21-nas-mcp-chatgpt-feasibility.md](2026-09-21-nas-mcp-chatgpt-feasibility.md) — **群晖 NAS 接入 ChatGPT 的可行性与部署位置**。起因：FAC / 赛狐 MCP 之后，问「公司群晖 NAS 能不能也用 MCP 接 ChatGPT，部署在哪」。
  - **结论：能接，但部署在 VPS（`api.vilavi.cn`），不要部署在 NAS 上。** 硬约束是 ChatGPT 由 OpenAI 服务端来连，必须公网可达；而 **NAS 公网只开非标端口 `11024`、标准 443 不通** —— 既接不了 ChatGPT，也不该为接它把 DSM 直接怼上公网。
  - **定论过程（值得记的教训）**：我在**北京办公室内网**初测 `https://nas.vilavi.cn/` 得 **HTTP 200**，但那是个**假阳性** —— 办公室 OpenWrt dnsmasq 把该域名**劫持到内网 `192.168.100.242`**。改用**两处独立外部主机**（上海 VPS + 美国 VPS）复测：`nas.vilavi.cn:443` **两处都失败**、`:11024` **两处都 200**、对照 `api.vilavi.cn:443` **两处都 200**。与仓库既有记载吻合。**教训：在办公网内测自家公网可达性 = 无效，必须换外部视角。**
  - **顺带验证**：那次外部测试同时证明 **上海 VPS 能访问 NAS 的 `11024`** → 方案 A 的链路（VPS → NAS）本来是通的，不需要额外打通。
  - **落地设计（方案 A）**：ChatGPT → `api.vilavi.cn` nginx `/nas/*` → `nas-mcp` 容器（FastMCP）→ `nas.vilavi.cn:11024` DSM FileStation。
    **只复用现有件，不引第三方**：`NAS_API/synology.py`（认证 + `NAS_ROOT_FOLDER` 范围限制）、`sellfox_shipping/mcp_tools.py` 的 FastMCP 骨架、`sellfox-api-proxy`/`new-api` 那套「Docker + nginx 路径块」模式。**明确不推荐**网上那些第三方群晖 MCP（默认权限面覆盖 Docker/备份/Photos，而我们只要一个共享文件夹）。
  - **工具设计**：只读侧先上（`available`/`get_file_list`/`get_thumbnail`/`download_file`/`folder_exists`）；写侧默认不暴露；**`delete_folder` 建议永不暴露**（破坏性）。
  - **安全约束**：① 专用 DSM 账号 + **只读权限**（DSM API **不支持 2FA** → 必须应用专用密码）；② DSM Auto Block 白名单要放行 VPS 出口 IP；③ **证书校验要打开**（`NAS_API` 现用 `cert_verify=False`，那是为局域网设计的，走公网应校验 LE 证书）；④ 范围锁死在 `NAS_ROOT_FOLDER`；⑤ 容器侧设超时与单文件大小上限。
  - **未决（含一条对赛狐复用的共同问题）**：① **ChatGPT 能否用「自定义标头」鉴权** —— 这个结论**赛狐和 NAS 是同一个**，验一次两处受益；② VPS 出口 IP 到底是 `82.156.238.248` 还是 `8.133.254.66`（加 DSM 白名单前须确认）；③ 是否只给局域网 Agent 用（那样方案 C 最省事，不必上任何公网服务）。
- **同日修订（用户反馈后深挖，含两处对本文自身的更正）**：
  - **更正 ①：`sellfox_shipping/mcp_tools.py` 不是「现成的骨架」。** 文件确实在（201 行、2026-07-16 提交），但**从未启用** —— `fastmcp` **不在根 `pyproject.toml`**（只有该模块 Dockerfile 单独装），`main.py:7-17` 用 `try/except ImportError: pass` **静默吞掉**；`AGENT_HANDOFF.md:253` 自述「legacy；根 uv 环境无 fastmcp」。相关测试验证的是**「不装 fastmcp 也能起服务」的 no-op 路径**。→ 只是「可参考形状」，复用它等于从头验证。
  - **更正 ②：「不推荐第三方群晖 MCP」下得太粗。** 深挖后有**明显更贴合**的方案：**`mrquj/mcp-server-synology`** —— `POST /mcp` **Streamable HTTP** + `Authorization: Bearer`，**默认只绑 `127.0.0.1:3020`**（要求前置反代，与本文设计一致），带**路径白名单（含 symlink 逃逸防护）**、只读启发式、**策略下不可能成功的工具直接从清单隐藏**、`/healthz` 可审计。另有 `cmeans`（权限分层 + 2FA，偏本地 stdio）、`lordraw77`（71 工具，面过宽）、`AnythingMCP`（通用网关，自带 OAuth2/RBAC，但对「一个共享文件夹」过重）。
  - **新发现 ③：暴露路径有比公网端口更好的选择。** 上海 VPS 上 tailnet 已存在，**办公室 OpenWrt 路由器在网内**（`100.124.94.69`，VPS 能 ping 通），但**路由器未 advertise 办公网段**，故**到不了 NAS**（`192.168.100.242` ping 失败）。`mrquj` 文档针对「家用路由器后的 NAS」明确建议：**别端口转发 DSM，改用私网 overlay**。→ **把 NAS 拉上 tailnet**（NAS 装 Tailscale）即可让 VPS 走私网调 DSM，**DSM 完全不用公网暴露** —— 比现在的 `:11024` 更干净。
  - **新发现 ④：Tailscale Funnel 已在用**（`https://izuf6cg60rfql8k8qbw87xz.alpines-grouper.ts.net`），当前 `/` → `127.0.0.1:3000`（即 **new-api 已被公网暴露**）。可作为 MCP 的备选前置，但优先用已有 nginx。
  - **IP 查实 ⑤**：`8.133.254.66` = 上海 VPS 的**真实出口 IP**（在该机 `curl ifconfig.me` 实得；网卡只有 `192.168.0.12` + Tailscale `100.119.28.72`）。`82.156.238.248` **不是**这台的出口 —— 它是赛狐白名单里的另一条目（2026-06-25 入仓），**两者关系仍待确认**。→ 给 DSM 加白名单应加 **`8.133.254.66`**。
  - **鉴权疑问已解答（⑥）**：ChatGPT 连接器 **两条路线都支持** —— A. 静态令牌（选「访问令牌/API 密钥」→ 发 `Authorization: Bearer`）；B. OAuth 2.1（PKCE + protected-resource metadata + DCR/CIMD）。但 **MCP 授权规范已把 OAuth 定为强制**（有资料称 2026-03-15 起），静态令牌属**过渡**方案，且**可发布的应用**必须 OAuth。
    **⭐ 关键：我们的 FAC 已用 OAuth 把 ChatGPT 跑通 —— 路线 B 是被验证过的；路线 A 一次没验过。** → 最低成本动作：拿一个支持 Bearer 的最小服务在 ChatGPT 里试一次「访问令牌」连接器，**10 分钟定路线**。这个结论**赛狐与 NAS 共用**。
  - **推进顺序已据此调整**：① 鉴权最小验证 → ② NAS 拉上 tailnet → ③ 实现路线二选一（先在本地跑 `mrquj` 验连通，再决定是否自建）→ ④ 前置反代 → ⑤ 安全约束。
- **同日修订二（用户补充办公室架构后，再改一次 —— 其中一条推翻了上一轮的建议）**：
  - **查实 ①：公网 443 不通的原因是「联通限制」（ISP 层封入向 443），不是配置问题。** 仓库早已记载（`NAS_API/docs/reference/nas-multi-domain-access.md` §网络拓扑：「端口转发 443 → 192.168.1.5:443（LAN 通，**公网不通 — 联通限制**）」）。→ **NAS 永远给不了公网标准 443**，除非走隧道（Cloudflare Tunnel / Tailscale Funnel，不依赖入向端口）。**这条强化了「部署在 VPS」的结论。**
  - **查实 ②：本开发机在 `192.168.10.9`（新华三网段），DNS 指向 `192.168.10.1`，该 DNS 把 `nas.vilavi.cn` 解析成 `192.168.100.242`** → curl 实连 `192.168.100.242:443` 得 200。**证实「假阳性」的机制是内网 DNS 覆盖**（且仓库记着该网段 DNS 也劫持 myds）。另注：本机 ping 不通任何 NAS 地址但 TCP 通（ICMP 被挡）。
  - **⚠️ 推翻上一轮建议 ③：不要用「NAS 装 Tailscale」。** NAS 双网口（`eth0` OpenWrt LAN / `eth1` 光猫 LAN），**默认线路是光猫侧**（用户为「可访问率」选的），但**断电重启有一定概率翻到 LAN1**（近期断电 2 次后仍保持 LAN2）。后果：
    | 路径 | 依赖 NAS 出向默认路由？ | 断电翻转后 |
    |---|---|---|
    | 公网 `:11024`（现状） | ❌ 不依赖（入向转发） | ✅ 不受影响 |
    | NAS 装 Tailscale | ✅ 依赖 | ⚠️ 可能断 |
    | OpenWrt 定向转发 | ❌ 不依赖 | ✅ 不受影响 |
    → **T1（NAS 装 Tailscale）引入的正是当初选 LAN2 想规避的风险**，已从推荐里移除。
  - **新推荐：T3 —— 在 OpenWrt 上做定向转发**（只把 tailnet 侧一个端口 DNAT 到 `192.168.100.242:5001`）：只暴露 DSM 端口、不暴露整个网段、且不依赖 NAS 出向路由。**比 `mrquj` 文档给的泛化建议更贴合你们的双网卡现实。** 若嫌麻烦，**维持 T4（现状公网 `:11024`）其实够用且稳**，用「只读账号 + 只放行 VPS 出口 IP」收敛即可。
  - 另记用户提到的已知副作用：LAN1/LAN2 **翻墙能力不一致**，群晖自动备份 Google Sheet 到 NAS 的功能受默认口影响（用户表示可后议）。
## 2026-09-20

- **新增**: [2026-09-20-sellfox-official-mcp-feasibility.md](2026-09-20-sellfox-official-mcp-feasibility.md) — **赛狐官方 MCP 可行性**。FAC（ERPNext）接通后，接着问「赛狐能不能也接 MCP」。
  - **最终结论：可用，且已用只读链路跑通。** 端点 `https://api-mcp.sellfox.com/mcp`，`streamable-http`，协议 `2025-06-18`（与 FAC 同版本），`serverInfo` = `sellfox-api v1.30.0`。
  - **两条独立鉴权路径（关键，别混）**：
    | 路径 | 头 | 来源 | 实测 |
    |---|---|---|---|
    | A. API 账号 | `X-Sellfox-Client-Id` + `X-Sellfox-Client-Secret` | API 账号 App ID/Secret | ✅ **可用** |
    | B. MCP 管理 | 单头 `X-MCP-Key` | 后台「业务设置 → 全局 → MCP管理」 | ❌ `40027 未启用MCP功能` |
    - 客服答复针对的是 **B**；**A 现在就能用**。CSDN 教程给的正是 A（就实测而言它是对的），官方后台页面给的是 B —— **不矛盾，是两条通道**。
  - **只读链路实测通过**：① 直连 `openapi.sellfox.com` 取 token 得 `{"code":0,"msg":"success"}`（凭证有效 + **北京办公室 IP 白名单已放行**）；② MCP `initialize`/`tools/list` 200；③ 只读工具 `get_shop_page_list` 返回**真实店铺数据**。**数据未写入任何文件；生产 App Secret 未落盘、未写进文档。**
  - **工具清单：23 个 = 13 读 + 1 报表任务 + 9 个 SP 广告写**。13 个读工具已确认可用；`create_ad_download_task` 对应公开文档 `/api/cpc/download/createTask.json`（建**报表下载任务**，不改广告数据）。
  - **⚠️ 9 个 SP 广告写工具：未调用。** `edit_sp_campaign`（自述单次最多 100 条）、`edit_sp_ad_product/group/targeting`、`close_sp_negative_targeting`、`create_sp_{keyword,negative_keyword,product,negative_product}_targeting`。只读了 schema（`required=["shop_id","items"]`，`items` 是 `array<object>` 且 **schema 极薄、无字段级约束**），**未发任何写请求** —— 这些是生产广告写操作，在明确授权与隔离方案前不碰。
  - **与「赛狐广告无写 API」约束的关系（仍未定论）**：该约束在**公开 OpenAPI 层面仍成立**（本地镜像 443 篇、09-17 刷新：广告模块 `manageData/*` 全是分页查询、`hourData/*` 是报表、唯一 `create` 是报表任务）；而这 9 个工具**已能通过 MCP 触达**。**→ 既不能据此断定约束失效，也不能断定工具可用。** 要落地须显式验证。
  - **结论演变（如实保留，避免误信中间版本）**：首版「能接」→ 二版因 `40027` 改「不可用」并撤回一条过度断言 → **三版（本版）换 API 账号凭证实测只读成功，回到「可用」**。二版测出 `40027` 是因为**用错了头**（用了 B 路径），不是功能不可用。
  - **凭证归属的关键取舍**：官方 MCP 要**把生产 App ID/Secret 直接交给客户端**；自有 `sellfox-api-proxy` 则**签发自己的 key**、客户端拿不到赛狐凭证。→ 多人/多 Agent 场景优先走 proxy；官方 MCP 更适合单人自用。
  - **未决**：① 9 个写工具真伪（问客服，或在**明确指定的测试店铺**上用无副作用载荷验证 —— 需用户显式授权）；② B 路径何时开通；③ 限流是否同样适用。
  - **安全建议**（按项目既有偏好）：默认只读，建**权限收窄到只读的独立 API 账号**，把限制放在**服务端**而非 prompt。

## 2026-09-18

- **新增**: [2026-09-18-sellfox-private-api-terminology.md](2026-09-18-sellfox-private-api-terminology.md) — 区分赛狐「公开 OpenAPI」与「私有接口」。调研结论：业界**没有唯一权威说法**，最接近的是 **Shadow API（影子 API）**（Wiz/Invicti/Akto，OWASP API9:2023 Improper Inventory Management），但定义强调「归属方失去管控」——赛狐是**自己在用自己维护**，只是在公开 OpenAPI 之外，**不严格成立**；Tyk 的「UI 就是一个 ergonomics 更差的 API」最贴切本场景。**用词约定**：正文用「私有接口 / 非公开内部接口」，首次出现补「（undocumented internal API，业界亦称 shadow API）」，**避免用「浏览器 API」**（歧义大，易被读成 Playwright 自动化本身）。含 4 条判据、私有接口价值定位（**在「修」不在「批量」**，海外仓备货单改头程是典型唯一路径）、取证纪律（route 截获后 fulfill 假响应 = 零写入）。
- **新增**: [2026-09-18-sellfox-cost-accounting-fifo.md](2026-09-18-sellfox-cost-accounting-fifo.md) — 赛狐成本口径与 FIFO 批次（成本挂在批次上、调整单/出库按先进先出吃批次）。

## 2026-09-07

- **新增**: [2026-09-07-gls-poland-track-feasibility.md](2026-09-07-gls-poland-track-feasibility.md) — GLS（波兰分公司自发货）跟踪可行性。结论：读轨迹**不需开发者账号**——公开无鉴权 REST `gls-group.com/app/service/open/rest/PL/en/rstt029`(摘要) / `rstt028/{no}?postalCode=…`(全量明细) 免登录实测 200(样本 `29626585597`/邮编 21706，history 10 条覆盖建标/收件/交付)；官方 ShipIT/MyGLS 走 GLS 波兰客户(ADE plus/Uni-Portal) + office@gls-poland.com 开通 WebAPI，纯 dev portal 注册替代不了。分支 `feature/gls-track-research`。
- **实证**: 8 月通途样本 GLS-Poland 1265 行 → 去重 1176 单号（11 位 `2…`）；明细唯一钥匙=目的邮编（订单 `邮编` 列已有）。
- **全量验证 + ops 表**: loader 自动拆分一格多号 → 查询单元 1187；`--workers 4` 共享连接池跑整月 3m45s（无限流），ok 1148/err 39(非 GLS 或接口查无)。`gls_track/ops_report.py` 出 FedEx 风格 8-Sheet 异常表。口径：`HANDLING_DAYS=2`、营业日用波兰 2026 假日(非美国联邦)、周末不计、「Amazon是否判迟」仅 Amazon/亚马逊 渠道。输出 `通途非FBA订单202608 GLS运营异常表 20260907.xlsx`（1187 行：正常1073/查无39/承运延误30/在途24/漏发11/迟发9/卡件1）。


- **新增**: [2026-08-18-sps-commerce-api-feasibility.md](2026-08-18-sps-commerce-api-feasibility.md) — SPS Commerce API 自动化可行性（Pottery Barn）。结论：走 Transaction API + M2M client_credentials（无需 Redirect URI），沙盒实测读/写/删全部成功；生产需与 SPS 签约 + 实施团队开通。新增 `sps_api/` POC 模块。
- **关键发现**: Web Service App 不支持 client_credentials（403 unauthorized_client），必须配 Redirect URI；新建 Machine-to-Machine App 即可免交互拿 token。
- **跟进**: 从 `us@mxdeals.com` 读取了 2025-06/07 与 SPS 联系人 Alison Kudrle 的完整邮件线程，并向她发出回复（确认是否仍负责 + 自己对接 API 是否额外收费）。新增 `sps_api/read_sps_mail.py`、`sps_api/docs/reference/tencent-imap.md`（腾讯 IMAP 检索特性）、`sps_api/docs/research/2026-08-18-sps-alison-email-thread.md`。

## 2026-07-24

- **壳 PoC 骨架落地**: 分支 `feature/ai-access-shell-poc` — `ai_access_poc/open_webui/` compose + Tool + Skill；`SELLFOX_API/client.py`。
- **新增**: [2026-07-24-unified-ai-access-poc-plan.md](2026-07-24-unified-ai-access-poc-plan.md) — C′ 双 PoC 实施计划：壳 OWUI + 板 IvyeaOps 赛狐只读映射与验收标准。
- **纠偏补篇**: 独立复审文档 §8 — 撤销「advertise/ 已验证」论据；赛狐广告无写 API；IvyeaOps→赛狐分层成本 15–34 人天（只读）；推荐 Portal 融合 C′（OWUI 壳 + IvyeaOps 板）。
- **新增**: [2026-07-24-unified-ai-access-independent-review.md](2026-07-24-unified-ai-access-independent-review.md) — 对 PR #109 统一 AI 接入调研的独立复审；回答开放问题 8.1–8.5；裁决推荐 Open WebUI 主路径（A′）并强制反证 IvyeaOps 全量改造。
- **新增**: 本 log.md（OKF bundle 补齐）。
