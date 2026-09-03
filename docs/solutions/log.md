---
okf: v0.1
type: Log
title: 解决方案变更日志
tags: [solutions, log]
---

# 变更日志

## 2026-09-03
- **新增**: `developer-experience/workbuddy-custom-model-newapi-config.md` — WorkBuddy 接公司 new-api 自定义模型，`useCustomProtocol` 必须 `false` 且 `url` 带 `/v1`，否则发消息只回「任务完成」无正文。

## 2026-08-31
- **更新**: `integration-issues/nas-multi-domain-access-openwrt-quickconnect.md` — QC 与 DSM 外部访问 DDNS 架构澄清；路径 A（OpenWrt 自定义域）vs 路径 B（QC/myds）；勿删 myds、无 DDNS 优先开关。

## 2026-08-28
- **新增**: `integration-issues/nas-multi-domain-access-openwrt-quickconnect.md` — NAS 多域名（nas.daneey.com / nas.vilavi.cn）、OpenWrt ACME 第二张证、DSM 反代铁律、QC 直连/cn4、联通 443 限制；政策保留 `fangzhouhui.quickconnect.cn` 统一入口。
- **新增**: `NAS_API/` OKF bundle、`AGENT_HANDOFF.md`、`.agents/skills/nas-access/`。
## 2026-08-25
- **新增**: `workflow-issues/en-channel-account-gsheet-sync.md` — Google 表渠道账号 → 生产 EN Channel Account；人变才加行；Amazon 禁止 EUR、按 Johna 九国拆；Illiosenergy/`ILLIOSPL`。
- **新增**: `channel_account_sync/` 折叠/命名库、fetch/compare/apply、OKF、Skill。
- **生产结果**: 2026-08-25 新建 18 账号、10 别名、122 个已有账号补负责人，Kaufland 补 AT/IT/FR；未建 `AMZFZHSXEUR`。

## 2026-08-24
- **新增**: `workflow-issues/sellfox-cover-combo-create-ops.md` — 三角皮壳 `PK# -> KS x1` 组合代理批量创建；与 EN `TJ#`/`sync-combos` 分流；`pageList total=0` 翻页、禁止并行 apply、组合商品不在普通商品。
- **新增**: `SELLFOX_API/cover_combo_ops.py` / `cover_combo_plan.py` 与 `docs/reference/cover-combo-ops.md`。
- **生产结果**: 2026-08-21 `status` 计划 955、线上 957 全 `isGroup=1`、`need_create=0`；只读配对候选 604（Active 91），未写 `matchByMsku`。
- **更新**: 共享库存代理 convention 阶段 2 对 KS0001/KS0248 标已完成；Skill / HANDOFF / CONCEPTS 分流。

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
- **新增**: `workflow-issues/retro-sofa-combo-batch-staging.md` + `SELLFOX_API/retro_sofa_stage.py` — 复古造型大体量沙发四模块组合 1 个创建并回读（`sync-combos` `ok=1`）。
- **新增**: `workflow-issues/outdoor-pad-combo-batch-staging.md` + `SELLFOX_API/outdoor_pad_stage.py` — 户外托盘垫 6 个套装按确认组成创建并回读（`sync-combos` `ok=6`）。
- **新增**: `workflow-issues/fringe-sofa-combo-batch-staging.md` + `SELLFOX_API/fringe_sofa_stage.py` — 弧形流苏沙发单件整沙发组合创建并回读（`sync-combos` `ok=1`）。
- **新增**: `workflow-issues/comma-sofa-combo-batch-staging.md` + `SELLFOX_API/comma_sofa_stage.py` — 逗号组合沙发 2 个组合创建并回读（`TJ#KS0369x1_KS0378x1_KS0379x1-001/002`，赛狐 3924081/3924082）。
- **新增**: `workflow-issues/triangle-set-combo-batch-staging.md` + `SELLFOX_API/triangle_set_stage.py` / `triangle_set_apply.py` — 三角有扣套装 13 个组合创建并回读（`TJ#KS0001x1_KS0260x1-001~003`、`x2-001~010`，赛狐 3924083~3924095）。
- **更新**: `workflow-issues/index.md`、`docs/solutions/index.md`、`CONCEPTS.md`
- **评审修正**: Cursor 审查后拆分 EN Tongtool Cost Review 与特殊规则 1.7.0 引擎（`engine_170.py`），禁止把本地特殊规则当 Cost Review 实现；修正库存模型/核心验收标题和阶段编号；不可破坏规则限定为组合代理模型；审计脚本 next_actions 指向 4B 成本覆盖；missing-products 补充已有独立普通 `PK#` 的评估路由；CONCEPTS 引擎路径修正为完整 `tongtool_order_cost/tongtool_order_cost/engine_170.py`，扣减规则明确仅组合代理适用。
- **更新**: `conventions/sellfox-cover-shared-inventory-transition.md` — `PK#` 组合从永久/冻结模型降为并行期单一实物池下的推荐默认；补充独立普通商品、外部共享池分配器、重复 ATP 风险及一对多/多对一库存守恒。成本路线改为验证 FBM 订单采购成本导入覆盖，记录 `mergePurchaseCost`、调整单 API 与加工单写链缺口，沙盒拆为库存和成本两条。
- **更新（早期阶段，已由上一条继续收敛）**: `conventions/sellfox-cover-shared-inventory-transition.md` — [#191](https://github.com/keyapi/fzh-data/pull/191) 在波兰 covers 确认之后：组合采购成本复选框只改商品主数据；子件 `KS` 仓 FIFO 仍不是皮壳部分成本；EN Tongtool Cost Review 按 `-Cover`/`-Foam`/`-1`/`-2` 与交付形态切片，赛狐无对等定制；当时先暂停新测试单，后续改为可用已有皮壳 FBM 订单验证成本覆盖。

## 2026-08-20
- **新增**: `conventions/sellfox-cover-shared-inventory-transition.md` — 固化三角类在通途/赛狐并行期以 `KS` 普通商品承接库存、`PK# -> KS x1` 组合商品承接皮壳 Listing 的共享库存代理；明确不是 EN Product Bundle/BOM，加工商品留待通途退役后评估，并定义单 SKU 沙盒三项验收。
- **新增**: `sellfox_cover_inventory/` 与 `.agents/skills/sellfox-cover-inventory/` — OKF bundle、Handoff、只读审计脚本及触发路由。
- **更新**: `conventions/sellfox-cover-shared-inventory-transition.md` — 美中皮壳仓 vs DANEEY 主仓；FBA/退货审计 blocked；missing-products 禁止的是有库存 `PK#` 普通商品。
- **更新**: 用户确认赛狐 `POLAND` 对应通途 covers 仓、不对应 `FZHPoland-finished`；只读审计仅对波兰成品仓名 `cautions`。
- **新增**: `conventions/erpnext-product-cover-variant-pairing.md` — 三角靠枕/无扣成品↔皮壳 suffix 审计、一键配套复制而非笛卡尔、独立 PK# 须重建（CannotChangeConstantError）、cover-only 176/27 暂缓。
- **更新**: `conventions/erpnext-item-variant-creation-convention.md` — 独立皮壳禁止 PUT `variant_of`，改为无库存重建。

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
