---
okf: v0.1
type: Log
title: EN_API 文档变更日志
---

# 变更日志

## 2026-09-24

- **新增**: [reference/en-server-access.md](reference/en-server-access.md) —— EN 服务器与环境访问单一事实源（生产/测试 SSH 别名、`bench restart` 规矩、REST 凭证、3 条常见坑）。
  **背景**：仓库里 10 处把"生产 SSH 不可达"写成了事实，新会话读到后反复向用户确认入口或绕道；实测两台 SSH 一直可达，入口就在 `~/.ssh/config`。AGENTS.md 的「ERPNext 系统访问」指针由 `EN_API/README.md` 改指本页。

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
