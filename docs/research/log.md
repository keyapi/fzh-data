---
okf: v0.1
type: Log
title: 调研记录变更日志
description: docs/research 目录变更历史
---

# 变更日志

## 2026-09-21

- **新增**: [2026-09-21-sellfox-walmart-settlement-api.md](2026-09-21-sellfox-walmart-settlement-api.md) — 赛狐 Walmart 账期（结算明细）API 实测可行性。起点是「platform-account-reconciliation 的账期数据源一直是财务手工 xlsx，能否走 API」。结论：**能**。`POST /api/financial/walmartReport/queryStatementDetail.json`（公开 OpenAPI，非私有接口），App 权限已开通 `code=0`，**`periodStartDate`/`periodEndDate` 实测 200/200 行非空**；实测窗口 `2026-08-01→09-21`、店铺 `598030 Centrade US` 共 263 行（200+63），窗口内仅 1 个账期 `2026-08-08→2026-09-05`。EN 侧 `platform_code=walmart_api`、`name=WM-{po}`、`sale_account=WM-CtrdUS`，赛狐 `purchaseOrder` == EN `platform_order_id` **匹配 44/44 = 100%**，`partnerItemId` == EN `Item.platform_sku`。
- **纠偏**: 现有设计文档计划扩展的 **Wayfair WFUS 拿不到赛狐数据源** —— `多平台利润报表` 的 `platformTypes` 枚举无 `WAYFAIR`，赛狐无任何 Wayfair 财务端点；Overstock 在赛狐平台枚举里也不存在。即「Walmart 走得通、Wayfair 走不通」，与既有假设相反。
- **实证坑**: ①`data` 只返回 `rows`，**无 `totalSize`/`totalPage`**，必须翻到短页为止；②代理限流除 `code=40019` 外还有 HTTP 层 `{"detail":"Global rate limited. Retry after Xs"}`（无 `code` 字段），`client.py:114 is_rate_limited_response()` 不认这种；③EN 侧 `requests.Session()` 复用会**静默返回空**（44 个 PO 查 0 条，换裸 `requests.get` 立刻 44/44）；④EN 拆单同 OSTKUS：459 条 WM 单 / 442 个唯一 PO，9 个 PO 有 `{po}`+`{po}_1`+`{po}_2` 多条，2 个只有 `_N` 无裸单；⑤`Tongtool Order Item` 直接查列表 403，item 级只能从父单 detail 读。
- **新增脚本**: `SELLFOX_API/probe_walmart_settlement.py`（只读探针，复用 `client.py` + `repo_root.find_main_root()`；`raw_post()` 绕开 `signed_post()` 的异常包装以保留错误码，并处理两种限流形态）。
- **补测：账期勾稽 + 平台费口径结案**。摸清 **Walmart 是双周账期（14 天）**，2026 年 15 段（`08-08→09-05` 异常为 28 天，疑两期合并，待确认）。拉最近 3 个账期（384 行 / 78 单）：**销售额三个账期全部分毫不差**（1317.28 / 1511.75 / 4346.60，差异均 0.00），订单级 73/77 精确一致（4 单为跨期，销售行在更早账期）。**平台费之谜解开**：`赛狐 Commission on Product = (商品价 + Total Walmart Funded Savings) × 15%`，而 `EN platform_fee = 商品价 × 15%` —— 差额恰为「沃尔玛补贴 × 15%」，逐单 64/64 命中、汇总 28.28 vs 28.32。**结论：赛狐对，EN `platform_fee` 漏算了补贴基数**；之前的「15%~17% 费率飘忽」是基数差异造成的假象。已给 OSTKUS 未结案的 `platform_fee` 差额（-25.73/-36.52）留下复查线索。
- **新增脚本**: `platform_account_reconciliation/scripts/reconcile_walmart.py` — Walmart 账期勾稽（跨账期合并 + 口径判定），输出 `账期总览/订单级勾稽/账期费用分类/账期明细` 四个 sheet。`AGENT_HANDOFF.md` 增补 §10 Walmart 章节。
- **顺带修复**: `reconcile_ostkus.py` 的 `ENV_FILE` 原写死仓库根，**在 git worktree 里因凭证只在主仓库而跑不起来**；改为向上搜索 `EN_API/.env`（`_resolve_env_file()`）。全量测试 629 passed。

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
