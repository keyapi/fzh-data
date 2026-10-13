---
okf: v0.1
type: Log
title: EN_API 文档变更日志
---

# 变更日志

## 2026-10-13

- **新增（统一履约查询入口）**: `EN_API/fulfillment_query.py` + `EN_API/fulfillment/` 包 —— 在 `item_shipment_status.py` 引擎之上叠加 多输入 / 阶段 0–3 状态机 / 数量阶梯对账 / 事实·推导·估算分层 / 异常 §8 结构 + 下一行动；输出 JSON（权威）+ 控制台 + Excel（9 分区，`--legacy-sheets` 复刻旧 3 Sheet）。实现按蓝图 §3/§4/§8/§9/§12 V1。
  - **落点取舍**：**包裹引擎而非整体搬迁** —— 引擎带 fixture 断言与单测（`tests/test_item_shipment_status.py` 用 `monkeypatch.setattr(iss, "api_get_status", ...)` 打桩，要求 `paginated_get`/`api_get_status` 同模块命名空间），整体搬迁会破坏该契约且回归风险高。引擎文件**未改动**。
  - **实测踩坑**：ERPNext 对突发请求限流 —— 多打一轮冗余 DN 查询会让后续 WO 查询返回 **403 PermissionError**。已改为出库单只查一次。
  - **回归**：`--codes CENKZ1325-Yellow-138 --assert-fixture` 稳定档 14/14 通过、exit 0；`uv run pytest EN_API/tests/` 38 项通过（引擎老测试零改动）。
- **新增**: [reference/en-order-to-shipment-chain.md](reference/en-order-to-shipment-chain.md) —— **链路导航单一入口**：给一个通途 SKU，它在 ERPNext 里如何串起 销售订单→生产计划→工单→工序卡→销售出库；含链路图、每段 DocType/字段/代码落点（`item_shipment_status.py` 函数+行号）、7 条易错口径、统一查询入口、相关子项目与 PR 清单、最新实跑快照。
  **背景**：仓库此前有零散的 handoff 与蓝图，但没有一篇把「链路 + 子项目 + PR」串起来导航的文，新同事/新会话找不到入口。
- **实跑留证**: `--customer-code CENKZ1325-Yellow-138`（2026-10-13）10 张 SO / 330 件 = 有效 310 + 已改单 20；已发 166 / 未发 144（`DN 实算 == ERP delivered_qty` ✓）。
- **索引修正**: reference 索引补登此前遗漏的 `en-server-access.md`。
- **补业务口径（更准）**:
  - **退货净额抵扣**（修 bug）：`shipped_dn` 原先把退货型 DN 行（`is_return`）排除，导致有退货时 `DN 实算 == ERP delivered_qty` 校验翻车。改由新抽出的引擎函数 `enrich_so_rows` 按 docstatus=1 的**带符号 qty** 汇总（退货行负数自动抵扣）；`build_context` 与 fulfillment 共用该函数，避免口径分叉。Sheet2「计入已发」增「退货抵扣」标记。fixture 客户无退货 → 数字零变化。
  - **异常新增**：交期逾期（真实 SO 交期已过仍未发，与引擎「下单+3月」估算不同）、工序停滞（在产工单 N 天无新报工，阈值 `--stall-days` 默认 14）。
  - **整单齐套**（`--scope full_order_kit`，opt-in）：按**成品 BOM**（`BOM.items`，权威来源，非前缀约定）展开配套件，逐件算「已完工（工序卡第一道工序）+ 工厂侧库存」的可信可用量，取 min；简化（→`SXBZPK#`）/自引用 BOM 标「无法展开」。组件可用量为**全局**（未按订单行分配），到货仓/国外仓库存不计入（蓝图 §5/§13）。
  - 测试：`uv run pytest EN_API/tests/` **45 项通过**；`--assert-fixture` 仍 14/14、exit 0。

## 2026-09-24

- **新增**: [reference/en-server-access.md](reference/en-server-access.md) —— EN 服务器与环境访问单一事实源（生产/测试 SSH 别名、`bench restart` 规矩、REST 凭证、3 条常见坑）。
  **背景**：仓库里 10 处把"生产 SSH 不可达"写成了事实，新会话读到后反复向用户确认入口或绕道；实测两台 SSH 一直可达，入口就在 `~/.ssh/config`。AGENTS.md 的「ERPNext 系统访问」指针由 `EN_API/README.md` 改指本页。

## 2026-09-23

- **新增文档**：[reference/BOM成本报表逻辑.md](reference/BOM成本报表逻辑.md) —— `BOM Cost List V2` 报表的**逐列说明（业务版，拟发给非技术同事）**：每列含义与计算方式、取数规则、看数注意、常见疑问；全篇不含代码。
  依据报表源码整理，含两条实测验证：①成本口径是「材料 + 工序 + **加**废料」，与 ERPNext `total_cost` 的「减废料」**符号相反**（当前全库无废料项，未暴露）；②成本要求 BOM 同时「已启用 + 已设默认」，否则显示 0（生产 `KS0464-FHXYR-60x45x42-RED` 即因此为 0）。

## 2026-09-21

- **更正（生产）**: `WO-26-02571` / `WO-26-03197` 完工归属。03197 多开的 **52 件皮壳改挂到 02571**，再把**超量的 1 件归到 02571**（`03197-001` 13→14、`03197-004` 26→25）→ 终态 **02571 = 131（超计划 1）、03197 = 25（正好）**。
  七层一起改：**跟踪单号 + 完工入库 + 21 张真实员工报工（含 `operation_id`）+ 工序 `completed_qty` + 加工耗用 + 开料工单 753 的 6 行分配及兄弟子表 + 工单 `produced_qty`/`open_material_qty`**。
  **根因**：开料工单 753 把 78 件分给只需 25 件的 03197、只给需 130 件的 02571 分 78 → 两工单 `open_material_qty` 都 = 78，
  而 `work_order_override.update_work_order_qty` 在 `open_material_qty > 0` 时把「允许入库量」替换成它 → 一个字段同时造成「02571 卡在 78」与「03197 超产到 78」。
  - 脚本 `EN_API/wo_02571_03197_reassign.py`（`probe/dry/apply 分步/verify/cleanup`，默认 dry-run）
  - 测试演练 `EN_API/wo_02571_03197_rehearsal.py`（硬锁 `ensh.vilavi.cn`，含 `purge` 重建）
  - 总结 [WO-26-02571_完工归属更正总结.md](WO-26-02571_完工归属更正总结.md)
  - 关键坑：`fix-wo-qty` 必须早于 `redo`；redo 必须 `from_bom=1` + `set_basic_rate_manually=1`；工序要换 `operation_id` 再重算；取消加工耗用遇 Completed 工单要先降状态；布料重做要带批次并临时开 `auto_create_serial_and_batch_bundle_for_outward`

## 2026-09-14

- **脚本**: 新增 `item_shipment_status.py` — 客户物料号 / EN 物料号 → 销售订单发货状态 + 生产计划/工单/工序卡报表（单物料颗粒度，3 sheet Excel，`--assert-fixture` 回归自检）
- **文档**: 新增 `../AGENT_HANDOFF_物料发货状态.md`；本索引补登该 handoff 与既有的 `../AGENT_HANDOFF_DN追溯报表.md`（此前只登了物料组翻译专题）
- **沉淀**: `docs/solutions/workflow-issues/erpnext-so-closed-unshipped-and-unstarted-work-orders.md` — 子表反查父单的 API 铁律（子表直查 403 / 父单直查子字段 417 / 子表过滤"一行一子行"须按父单去重 / `in` 列表超 4094 字节请求行须分块），以及两条反直觉结论：`Closed` ≠ 已发完、`Work Order.status` 不可信（进度看工序卡）
- **背景**: 排查某客户物料号的销售订单发货情况；实测 10 张 SO / 330 件，已发 126 / 未发 184
- **评审修正**: 订单行 `item_code` 改为精确匹配（避免 `--item KS…` 带上 `PK#`/`ND#` 同行）；工序卡/工单取消件不计入进度；工单按 SO×物料挂行；完成量优先 `total_completed_qty`；超产跟工序卡比 `WO.qty`；`--assert-fixture` 只认客户码入口；list 查询 HTTP 失败不再当空结果；中文工单方法论收回「一键完工痕迹链」AND 门；主 `AGENT_HANDOFF.md` 补登发货状态 / DN 追溯
## 2026-09-20

- **修复（链接）**：`.agents/skills/en-image-upload/SKILL.md`（2 条）与 `.agents/skills/item-group-translation/SKILL.md`（1 条）指向本模块的链接少退一级，由 `../../` → `../../../`。

## 2026-08-31

- **文档**: 新增 OKF bundle（物料组翻译 TMT 管道）、`AGENT_HANDOFF_物料组翻译.md`、skill `item-group-translation`
- **背景**: 生产 `item_group_translation` 已由同事用开源 Google 翻译填入；保留 TMT 脚本供后续维护
- **代码**: `translate_item_group_names.py`、`test_tmt_connectivity.py`；依赖 `tencentcloud-sdk-python-tmt`

## 2026-08-28

- **脚本**: 首版 `translate_item_group_names.py` dry-run 424/424 TMT 成功
- **密钥**: 专用 CAM 用户 `tmt-api-translation`（`QcloudTMTFullAccess`）
