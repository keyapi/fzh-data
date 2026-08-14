---
okf: v0.1
type: Log
title: 解决方案变更日志
tags: [solutions, log]
---

# 变更日志

## 2026-08-14
<<<<<<< HEAD
- **新增**: `developer-experience/cursor-tongtool-mcp-registration.md` — Cursor 通途 MCP 不会从 clone/Marketplace/安装提示出现；`setup_cursor_mcp.py` 写用户级 mcp.json；同会话 goodsQuery 200。
- **新增**: `workflow-issues/tongtool-sku-rename-gsheet-remap.md` — 通途主档 SKU 改名导致 1.7.0 漏匹配；本地 gspread 凭证 + 订单 Google Sheet 旧名替换 + goodsQuery 校验。
- **新增**: `workflow-issues/index.md`
=======
- **更新**: `conventions/amazon-online-product-pairing-candidate-workflow.md` — 记录四家族试点的真实召回/排序指标、3,557 条分层对账、主动弃权和反馈溯源要求；明确模型未达生产门槛。
>>>>>>> origin/feature/amazon-pairing-ltr

## 2026-08-13
- **新增**: `developer-experience/windows-codex-powershell-utf8.md` — Windows Agent 的 `&&` ParserError、GBK/UTF-8 乱码与 PS 5.1 BOM 对照；`scripts/env_doctor.py` + `windows-agent-shell` skill；本机 PS 5.1 基线 vs pwsh 7.6.4 验证。
- **新增**: `developer-experience/index.md` — developer-experience 分类索引。
- **新增**: `integration-issues/tongtool-erp2-mcp-shared-rate-limit.md` — 记录通途 ERP2 MCP 的本机凭证分层、运行时权限探测、524/525/526 判别，以及双 App 共享五次每分钟限流的实时证据；对应基础文档、Skill、Handoff 与可复跑只读测试脚本已在 `tongtool_api/`。

## 2026-08-11
- **新增**: `conventions/amazon-online-product-pairing-candidate-workflow.md` — 区分 Amazon 在线商品和多平台配对机制，固化别名严格匹配、人工确认、规则/ML 分阶段演进及禁止自动写入的边界。
- **更新**: 三方主线惯例补充 PR #162 后的 1411 行映射快照、HM1510 REST 417 阻断与冻结结论；映射表是库存同步设计输入，不是写入授权。
- **新增**: `conventions/tongtu-en-sellfox-instock-sku-mainline.md` — 通途有库存 SKU 的完整码登记、EN 产品映射、赛狐产品 SKU 验证及半成品边界。
- **背景**: 旧审计把 `-Cover/-Foam` 的基码匹配误作完整登记；本次以 EN 产品 `customer_items` 完整回读修正，固化三系统主线与只读调查边界。

## 2026-08-07
- **新增**: `conventions/erpnext-item-variant-creation-convention.md` — EN 物料/变体创建惯例（四层属性体系、9 类配套物料、API 创建链条、已知坑）
- **新增**: `conventions/index.md` — conventions 分类索引
- **背景**: 通途→EN→赛狐缺口分析中补建缺失物料 `KS0001-CMM-153-PURPLE`，逆向还原物料体系惯例；此前无文档记录此惯例
