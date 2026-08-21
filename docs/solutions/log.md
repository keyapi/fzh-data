---
okf: v0.1
type: Log
title: 解决方案变更日志
tags: [solutions, log]
---

# 变更日志

## 2026-08-21
- **新增**: `workflow-issues/soft-wall-combo-batch-staging.md` — 软包墙围 6 底层物料 × 4 数量 = 24 个 EN 套件/赛狐组合商品批量分阶段创建；登记表去重、`plan --full`、`apply` 三步写入、阶段记录 Excel 续跑。
- **新增**: `SELLFOX_API/soft_wall_stage.py` / `soft_wall_lookup.py` — 软包墙围计划/预览/状态/结果追踪与 EN/赛狐只读快照。
- **更新**: `SELLFOX_API/sellfox_combo_ops.py` 新增 `register-customer-code`；`combo_en.py` 增加客户物料号读写；`repo_root.py` 支持根 `.env` 含 EN 凭证；`combo-ops.md` 命令表/代码地图同步。
- **结果**: 24 个组合全部创建并回读，`sync-combos` `input_en=24 / output_rows=24 / ok=24`；新补齐通途SKU 统一小写 `pcs` 登记客户物料号。
- **新增**: `workflow-issues/zipper-combo-batch-staging.md` — 拉链款 41 行全部“无捆绑SKU”，按 `基码-EN物料码-Npcs` 合成唯一客户物料号，40 个组合全部创建并回读（`sync-combos` `ok=40`）。
- **新增**: `SELLFOX_API/zipper_stage.py` — 拉链款登记表名称自动匹配 EN 底层物料、合成通途SKU、批量 apply 与阶段记录。
- **更新**: `soft_wall_lookup.py` 支持 `--product` 通用快照；`soft_wall_stage.py` 支持 `configure(product)` 复用框架。
- **新增**: `workflow-issues/flex-headboard-combo-batch-staging.md` + `SELLFOX_API/flex_headboard_stage.py` — 灵活拼接床头板单变体 4 个数量档全部创建并回读（`sync-combos` `ok=4`）。
- **新增**: `workflow-issues/support-pad-combo-reconcile.md` + `SELLFOX_API/support_pad_stage.py` — 沙发支撑垫存量 EN 套件补齐客户物料号与缺失赛狐组合（`sync-combos` `ok=3`）。
- **新增**: `workflow-issues/combinable-sofa-combo-batch-staging.md` + `SELLFOX_API/combinable_sofa_stage.py` — 可组合扶手沙发双子件组合按 `基码x数量_基码x数量` 合成通途SKU，4 个组合全部创建并回读（`sync-combos` `ok=4`）。
- **新增**: `workflow-issues/deep-sofa-combo-batch-staging.md` + `SELLFOX_API/deep_sofa_stage.py` — 深卧单人沙发椅双色组合 3 个全部创建并回读（`sync-combos` `ok=3`）；`client.py` 增加代理嵌套 detail 限流识别与单测。
- **更新**: `workflow-issues/index.md`、`docs/solutions/index.md`、`CONCEPTS.md`

## 2026-08-19
- **新增**: `workflow-issues/tongtu-warehouse-rename-reconciliation.md` — 通途自发货仓库改名（美东-/美中-/波兰- 前缀）后的三处对账登记：通途清单 → 生产 ERPNext `Tongtu Shipping Warehouse`（新建照抄分公司成本列）→ 财务共享表「订单发货仓库对应成本来源」（参考旧名行、美东/波兰退货仓按主仓口径推断并确认）。含凭证在父仓库/worktree、uv、控制台编码、dry-run 等经验教训。
- **新增**: `.agents/skills/tongtool-warehouse-sync/SKILL.md` — 仓库改名/登记触发词 skill，handoff 指向上述文档。
- **更新**: `workflow-issues/index.md`、`docs/solutions/index.md`、`CONCEPTS.md`

## 2026-08-17
- **新增**: `workflow-issues/ostkus-account-reconciliation.md` — OSTKUS 账期与 EN Tongtool Order 对账；覆盖拆单后缀、OSFD- 前缀、重复主单、金额字段口径、跨期退单。
- **新增**: `workflow-issues/index.md` 更新

## 2026-08-14
- **新增**: `workflow-issues/pb-reconciliation-monthly-update.md` — PB 对账表月度更新脚本化（追加付款/补录发票/截止判定/双开票映射/不重不漏校验/颜色标记）+ UPS 交付核查判断迟发 vs PB 漏结算；openpyxl 全量重算、显式填色、CSV 数值转换陷阱。
- **更新**: `conventions/amazon-online-product-pairing-candidate-workflow.md` — 活证据≠Gold A、跨站同 MSKU/ASIN 传播、意图≠子串、配对≠库存主线；对应 sibling 分支 `feature/amazon-pairing-evidence`。
- **新增**: `developer-experience/cursor-tongtool-mcp-registration.md` — Cursor 通途 MCP 不会从 clone/Marketplace/安装提示出现；`setup_cursor_mcp.py` 写用户级 mcp.json；同会话 goodsQuery 200。
- **新增**: `workflow-issues/tongtool-sku-rename-gsheet-remap.md` — 通途主档 SKU 改名导致 1.7.0 漏匹配；本地 gspread 凭证 + 订单 Google Sheet 旧名替换 + goodsQuery 校验。
- **新增**: `workflow-issues/index.md`
- **更新**: `conventions/amazon-online-product-pairing-candidate-workflow.md` — 记录四家族试点的真实召回/排序指标、3,557 条分层对账、主动弃权和反馈溯源要求；明确模型未达生产门槛。
- **更新**: `conventions/amazon-online-product-pairing-candidate-workflow.md` — 记录四家族试点的真实召回/排序指标、3,557 条分层对账、主动弃权和反馈溯源要求；明确模型未达生产门槛。
- **新增**: `developer-experience/cursor-tongtool-mcp-registration.md` — Cursor 通途 MCP 不会从 clone/Marketplace/安装提示出现；`setup_cursor_mcp.py` 写用户级 mcp.json；同会话 goodsQuery 200。
- **新增**: `workflow-issues/tongtool-sku-rename-gsheet-remap.md` — 通途主档 SKU 改名导致 1.7.0 漏匹配；本地 gspread 凭证 + 订单 Google Sheet 旧名替换 + goodsQuery 校验。
- **新增**: `workflow-issues/index.md`

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
