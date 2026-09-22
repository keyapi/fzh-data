---
okf: v0.1
type: Log
title: EN_API 文档变更日志
---

# 变更日志

## 2026-09-21

- **更正（生产）**: `WO-26-02571` / `WO-26-03197` 完工归属。03197 多开的 **52 件皮壳改挂到 02571**，再把**超量的 1 件归到 02571**（`03197-001` 13→14、`03197-004` 26→25）→ 终态 **02571 = 131（超计划 1）、03197 = 25（正好）**。
  七层一起改：**跟踪单号 + 完工入库 + 21 张真实员工报工（含 `operation_id`）+ 工序 `completed_qty` + 加工耗用 + 开料工单 753 的 6 行分配及兄弟子表 + 工单 `produced_qty`/`open_material_qty`**。
  **根因**：开料工单 753 把 78 件分给只需 25 件的 03197、只给需 130 件的 02571 分 78 → 两工单 `open_material_qty` 都 = 78，
  而 `work_order_override.update_work_order_qty` 在 `open_material_qty > 0` 时把「允许入库量」替换成它 → 一个字段同时造成「02571 卡在 78」与「03197 超产到 78」。
  - 脚本 `EN_API/wo_02571_03197_reassign.py`（`probe/dry/apply 分步/verify/cleanup`，默认 dry-run）
  - 测试演练 `EN_API/wo_02571_03197_rehearsal.py`（硬锁 `ensh.vilavi.cn`，含 `purge` 重建）
  - 总结 [WO-26-02571_完工归属更正总结.md](WO-26-02571_完工归属更正总结.md)
  - 关键坑：`fix-wo-qty` 必须早于 `redo`；redo 必须 `from_bom=1` + `set_basic_rate_manually=1`；工序要换 `operation_id` 再重算；取消加工耗用遇 Completed 工单要先降状态；布料重做要带批次并临时开 `auto_create_serial_and_batch_bundle_for_outward`

## 2026-09-20

- **修复（链接）**：`.agents/skills/en-image-upload/SKILL.md`（2 条）与 `.agents/skills/item-group-translation/SKILL.md`（1 条）指向本模块的链接少退一级，由 `../../` → `../../../`。

## 2026-08-31

- **文档**: 新增 OKF bundle（物料组翻译 TMT 管道）、`AGENT_HANDOFF_物料组翻译.md`、skill `item-group-translation`
- **背景**: 生产 `item_group_translation` 已由同事用开源 Google 翻译填入；保留 TMT 脚本供后续维护
- **代码**: `translate_item_group_names.py`、`test_tmt_connectivity.py`；依赖 `tencentcloud-sdk-python-tmt`

## 2026-08-28

- **脚本**: 首版 `translate_item_group_names.py` dry-run 424/424 TMT 成功
- **密钥**: 专用 CAM 用户 `tmt-api-translation`（`QcloudTMTFullAccess`）
