---
okf: v0.1
type: Log
title: EN_API 文档变更日志
---

# 变更日志

## 2026-09-14

- **脚本**: 新增 `item_shipment_status.py` — 客户物料号 / EN 物料号 → 销售订单发货状态 + 生产计划/工单/工序卡报表（单物料颗粒度，3 sheet Excel，`--assert-fixture` 回归自检）
- **文档**: 新增 `../AGENT_HANDOFF_物料发货状态.md`；本索引补登该 handoff 与既有的 `../AGENT_HANDOFF_DN追溯报表.md`（此前只登了物料组翻译专题）
- **沉淀**: `docs/solutions/workflow-issues/erpnext-so-closed-unshipped-and-unstarted-work-orders.md` — 子表反查父单的 API 铁律（子表直查 403 / 父单直查子字段 417 / 子表过滤"一行一子行"须按父单去重 / `in` 列表超 4094 字节请求行须分块），以及两条反直觉结论：`Closed` ≠ 已发完、`Work Order.status` 不可信（进度看工序卡）
- **背景**: 排查某客户物料号的销售订单发货情况；实测 10 张 SO / 330 件，已发 126 / 未发 184

## 2026-08-31

- **文档**: 新增 OKF bundle（物料组翻译 TMT 管道）、`AGENT_HANDOFF_物料组翻译.md`、skill `item-group-translation`
- **背景**: 生产 `item_group_translation` 已由同事用开源 Google 翻译填入；保留 TMT 脚本供后续维护
- **代码**: `translate_item_group_names.py`、`test_tmt_connectivity.py`；依赖 `tencentcloud-sdk-python-tmt`

## 2026-08-28

- **脚本**: 首版 `translate_item_group_names.py` dry-run 424/424 TMT 成功
- **密钥**: 专用 CAM 用户 `tmt-api-translation`（`QcloudTMTFullAccess`）
