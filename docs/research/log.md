---
okf: v0.1
type: Log
title: 调研记录变更日志
description: docs/research 目录变更历史
---

# 变更日志

## 2026-09-15

- **新增**: [2026-09-15-shenzhen-office-egress-and-chatgpt-business.md](2026-09-15-shenzhen-office-egress-and-chatgpt-business.md) — 深圳办公室海外出口 + ChatGPT Business。读取并复核 ChatGPT 分享对话（`chatgpt.com/share/6aa8d85e-…`），结合项目实际网络资产调研。
- **关键结论**: ① 封号角度"公司统一出口"**比**"各自翻墙"更危险——"共享代理出口"是 OpenAI 风控首要扣分项且**一人违规全段连坐**（北京 8 人共用出口 IP 正命中）；② ChatGPT 与 Codex **共用同一账号体系**，"Codex 走近端 + 网页版走翻墙"不能隔离风险；③ 因此"深圳放设备"的理由只能是**管控**，不是封号；④ ①官方网页版 + ②不发凭证给员工 + ③不上设备 三者不可兼得。
- **纠正既有文档**: 翻墙主线路在 **2026-08 更换过订阅供应商**（`us_openai_api_proxy/docs/log.md` v0.14）；`.codex_tmp/sellfox-suite-pairing-audit/` 下的 `operations.md` 记载的是**迁移前的旧供应商**，是**历史快照**，勿当现值。供应商名/私有地址/隧道拓扑按模块隐私边界不入库。
- **实证来源**: 2023-04 与 2026-06 两次大规模封号记录、2026 三层风控机制、扣分项清单（含"美国住宅宽带 + 苹果内购仍被封"的被动污染案例）、V2EX 企业版讨论（"正常企业即使被 ban 也可以恢复"）。**诚实空白**：未找到中国公司 Business workspace 被封的公开案例。
- **落点**: 接受现状（深圳各自翻墙）+ 五条纪律（线路固定不跨国跳 / 非 AI 流量不走 AI 出口 / 一人一号 / 美国分公司实体卡一卡一号 / 邮箱避开 Outlook+共享 IP），¥0 当天可做。

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
