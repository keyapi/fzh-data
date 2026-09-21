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
