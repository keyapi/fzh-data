---
okf: v0.1
type: Log
title: tongtool_order_cost 变更日志
---
# 变更日志

## 2026-09-15
- **预测锁件数**: `test_prediction_does_not_scale_with_quantity` 锁定发货数量 1/2/3 写出同一预估；线上调用方不得再 × 件数。

## 2026-09-14
- **历史尾程字段剖析更正**: 费用列口径改为「一律用 `物流商运费`」（真实回传扣款）；`包裹总运费` 口径不稳只能兜底，`通途运费` 是通途侧阶梯预估。旧的「按月份切换费用列」结论作废。
- **月初场景核对**: 用真实月初工件确认月初有约 39% 的行依赖预估，且老方式在该批上高估约 10%。
- **费率表训练口径调研**: 新增 `research/2026-09-14-rate-table-training-methodology.md`（可信度理论 / 部分池化 / GLM 分阶段 / 末公里费率卡实务 + 来源链接）。
- **多方案实测与定稿**: 新增 `model_variants.py`、`compare_history_last_leg_variants.py`、`verify_history_last_leg_model.py`、`sweep_history_last_leg_thresholds.py`；定稿配置 `RECOMMENDED_VARIANT` = 独立分层发布 + 分区优先 + 10 样本 / 2 月门槛（可信度加权与排平坦实测≈0，不启用）。
- **修复缺陷**: ①费用列口径；②`预估 × 发货数量`（运费是整包价）；③排他式分层发布吃光细层导致覆盖率归零；④`覆盖月份数` 统计错列使月份门槛失效；⑤`_as_text` 对 pandas NA 输出字符串 `<NA>`。
- **导出契约**: 新增 `history_last_leg_export.LEVEL_NAMES`（11 层），与 EN 仓库 `history_last_leg_fee.LEVEL_NAMES` 逐字一致，两侧各有测试锁定；导出时校验未知层级。
- **经验条目**: 新增 `solutions/`（3 条 logic-errors + 1 条 best-practices），按 ce-compound schema 记录。

## 2026-08-14
- **Google Sheet**: 本地 service account（`secrets/gsheets-service-account.json`，gitignore）+ `gsheets.py` / `remap_gsheet_sku.py`；从 Colab notebook cell 0 bootstrap。
- **SKU 改名**: 井维护新名，订单表替换旧名；`lookup_tongtool_sku.py` 用 ERP2 goodsQuery 校验。已处理 `通途订单202606-特殊规则` 与 `通途订单202606` 各 3 张 FBA 相关表。
- **文档**: research 六月尾程缺口、lessons（gray60 / Foam97）、Skill `tongtool-order-cost`。

## 2026-08-13
- **FBA 尾程**: 正数/0 仍跳过（账期已含）；参考值 < 0 时写入 FBA `运费` 作为账期差异冲减。同步更新 AGENT_HANDOFF 验证要点与 README 示例规则表（20260813）。

## 2026-08-12
- **新增模块**: 本地 1.7.0 特殊规则引擎 + 多 Sheet 审计工作簿，用于 AMZBAINAUS 六月异议穿透核对。
