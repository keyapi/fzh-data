---
okf: v0.1
type: Log
title: 调研记录变更日志
description: docs/research 目录变更历史
---

# 变更日志

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
