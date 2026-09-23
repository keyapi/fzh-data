---
okf: v0.1
type: Index
title: 解决方案
description: 已解决问题的记录索引（由 scripts/check_solutions_health.py --fix 生成，勿手改）
tags: [solutions, index]
---

# 解决方案

> 由 `scripts/check_solutions_health.py --fix` 生成，勿手改。按日期倒序。
> 按类别浏览见各 `docs/solutions/<category>/index.md`。

| 日期 | 标题 | 文件 |
|------|------|------|
| 2026-09-23 | 扫描类脚本防"静默丢数"——反转匹配方向 | [best-practices/scanner-silent-data-loss-guard.md](best-practices/scanner-silent-data-loss-guard.md) |
| 2026-09-23 | grok-bot（美东）SSH 接入 — 对称 NAT 下的跳板选路与 Tailscale SSH 验证绕过 | [integration-issues/grokbot-ssh-via-shanghai-jump-symmetric-nat.md](integration-issues/grokbot-ssh-via-shanghai-jump-symmetric-nat.md) |
| 2026-09-23 | Excel 交付物金额核对——公式单元格与 LibreOffice 重算 | [tooling-decisions/excel-formula-cells-and-recalc-verification.md](tooling-decisions/excel-formula-cells-and-recalc-verification.md) |
| 2026-09-22 | 重定向用 307 会让浏览器重放 POST —— 退出登录报 405 | [integration-issues/redirect-307-replays-post-405.md](integration-issues/redirect-307-replays-post-405.md) |
| 2026-09-22 | 自建服务接入公司钉钉 OIDC 桥（客户端侧做法） | [integration-issues/dingtalk-oidc-bridge-client-onboarding.md](integration-issues/dingtalk-oidc-bridge-client-onboarding.md) |
| 2026-09-22 | 背贴品名缺失怎么补——通途SKU 在 EN 有两种登记写法，且不在 item_languages 里 | [integration-issues/sku-name-backfill-via-en-customer-code.md](integration-issues/sku-name-backfill-via-en-customer-code.md) |
| 2026-09-22 | 用 Drive API 改同事的 Colab notebook（.ipynb）——cell 插入、回读比对、并发守卫 | [developer-experience/colab-notebook-drive-api-editing.md](developer-experience/colab-notebook-drive-api-editing.md) |
| 2026-09-22 | 承运商批量导入面单的字段长度上限——UPS Reference 35 字符、FedEx poNumber 30（多 SKU 合并后必须主动截断） | [integration-issues/carrier-label-batch-field-length-limits.md](integration-issues/carrier-label-batch-field-length-limits.md) |
| 2026-09-22 | 办公室出口拓扑与应急链路（OpenClash ↔ 上海跳板 ↔ 美国 Vultr） | [architecture-patterns/office-egress-fallback-chain.md](architecture-patterns/office-egress-fallback-chain.md) |
| 2026-09-22 | 前缀化反向代理下的登录跳转：`return_to` 必须用浏览器可见路径 | [integration-issues/reverse-proxy-prefix-return-to.md](integration-issues/reverse-proxy-prefix-return-to.md) |
| 2026-09-22 | 公开代码仓与私有公司知识分层——兼顾 Agent 检索、同事使用与防泄露 | [architecture-patterns/public-private-agent-knowledge-split.md](architecture-patterns/public-private-agent-knowledge-split.md) |
| 2026-09-22 | 为什么把「改同事的 Colab notebook」做成独立工具箱 colab_kit（而不是塞进 google_drive_permissions） | [tooling-decisions/colab-kit-notebook-edit-toolbox.md](tooling-decisions/colab-kit-notebook-edit-toolbox.md) |
| 2026-09-22 | notebook 里别用 !shell 做文件操作——文件名含空格会让 !zip 静默失败 | [developer-experience/colab-shell-out-filename-spaces.md](developer-experience/colab-shell-out-filename-spaces.md) |
| 2026-09-22 | gh pr edit 会因 Projects classic 弃用而失败——改 PR 标题/body 要走 gh api PATCH（且管道会掩盖退出码） | [developer-experience/gh-pr-edit-projects-classic-workaround.md](developer-experience/gh-pr-edit-projects-classic-workaround.md) |
| 2026-09-22 | Tailscale 慢到不可用：先查直连（UDP 41641 入站），别急着换方案 | [tooling-decisions/tailscale-relay-vs-public-https-china.md](tooling-decisions/tailscale-relay-vs-public-https-china.md) |
| 2026-09-22 | Tailscale 2026 新能力盘点与对本仓库的适用性（Tailcat / Peer Relays / Services） | [tooling-decisions/tailscale-2026-capabilities.md](tooling-decisions/tailscale-2026-capabilities.md) |
| 2026-09-21 | 把 FAC / 赛狐 / NAS 三个 MCP 接上 ChatGPT —— 一次串起来的方法与四个教训 | [workflow-issues/mcp-to-chatgpt-bringup-lessons.md](workflow-issues/mcp-to-chatgpt-bringup-lessons.md) |
| 2026-09-21 | 中文意图路由（intent_router）—— TypeSafe Jev + 置信度闸门 | [tooling-decisions/typesafe-jev-intent-router.md](tooling-decisions/typesafe-jev-intent-router.md) |
| 2026-09-21 | git worktree 新分支的 upstream 被指成 main —— 裸 push 的隐藏方向 | [developer-experience/git-worktree-branch-upstream-tracks-main.md](developer-experience/git-worktree-branch-upstream-tracks-main.md) |
| 2026-09-21 | ce-okf skill — 把「ce-compound + OKF 收尾」固化成一个命令 | [tooling-decisions/ce-okf-conversation-wrapup-skill.md](tooling-decisions/ce-okf-conversation-wrapup-skill.md) |
| 2026-09-21 | Windows 上 worktree 的 CLAUDE.md：symlink 还是 stub，取决于开发者模式 | [developer-experience/windows-worktree-claude-md-symlink.md](developer-experience/windows-worktree-claude-md-symlink.md) |
| 2026-09-21 | Walmart 账期走赛狐 API 直拉；平台费口径结案（差额=沃尔玛补贴×15%） | [workflow-issues/walmart-account-period-sellfox-api.md](workflow-issues/walmart-account-period-sellfox-api.md) |
| 2026-09-21 | Amazon 账期报表只能走赛狐「插件获取报告」——API 不可触发，且文件地址 1 小时过期 | [integration-issues/sellfox-amazon-settlement-plug-only.md](integration-issues/sellfox-amazon-settlement-plug-only.md) |
| 2026-09-20 | 用库存调整单同步数量会让成本越来越改不动 —— 成因与三个选项 | [workflow-issues/sellfox-inventory-sync-cost-drift.md](workflow-issues/sellfox-inventory-sync-cost-drift.md) |
| 2026-09-20 | 「特殊规则改赛狐入库成本」执行记录 —— 下调成本受批次剩余货值约束，越消耗越改不动 | [workflow-issues/sellfox-incentive-cost-adjust-2026-09.md](workflow-issues/sellfox-incentive-cost-adjust-2026-09.md) |
| 2026-09-18 | 赛狐调整单写链路实测——createV2 一步到位，batchConfirmAdjust 只适用「待调整」态 | [integration-issues/sellfox-adjust-order-write-chain.md](integration-issues/sellfox-adjust-order-write-chain.md) |
| 2026-09-18 | 赛狐海外仓备货单改「单个头程费用」——无 Excel 路径，只能走私有接口 | [integration-issues/sellfox-restock-headfee-api.md](integration-issues/sellfox-restock-headfee-api.md) |
| 2026-09-18 | 赛狐成本补录单——公开 OpenAPI 只读，创建/审核走内部接口（完整契约实测） | [integration-issues/sellfox-cost-adjust-api.md](integration-issues/sellfox-cost-adjust-api.md) |
| 2026-09-16 | 「货物到哪了」查询方法 — 四个数据源的可靠性分级与查询顺序 | [workflow-issues/cargo-location-tracking-source-reliability.md](workflow-issues/cargo-location-tracking-source-reliability.md) |
| 2026-09-16 | PB 断货通知与 0 库存订单处理 — 数据来源、PO 映射与三个反直觉陷阱 | [workflow-issues/pb-out-of-stock-notification-and-zero-stock-orders.md](workflow-issues/pb-out-of-stock-notification-and-zero-stock-orders.md) |
| 2026-09-15 | EN 端到端供应链履约可视化蓝图 — 从销售订单到国外仓上架 | [architecture-patterns/en-end-to-end-supply-chain-fulfillment-visibility.md](architecture-patterns/en-end-to-end-supply-chain-fulfillment-visibility.md) |
| 2026-09-14 | EN 销售订单「已关闭未发货」死单与工单进度不可信 — 子表反查父单的 API 铁律 | [workflow-issues/erpnext-so-closed-unshipped-and-unstarted-work-orders.md](workflow-issues/erpnext-so-closed-unshipped-and-unstarted-work-orders.md) |
| 2026-09-10 | DeepSeek flash 系列 2026-09-10 降价改价 + OpenRouter 迁移评估（结论：不迁） | [tooling-decisions/deepseek-flash-price-cut-2026-09-10-openrouter-evaluation.md](tooling-decisions/deepseek-flash-price-cut-2026-09-10-openrouter-evaluation.md) |
| 2026-09-10 | Amazon 账期按账号对账（NAS + 钉钉 + 赛狐结算组） | [conventions/amazon-period-file-reconcile.md](conventions/amazon-period-file-reconcile.md) |
| 2026-09-09 | 通途统计导出下载识别——按「最上行 = 本次提交」锚定（替代 href 基线差集） | [architecture-patterns/tongtu-orderdetail-export-row-anchor.md](architecture-patterns/tongtu-orderdetail-export-row-anchor.md) |
| 2026-09-09 | 赛狐自动拉取 Amazon 账期（结算中心V2 + 紫鸟插件列式报表）与两报表口径取舍 | [tooling-decisions/amazon-settlement-autofetch-sellfox.md](tooling-decisions/amazon-settlement-autofetch-sellfox.md) |
| 2026-09-09 | 赛狐 Apifox API 文档本地镜像刷新与对账 | [conventions/sellfox-apifox-api-docs-mirror-refresh.md](conventions/sellfox-apifox-api-docs-mirror-refresh.md) |
| 2026-09-09 | 账期/收款核算 生态地图（各平台账期 → 汇率/税/附加费 → 回款归属/回款率 → 归集给财务） | [architecture-patterns/account-period-revenue-reconciliation-ecosystem.md](architecture-patterns/account-period-revenue-reconciliation-ecosystem.md) |
| 2026-09-09 | Amazon&新平台账期「提交异常/迟交」审计方法与规则 | [workflow-issues/amazon-account-period-late-submission-audit.md](workflow-issues/amazon-account-period-late-submission-audit.md) |
| 2026-09-08 | parcel_track 处理天数统一 3 个营业日与 per-carrier 顺序并发 | [conventions/parcel-track-handling-days-sequential-workers.md](conventions/parcel-track-handling-days-sequential-workers.md) |
| 2026-09-08 | new-api/sellfox-proxy 离职自动封号不可靠 —— 双通道检测加固 | [integration-issues/dingtalk-offboarding-hardening.md](integration-issues/dingtalk-offboarding-hardening.md) |
| 2026-09-08 | CLIProxyAPI `auth_unavailable`：升级、浏览器 OAuth 与真实模型验收 | [integration-issues/cliproxyapi-auth-unavailable-oauth-recovery.md](integration-issues/cliproxyapi-auth-unavailable-oauth-recovery.md) |
| 2026-09-07 | 办公室 OpenClash 屏蔽 Adobe 授权校验域名的处理与教训 | [best-practices/adobe-genuine-prompts-office-openclash.md](best-practices/adobe-genuine-prompts-office-openclash.md) |
| 2026-09-07 | GLS 波兰自发货跟踪——公开无鉴权 REST 免账号可行 + 口径坑（日历/脏单元格/返件） | [integration-issues/gls-track-public-rest-calendar.md](integration-issues/gls-track-public-rest-calendar.md) |
| 2026-09-04 | FedEx 官方批量 Track 查询 + 账号/组织恢复路径 | [workflow-issues/fedex-track-batch-query.md](workflow-issues/fedex-track-batch-query.md) |
| 2026-09-03 | WorkBuddy 接公司 new-api 自定义模型：useCustomProtocol 必须 false 且 url 带 /v1 | [developer-experience/workbuddy-custom-model-newapi-config.md](developer-experience/workbuddy-custom-model-newapi-config.md) |
| 2026-09-02 | web-automation-capability-pod-monorepo.md | [architecture-patterns/web-automation-capability-pod-monorepo.md](architecture-patterns/web-automation-capability-pod-monorepo.md) |
| 2026-09-01 | 服务器暴露面审计与安全加固（数据库远程 root、端口瘦身、凭证轮换） | [best-practices/server-exposure-audit-and-hardening.md](best-practices/server-exposure-audit-and-hardening.md) |
| 2026-09-01 | Cursor state.vscdb 膨胀 + Synology Drive 连续备份吃光 C 盘 | [integration-issues/cursor-state-vscdb-synology-cdrive-backup.md](integration-issues/cursor-state-vscdb-synology-cdrive-backup.md) |
| 2026-08-31 | en-item-group-tencent-tmt-translation.md | [tooling-decisions/en-item-group-tencent-tmt-translation.md](tooling-decisions/en-item-group-tencent-tmt-translation.md) |
| 2026-08-31 | DeepSeek 峰谷分时定价：new-api 静态 ModelRatio 的 cron 定时切换方案 | [tooling-decisions/new-api-deepseek-time-based-pricing-automation.md](tooling-decisions/new-api-deepseek-time-based-pricing-automation.md) |
| 2026-08-28 | 群晖 NAS 多域名访问 — OpenWrt ACME、DSM 反代与 QuickConnect 选路 | [integration-issues/nas-multi-domain-access-openwrt-quickconnect.md](integration-issues/nas-multi-domain-access-openwrt-quickconnect.md) |
| 2026-08-25 | Google 表渠道账号同步到 EN Channel Account | [workflow-issues/en-channel-account-gsheet-sync.md](workflow-issues/en-channel-account-gsheet-sync.md) |
| 2026-08-24 | 三角皮壳 PK# 组合代理批量创建（不是 EN 套件） | [workflow-issues/sellfox-cover-combo-create-ops.md](workflow-issues/sellfox-cover-combo-create-ops.md) |
| 2026-08-22 | 逗号组合沙发三模块组合套件批量创建 | [workflow-issues/comma-sofa-combo-batch-staging.md](workflow-issues/comma-sofa-combo-batch-staging.md) |
| 2026-08-22 | 三角有扣套装（三角靠枕 + 50cm 圆枕）组合批量创建 | [workflow-issues/triangle-set-combo-batch-staging.md](workflow-issues/triangle-set-combo-batch-staging.md) |
| 2026-08-21 | 软包墙围 EN 套件 / 赛狐组合商品批量分阶段创建 | [workflow-issues/soft-wall-combo-batch-staging.md](workflow-issues/soft-wall-combo-batch-staging.md) |
| 2026-08-21 | 灵活拼接床头板 EN 套件 / 赛狐组合商品批量创建 | [workflow-issues/flex-headboard-combo-batch-staging.md](workflow-issues/flex-headboard-combo-batch-staging.md) |
| 2026-08-21 | 深卧单人沙发椅双色组合套件批量创建 | [workflow-issues/deep-sofa-combo-batch-staging.md](workflow-issues/deep-sofa-combo-batch-staging.md) |
| 2026-08-21 | 沙发支撑垫存量 EN 套件补齐（客户物料号 + 赛狐组合） | [workflow-issues/support-pad-combo-reconcile.md](workflow-issues/support-pad-combo-reconcile.md) |
| 2026-08-21 | 拉链款 EN 套件 / 赛狐组合商品批量创建（无捆绑SKU 合成客户物料号） | [workflow-issues/zipper-combo-batch-staging.md](workflow-issues/zipper-combo-batch-staging.md) |
| 2026-08-21 | 户外托盘垫套装组合批量创建 | [workflow-issues/outdoor-pad-combo-batch-staging.md](workflow-issues/outdoor-pad-combo-batch-staging.md) |
| 2026-08-21 | 弧形流苏沙发单件整沙发组合创建 | [workflow-issues/fringe-sofa-combo-batch-staging.md](workflow-issues/fringe-sofa-combo-batch-staging.md) |
| 2026-08-21 | 复古造型大体量沙发四模块组合套件创建 | [workflow-issues/retro-sofa-combo-batch-staging.md](workflow-issues/retro-sofa-combo-batch-staging.md) |
| 2026-08-21 | 可组合扶手沙发双子件套件批量创建 | [workflow-issues/combinable-sofa-combo-batch-staging.md](workflow-issues/combinable-sofa-combo-batch-staging.md) |
| 2026-08-20 | 赛狐组合商品/套件 SKU 创建与配对工作流 | [conventions/sellfox-combo-sku-create-pairing-workflow.md](conventions/sellfox-combo-sku-create-pairing-workflow.md) |
| 2026-08-20 | 三角类皮壳在通途与赛狐并行期的共享库存代理 | [conventions/sellfox-cover-shared-inventory-transition.md](conventions/sellfox-cover-shared-inventory-transition.md) |
| 2026-08-20 | EN 成品与皮壳 1:1 配对审计与孤儿皮壳重建 | [conventions/erpnext-product-cover-variant-pairing.md](conventions/erpnext-product-cover-variant-pairing.md) |
| 2026-08-19 | 通途自发货仓库改名后的对账与登记（ERPNext + 财务共享表） | [workflow-issues/tongtu-warehouse-rename-reconciliation.md](workflow-issues/tongtu-warehouse-rename-reconciliation.md) |
| 2026-08-18 | SPS Commerce API 自动化（Pottery Barn）— Transaction API + M2M client_credentials | [architecture-patterns/sps-commerce-api-automation.md](architecture-patterns/sps-commerce-api-automation.md) |
| 2026-08-17 | OSTKUS 账期与 EN Tongtool Order 对账 | [workflow-issues/ostkus-account-reconciliation.md](workflow-issues/ostkus-account-reconciliation.md) |
| 2026-08-14 | 通途主档 SKU 改名后用本地 gspread 对齐订单 Google Sheet | [workflow-issues/tongtool-sku-rename-gsheet-remap.md](workflow-issues/tongtool-sku-rename-gsheet-remap.md) |
| 2026-08-14 | PB 对账表月度更新 — 脚本自动化 + UPS 交付核查 | [workflow-issues/pb-reconciliation-monthly-update.md](workflow-issues/pb-reconciliation-monthly-update.md) |
| 2026-08-14 | Cursor 通途 MCP 不会自动出现，必须写用户级 mcp.json | [developer-experience/cursor-tongtool-mcp-registration.md](developer-experience/cursor-tongtool-mcp-registration.md) |
| 2026-08-13 | Windows Codex/Cursor：PowerShell 5.1 && 与 GBK/UTF-8 对照及 env_doctor | [developer-experience/windows-codex-powershell-utf8.md](developer-experience/windows-codex-powershell-utf8.md) |
| 2026-08-13 | Tongtool ERP2 MCP 接入与双 App 共享限流验证 | [integration-issues/tongtool-erp2-mcp-shared-rate-limit.md](integration-issues/tongtool-erp2-mcp-shared-rate-limit.md) |
| 2026-08-11 | 通途有库存 SKU 三方主线补齐惯例 | [conventions/tongtu-en-sellfox-instock-sku-mainline.md](conventions/tongtu-en-sellfox-instock-sku-mainline.md) |
| 2026-08-11 | Amazon 在线商品配对的分层候选与运营确认流程 | [conventions/amazon-online-product-pairing-candidate-workflow.md](conventions/amazon-online-product-pairing-candidate-workflow.md) |
| 2026-08-07 | EN 物料/变体创建惯例 — 四层属性体系与配套物料 | [conventions/erpnext-item-variant-creation-convention.md](conventions/erpnext-item-variant-creation-convention.md) |
| 2026-08-05 | ChatGPT Edu 账号 CLIProxyAPI 429 限流机制调研 | [integration-issues/chatgpt-edu-cliproxyapi-429-rate-limit.md](integration-issues/chatgpt-edu-cliproxyapi-429-rate-limit.md) |
| 2026-07-28 | 赛狐 Phase2 ingest — IvyeaOps 五杠杆优化器数据接线 | [architecture-patterns/sellfox-ivyeaops-five-lever-ingest.md](architecture-patterns/sellfox-ivyeaops-five-lever-ingest.md) |
| 2026-07-28 | 浏览空表 ≠ 拉取失败 — VERCART 搜索词/定向复验 | [best-practices/sellfox-empty-searchterm-vs-target-report-split.md](best-practices/sellfox-empty-searchterm-vs-target-report-split.md) |
| 2026-07-28 | 搜索词收割勿把 ASIN 当精准关键词 | [best-practices/sellfox-search-term-asin-as-keyword-harvest.md](best-practices/sellfox-search-term-asin-as-keyword-harvest.md) |
| 2026-07-28 | Sellfox 报表 Job 队列（错开 create + 合并轮询） | [architecture-patterns/sellfox-ivyeaops-report-job-queue.md](architecture-patterns/sellfox-ivyeaops-report-job-queue.md) |
| 2026-07-28 | Sellfox 对齐原生按需拉取 — READ_DATASETS 12/12 | [architecture-patterns/sellfox-ivyeaops-ondemand-fetch-parity.md](architecture-patterns/sellfox-ivyeaops-ondemand-fetch-parity.md) |
| 2026-07-28 | SKU 背贴 PDF 生成与通用名称查询模式 | [architecture-patterns/sku-label-pdf-generation-and-name-lookup.md](architecture-patterns/sku-label-pdf-generation-and-name-lookup.md) |
| 2026-07-27 | Windows WSL2 Docker VHDX disk space optimization and migration | [developer-experience/windows-wsl-docker-disk-optimization.md](developer-experience/windows-wsl-docker-disk-optimization.md) |
| 2026-07-27 | IvyeaOps AI 问答 503 — deepseek-chat 无渠道，改用 deepseek-v4-flash | [integration-issues/ivyeaops-assistant-deepseek-v4-model-name.md](integration-issues/ivyeaops-assistant-deepseek-v4-model-name.md) |
| 2026-07-24 | owui-sellfox-xlsx-tool-summary-open-terminal.md | [tooling-decisions/owui-sellfox-xlsx-tool-summary-open-terminal.md](tooling-decisions/owui-sellfox-xlsx-tool-summary-open-terminal.md) |
| 2026-07-24 | FZH 统一 AI 接入方案 — 调研阶段性总结 | [integration-issues/fzh-unified-ai-access-conclusion.md](integration-issues/fzh-unified-ai-access-conclusion.md) |
| 2026-07-23 | Agent-to-DingTalk File Delivery via ERPNext Bridge | [architecture-patterns/agent-dingtalk-file-bridge-via-erpnext.md](architecture-patterns/agent-dingtalk-file-bridge-via-erpnext.md) |
| 2026-07-20 | 赛狐 trackNo 写路径 vs 本地 import vs 通途/自动推送 | [architecture-patterns/sellfox-trackno-write-path-vs-local-import.md](architecture-patterns/sellfox-trackno-write-path-vs-local-import.md) |
| 2026-07-15 | 赛狐尾程打单系统 — 完整调研与架构规划 | [architecture-patterns/sellfox-shipping-research-and-architecture.md](architecture-patterns/sellfox-shipping-research-and-architecture.md) |
| 2026-07-15 | ERPNext Custom App 跨版本 API 兼容性检查 | [workflow-issues/erpnext-version-api-compatibility.md](workflow-issues/erpnext-version-api-compatibility.md) |
| 2026-07-14 | Search First Before Implementing: Always Check Official and Project Documentation Before Making Changes | [workflow-issues/search-first-before-implementing.md](workflow-issues/search-first-before-implementing.md) |
| 2026-07-14 | Codex (ChatGPT Desktop) 更新后 Windows 安装失败与对话历史恢复 | [developer-experience/codex-chatgpt-windows-setup-config-recovery.md](developer-experience/codex-chatgpt-windows-setup-config-recovery.md) |
| 2026-07-10 | ERPNext Work Order Production Data Anomaly Investigation Methodology | [best-practices/erpnext-work-order-investigation-methodology.md](best-practices/erpnext-work-order-investigation-methodology.md) |
| 2026-07-09 | sellfox-api-proxy-design.md | [architecture-patterns/sellfox-api-proxy-design.md](architecture-patterns/sellfox-api-proxy-design.md) |
| 2026-07-03 | 从生产系统复制 Purchase Receipt 工作流 V3 到测试系统 | [workflow-issues/workflow-copy-prod-to-test.md](workflow-issues/workflow-copy-prod-to-test.md) |
| 2026-07-03 | ERPNext 工作流配置完整指南 | [architecture-patterns/erpnext-workflow-configuration.md](architecture-patterns/erpnext-workflow-configuration.md) |
| 2026-07-03 | ERPNext 工作流设计器画布自动布局算法 | [architecture-patterns/workflow-builder-layout-algorithm.md](architecture-patterns/workflow-builder-layout-algorithm.md) |
| 2026-07-03 | ERPNext 工作流操作指南：跨系统管理与设计模式 | [architecture-patterns/erpnext-workflow-operations-guide.md](architecture-patterns/erpnext-workflow-operations-guide.md) |
| 2026-07-03 | AGENTS.md Missing ERPNext Environment Access Distinction | [documentation-gaps/agent-system-access-documentation-gap.md](documentation-gaps/agent-system-access-documentation-gap.md) |
| 2026-06-30 | Verify External API Claims Against Official Documentation Before Committing to Docs | [documentation-gaps/unverified-external-api-claims-in-docs.md](documentation-gaps/unverified-external-api-claims-in-docs.md) |
| 2026-06-30 | GitHub to Gitee Mirror Sync via GitHub Actions | [tooling-decisions/github-gitee-mirror-sync.md](tooling-decisions/github-gitee-mirror-sync.md) |
| 2026-06-26 | 钉钉 SSO 登录 new-api（OIDC Bridge 桥接方案） | [integration-issues/dingtalk-sso-new-api-oidc-bridge.md](integration-issues/dingtalk-sso-new-api-oidc-bridge.md) |
