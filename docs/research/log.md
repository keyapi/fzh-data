---
okf: v0.1
type: Log
title: 调研记录变更日志
description: docs/research 目录变更历史
---

# 变更日志

## 2026-09-20

- **新增**: [2026-09-20-sellfox-official-mcp-feasibility.md](2026-09-20-sellfox-official-mcp-feasibility.md) — **赛狐官方 MCP 可行性**。FAC（ERPNext）接通后，接着问「赛狐能不能也接 MCP」。
  - **结论：有官方托管 MCP，协议层已通，但当前「未启用」→ 现在不能用，等赛狐开通。** 端点 `https://api-mcp.sellfox.com/mcp`，`streamable-http`，协议 `2025-06-18`（与 FAC 同版本），`serverInfo` = `sellfox-api v1.30.0`。
  - **当前状态实测**（决定性）：用官方后台给的 `X-MCP-Key` 调**只读**工具 `get_shop_page_list` → `initialize` 200、`tools/list` 200，但 `tools/call` 返回 **`code 40027「未启用MCP功能，请联系管理员」`**。与赛狐后台「业务设置 → 全局 → MCP管理」显示的「不可用」**一致**。**→ 开通前任何客户端侧改动都不会生效。**
  - **鉴权以官方后台为准：单头 `X-MCP-Key`**（后台 MCP 管理页生成）。CSDN 教程给的是 `X-Sellfox-Client-Id` + `X-Sellfox-Client-Secret` **两个头** —— 与官方不一致（实测两套服务端似乎都认，但接入应以后台给的为准）。**key 是凭证，未写入任何文件。**
  - **⚠️ 一处早先过度结论已在文档内更正**：调研中途曾据 `tools/list` 断言「推翻项目既有约束『赛狐广告无写 API』」。**对照公开 API 文档后该断言不成立** —— 核对本地镜像 `SELLFOX_API/docs/api-reference/`（443 篇，**09-17 刚刷新**）发现广告模块**只有读**：`manageData/*` 全是分页查询（参数为 `运行状态`/`不传默认查询全部`/`pageSize`），唯一含 `create` 的是 `download/createTask.json`（建**报表下载任务**，非改数据）。
    - 所以「赛狐广告无写 API」在 OpenAPI 层面**仍然成立**；真实情况是 **MCP 的 11 个写工具在公开文档里没有对应端点 —— 差异未解释**（可能是私有接口 / 工具已注册但后端未实现 / 文档未覆盖）。**启用前无法验证**（只读都被 40027 挡住）。**不要据此改动既有结论或放开写权限。**
  - **API 文档里的「11 个写工具」矛盾**：`tools/list`（**静态清单，无凭据也返回**）实测 23 个工具，其中 11 个是 SP 广告编辑/创建（`edit_sp_campaign` 自述单次最多 100 条等），**但公开 API 文档没有对应端点**。已在文档中标注为「未解释的差异」，**不当作可用能力**。
  - **写权限处置建议**（按项目既有安全偏好）：若将来启用且确认可写，先建**权限收窄到只读的独立 API 账号**，把限制放在**服务端**而不是 prompt 里；真要写先在单个测试店铺上跑并人工确认。
  - **未决**：① MCP 何时启用（等客服）；② 11 个写工具是真是假（启用后验或直接问客服）；③ IP 白名单对官方托管 MCP 是否生效。
  - 与自有 `sellfox-api-proxy`（VPS `api.vilavi.cn/sellfox`，catch-all 443 端点，**已在用**）**并存不冲突**，文档给了取舍表。

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
