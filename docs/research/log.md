---
okf: v0.1
type: Log
title: 调研记录变更日志
description: docs/research 目录变更历史
---

# 变更日志

## 2026-09-21

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
