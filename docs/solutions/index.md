---
okf: v0.1
type: Index
title: 解决方案
description: 已解决问题的记录索引
tags: [solutions, index]
---

# 解决方案

| 日期 | 标题 | 文件 |
|------|------|------|
| 2026-09-16 | PB 断货通知与 0 库存订单处理 — PO/SKU 映射与三个反直觉陷阱 | [workflow-issues/pb-out-of-stock-notification-and-zero-stock-orders.md](workflow-issues/pb-out-of-stock-notification-and-zero-stock-orders.md) |
| 2026-09-16 | 「货物到哪了」查询方法 — 四个数据源的可靠性分级与查询顺序 | [workflow-issues/cargo-location-tracking-source-reliability.md](workflow-issues/cargo-location-tracking-source-reliability.md) |
| 2026-09-21 | 把 FAC / 赛狐 / NAS 三个 MCP 接上 ChatGPT —— 一次串起来的方法与四个教训 | [workflow-issues/mcp-to-chatgpt-bringup-lessons.md](workflow-issues/mcp-to-chatgpt-bringup-lessons.md) |
| 2026-09-22 | 承运商批量导入面单的字段长度上限（UPS Reference 35 / FedEx poNumber 30） | [integration-issues/carrier-label-batch-field-length-limits.md](integration-issues/carrier-label-batch-field-length-limits.md) |
| 2026-09-22 | 背贴品名缺失怎么补——通途SKU 在 EN 有两种登记写法 | [integration-issues/sku-name-backfill-via-en-customer-code.md](integration-issues/sku-name-backfill-via-en-customer-code.md) |
| 2026-09-22 | 用 Drive API 改同事的 Colab notebook（cell 插入 / 回读比对 / 并发守卫） | [developer-experience/colab-notebook-drive-api-editing.md](developer-experience/colab-notebook-drive-api-editing.md) |
| 2026-09-22 | notebook 里别用 `!shell` 做文件操作——文件名含空格会让 `!zip` 静默失败 | [developer-experience/colab-shell-out-filename-spaces.md](developer-experience/colab-shell-out-filename-spaces.md) |
| 2026-09-22 | 把「改同事的 Colab notebook」做成独立工具箱 colab_kit（tooling 决策） | [tooling-decisions/colab-kit-notebook-edit-toolbox.md](tooling-decisions/colab-kit-notebook-edit-toolbox.md) |
| 2026-09-22 | `gh pr edit` 因 Projects classic 弃用而失败——改 PR 要走 `gh api PATCH` | [developer-experience/gh-pr-edit-projects-classic-workaround.md](developer-experience/gh-pr-edit-projects-classic-workaround.md) |
| 2026-09-21 | 把 FAC / 赛狐 / NAS 三个 MCP 接上 ChatGPT —— 一次串起来的方法与四个教训 | [workflow-issues/mcp-to-chatgpt-bringup-lessons.md](workflow-issues/mcp-to-chatgpt-bringup-lessons.md) |
| 2026-09-09 | 账期/收款核算 生态地图（各平台账期 → 汇率/税/附加费 → 回款归属/回款率 → 归集给财务） | [architecture-patterns/account-period-revenue-reconciliation-ecosystem.md](architecture-patterns/account-period-revenue-reconciliation-ecosystem.md) |
| 2026-09-09 | Amazon&新平台账期「提交异常/迟交」审计方法与规则 | [workflow-issues/amazon-account-period-late-submission-audit.md](workflow-issues/amazon-account-period-late-submission-audit.md) |
| 2026-09-09 | 赛狐自动拉取 Amazon 账期（结算中心V2 + 紫鸟插件列式报表）与两报表口径取舍 | [tooling-decisions/amazon-settlement-autofetch-sellfox.md](tooling-decisions/amazon-settlement-autofetch-sellfox.md) |
| 2026-09-14 | EN 销售订单「已关闭未发货」死单与工单进度不可信 — 子表反查父单的 API 铁律 | [workflow-issues/erpnext-so-closed-unshipped-and-unstarted-work-orders.md](workflow-issues/erpnext-so-closed-unshipped-and-unstarted-work-orders.md) |
| 2026-09-10 | Amazon 账期按账号对 NAS/钉钉/赛狐结算组 | [conventions/amazon-period-file-reconcile.md](conventions/amazon-period-file-reconcile.md) |
| 2026-09-20 | 「特殊规则改赛狐入库成本」执行记录 —— 下调受批次剩余货值封顶，越消耗越改不动 | [workflow-issues/sellfox-incentive-cost-adjust-2026-09.md](workflow-issues/sellfox-incentive-cost-adjust-2026-09.md) |
| 2026-09-20 | 用库存调整单同步数量会让成本越来越改不动 —— 成因与三个选项 | [workflow-issues/sellfox-inventory-sync-cost-drift.md](workflow-issues/sellfox-inventory-sync-cost-drift.md) |
| 2026-09-21 | git worktree 新分支的 upstream 被指成 `main` —— 裸 push 的隐藏方向 | [developer-experience/git-worktree-branch-upstream-tracks-main.md](developer-experience/git-worktree-branch-upstream-tracks-main.md) |
| 2026-09-21 | 中文意图路由（intent_router）—— TypeSafe Jev + 置信度闸门 | [tooling-decisions/typesafe-jev-intent-router.md](tooling-decisions/typesafe-jev-intent-router.md) |
| 2026-09-21 | Windows worktree 的 `CLAUDE.md`：symlink 还是 stub，取决于开发者模式 | [developer-experience/windows-worktree-claude-md-symlink.md](developer-experience/windows-worktree-claude-md-symlink.md) |
| 2026-09-21 | ce-okf skill — 把「ce-compound + OKF 收尾」固化成一个命令 | [tooling-decisions/ce-okf-conversation-wrapup-skill.md](tooling-decisions/ce-okf-conversation-wrapup-skill.md) |
| 2026-09-21 | Amazon 账期报表只能走赛狐「插件获取报告」——API 不可触发，文件地址 1 小时过期 | [integration-issues/sellfox-amazon-settlement-plug-only.md](integration-issues/sellfox-amazon-settlement-plug-only.md) |
| 2026-09-21 | Walmart 账期走赛狐 API 直拉；平台费口径结案（差额=沃尔玛补贴×15%） | [workflow-issues/walmart-account-period-sellfox-api.md](workflow-issues/walmart-account-period-sellfox-api.md) |
| 2026-09-18 | 赛狐备货单改「单个头程费用」——无 Excel 路径，只能走私有接口 | [integration-issues/sellfox-restock-headfee-api.md](integration-issues/sellfox-restock-headfee-api.md) |
| 2026-09-18 | 赛狐成本补录单——公开 OpenAPI 只读，创建/审核走内部接口（完整契约实测） | [integration-issues/sellfox-cost-adjust-api.md](integration-issues/sellfox-cost-adjust-api.md) |
| 2026-09-18 | 赛狐调整单写链路——createV2 一步到位，batchConfirmAdjust 只适用「待调整」态 | [integration-issues/sellfox-adjust-order-write-chain.md](integration-issues/sellfox-adjust-order-write-chain.md) |
| 2026-09-10 | DeepSeek flash 降价改价 + OpenRouter 迁移评估（结论：不迁） | [tooling-decisions/deepseek-flash-price-cut-2026-09-10-openrouter-evaluation.md](tooling-decisions/deepseek-flash-price-cut-2026-09-10-openrouter-evaluation.md) |
| 2026-09-08 | CLIProxyAPI `auth_unavailable`：升级、浏览器 OAuth 与真实模型验收 | [integration-issues/cliproxyapi-auth-unavailable-oauth-recovery.md](integration-issues/cliproxyapi-auth-unavailable-oauth-recovery.md) |
| 2026-09-08 | parcel_track 处理天数统一 3 个营业日与 per-carrier 顺序并发 | [conventions/parcel-track-handling-days-sequential-workers.md](conventions/parcel-track-handling-days-sequential-workers.md) |
| 2026-09-08 | new-api/sellfox-proxy 离职自动封号不可靠——双通道检测加固（60121 + identity_map + audit） | [integration-issues/dingtalk-offboarding-hardening.md](integration-issues/dingtalk-offboarding-hardening.md) |
| 2026-09-07 | 办公室 OpenClash 屏蔽 Adobe 授权校验域名 | [best-practices/adobe-genuine-prompts-office-openclash.md](best-practices/adobe-genuine-prompts-office-openclash.md) |
| 2026-09-04 | FedEx 官方批量 Track 查询 + 账号/组织恢复路径 | [workflow-issues/fedex-track-batch-query.md](workflow-issues/fedex-track-batch-query.md) |
| 2026-09-03 | WorkBuddy 接公司 new-api 自定义模型 — useCustomProtocol=false + url 带 /v1 | [developer-experience/workbuddy-custom-model-newapi-config.md](developer-experience/workbuddy-custom-model-newapi-config.md) |
| 2026-09-01 | Cursor state.vscdb 膨胀 + Synology Drive 连续备份吃光 C 盘 | [integration-issues/cursor-state-vscdb-synology-cdrive-backup.md](integration-issues/cursor-state-vscdb-synology-cdrive-backup.md) |
| 2026-09-01 | 服务器暴露面审计与安全加固（数据库远程 root、端口瘦身、凭证轮换） | [best-practices/server-exposure-audit-and-hardening.md](best-practices/server-exposure-audit-and-hardening.md) |
| 2026-08-31 | DeepSeek 峰谷分时定价 — new-api 静态 ModelRatio 的 cron 定时切换 | [tooling-decisions/new-api-deepseek-time-based-pricing-automation.md](tooling-decisions/new-api-deepseek-time-based-pricing-automation.md) |
| 2026-08-28 | 群晖 NAS 多域名访问 — OpenWrt ACME、DSM 反代与 QuickConnect | [integration-issues/nas-multi-domain-access-openwrt-quickconnect.md](integration-issues/nas-multi-domain-access-openwrt-quickconnect.md) |
| 2026-08-25 | Google 表渠道账号同步到 EN Channel Account | [workflow-issues/en-channel-account-gsheet-sync.md](workflow-issues/en-channel-account-gsheet-sync.md) |
| 2026-08-24 | 三角皮壳 PK# 组合代理批量创建（不是 EN 套件） | [workflow-issues/sellfox-cover-combo-create-ops.md](workflow-issues/sellfox-cover-combo-create-ops.md) |
| 2026-08-21 | 软包墙围 EN 套件/赛狐组合商品批量分阶段创建 | [workflow-issues/soft-wall-combo-batch-staging.md](workflow-issues/soft-wall-combo-batch-staging.md) |
| 2026-08-21 | 拉链款无捆绑SKU 合成客户物料号并批量创建组合 | [workflow-issues/zipper-combo-batch-staging.md](workflow-issues/zipper-combo-batch-staging.md) |
| 2026-08-21 | 灵活拼接床头板单变体多数量档批量创建组合 | [workflow-issues/flex-headboard-combo-batch-staging.md](workflow-issues/flex-headboard-combo-batch-staging.md) |
| 2026-08-21 | 沙发支撑垫存量 EN 套件补齐客户物料号与赛狐组合 | [workflow-issues/support-pad-combo-reconcile.md](workflow-issues/support-pad-combo-reconcile.md) |
| 2026-08-21 | 可组合扶手沙发双子件套件批量创建 | [workflow-issues/combinable-sofa-combo-batch-staging.md](workflow-issues/combinable-sofa-combo-batch-staging.md) |
| 2026-08-21 | 深卧单人沙发椅双色组合套件批量创建 | [workflow-issues/deep-sofa-combo-batch-staging.md](workflow-issues/deep-sofa-combo-batch-staging.md) |
| 2026-08-21 | 复古造型大体量沙发四模块组合套件创建 | [workflow-issues/retro-sofa-combo-batch-staging.md](workflow-issues/retro-sofa-combo-batch-staging.md) |
| 2026-08-21 | 户外托盘垫套装组合批量创建 | [workflow-issues/outdoor-pad-combo-batch-staging.md](workflow-issues/outdoor-pad-combo-batch-staging.md) |
| 2026-08-21 | 弧形流苏沙发单件整沙发组合创建 | [workflow-issues/fringe-sofa-combo-batch-staging.md](workflow-issues/fringe-sofa-combo-batch-staging.md) |
| 2026-08-22 | 逗号组合沙发三模块组合套件批量创建 | [workflow-issues/comma-sofa-combo-batch-staging.md](workflow-issues/comma-sofa-combo-batch-staging.md) |
| 2026-08-22 | 三角有扣套装（三角靠枕 + 50cm 圆枕）组合批量创建 | [workflow-issues/triangle-set-combo-batch-staging.md](workflow-issues/triangle-set-combo-batch-staging.md) |
| 2026-08-20 | 三角类皮壳在通途与赛狐并行期的共享库存代理 | [conventions/sellfox-cover-shared-inventory-transition.md](conventions/sellfox-cover-shared-inventory-transition.md) |
| 2026-08-20 | EN 成品与皮壳 1:1 配对审计与孤儿皮壳重建 | [conventions/erpnext-product-cover-variant-pairing.md](conventions/erpnext-product-cover-variant-pairing.md) |
| 2026-08-19 | 通途发货仓库改名后三处对账登记（通途→ERPNext→财务共享表） | [workflow-issues/tongtu-warehouse-rename-reconciliation.md](workflow-issues/tongtu-warehouse-rename-reconciliation.md) |
| 2026-08-17 | OSTKUS 账期与 EN Tongtool Order 对账 | [workflow-issues/ostkus-account-reconciliation.md](workflow-issues/ostkus-account-reconciliation.md) |
| 2026-08-14 | PB 对账表月度更新 — 脚本自动化 + UPS 交付核查 | [workflow-issues/pb-reconciliation-monthly-update.md](workflow-issues/pb-reconciliation-monthly-update.md) |
| 2026-08-14 | Cursor 通途 MCP 不会自动出现，必须写用户级 mcp.json | [developer-experience/cursor-tongtool-mcp-registration.md](developer-experience/cursor-tongtool-mcp-registration.md) |
| 2026-08-14 | 通途主档 SKU 改名后用本地 gspread 对齐订单 Google Sheet | [workflow-issues/tongtool-sku-rename-gsheet-remap.md](workflow-issues/tongtool-sku-rename-gsheet-remap.md) |
| 2026-08-13 | Windows Codex/Cursor：PowerShell 5.1 && 与 GBK/UTF-8 对照及 env_doctor | [developer-experience/windows-codex-powershell-utf8.md](developer-experience/windows-codex-powershell-utf8.md) |
| 2026-08-11 | 通途有库存 SKU 三方主线补齐惯例 | [conventions/tongtu-en-sellfox-instock-sku-mainline.md](conventions/tongtu-en-sellfox-instock-sku-mainline.md) |
| 2026-08-11 | Amazon 在线商品配对的分层候选与运营确认流程 | [conventions/amazon-online-product-pairing-candidate-workflow.md](conventions/amazon-online-product-pairing-candidate-workflow.md) |
| 2026-08-07 | EN 物料/变体创建惯例 — 四层属性体系与配套物料 | [conventions/erpnext-item-variant-creation-convention.md](conventions/erpnext-item-variant-creation-convention.md) |
| 2026-07-28 | 浏览空表 ≠ 拉取失败 — VERCART 搜索词/定向复验 | [best-practices/sellfox-empty-searchterm-vs-target-report-split.md](best-practices/sellfox-empty-searchterm-vs-target-report-split.md) |
| 2026-07-28 | 赛狐报表 Job 队列（错开 create + 合并轮询） | [architecture-patterns/sellfox-ivyeaops-report-job-queue.md](architecture-patterns/sellfox-ivyeaops-report-job-queue.md) |
| 2026-07-28 | SKU 背贴 PDF 生成与通用名称查询模式 | [architecture-patterns/sku-label-pdf-generation-and-name-lookup.md](architecture-patterns/sku-label-pdf-generation-and-name-lookup.md) |
| 2026-07-28 | 赛狐 Phase2 ingest — IvyeaOps 五杠杆优化器数据接线 | [architecture-patterns/sellfox-ivyeaops-five-lever-ingest.md](architecture-patterns/sellfox-ivyeaops-five-lever-ingest.md) |
| 2026-07-27 | IvyeaOps AI 问答 503 — deepseek-v4-flash | [integration-issues/ivyeaops-assistant-deepseek-v4-model-name.md](integration-issues/ivyeaops-assistant-deepseek-v4-model-name.md) |
| 2026-07-24 | FZH 统一 AI 接入方案 — 选型结论 | [integration-issues/fzh-unified-ai-access-conclusion.md](integration-issues/fzh-unified-ai-access-conclusion.md) |
| 2026-07-14 | 先搜再造：官方/项目文档 → 内部约定要搜代码 → 第三方方案要抄功能清单 | [workflow-issues/search-first-before-implementing.md](workflow-issues/search-first-before-implementing.md) |
