---
okf: v0.1
type: Log
title: tongtool_order_cost 变更日志
---
# 变更日志

## 2026-11-11
- **特殊规则换表**：1.7.0 改读 ws `黄-特殊规则-订单改销售额成本`；旧 `Jeck特殊规则-订单改销售额成本` 只读留存。13 行混合规则按老板口径**参考值优先**（清系数），引擎打印提醒并新增 `meta["n_mixed_ref_priority"]`。
- **FBA 列对齐**：28 条 FBA 规则的 `二次加工`/`绍兴二次` 参考值对调（二次=0、绍兴承接），数值和总净额不变；Colab cell 22 同步参考值优先。
- **成本口径**：记录旧 9/3 BOM 与最新 BOM 的差异，阅读枕第 776–777 行由扣减 −77.8/件变为 +20.2/件；老板 2026-11-10 确认按现有参考值执行。详见 `docs/solutions/workflow-issues/tongtool-special-rule-ref-priority-and-bom-caliber.md`。
- **成本口径补充**：分公司发成品二次=0（202609 18 行 −1,341.65；202608 16 行 −1,303.48）；FBA 绍兴二次直接用 `cost_sxbzcp`，不再用 `sx_cost_all−cost_fg`（264 行 `sx_cost_all=0` 会低估）；最终表是 `build_tabs/1104 BOM`，`out/merged_202609.csv` 11-04 为旧表。

## 2026-09-18
- **月度链路 runbook**：新增 `docs/reference/monthly-tail-cost-pipeline.md`（通途导出→清表头→EN 列表入口→键值合并→GSheet in-place；含覆盖率口径与「缺尾清单」整理）。
- **口径结论**：`needs=1` 分母下，202606 通途实收尾程覆盖 **99.6%**（李惠预估补 21、0 遗漏）；202607 首轮 **75.0%** → 09-18 再导后 **87.3%**，EN 历史预估补 833，**仍缺 25**。
- **缺尾清单**（给运营/物流商核对账单）：筛选 `needs=1 且 来源∈{历史预估,通途运费}`；主战场 GLS 波兰（737 行/714 包裹）与 US-FedEx（91）；排序 `发货方式→邮寄方式→发货日期→发货时间→包裹号`，冻结首行。

## 2026-09-11
- **新增脚本**: `scripts/upload_monthly_order_sheet.py` — 月度成品 xlsx → 固定 gsheet 月度 ws（`通途订单YYYYMM` / `YYYY年M月订单`）。
  patch 模式：`duplicate_sheet`（留原索引，FBA 左侧）→ 旧 ws 归档 `弃用… <日期>` → **只覆盖变化列**（默认 `物流商运费`）→ 回读校验；
  不做 `clear()` 整表写（单请求体积上限 ~10MB，且 clear 后有空窗丢数据风险）。参考 `docs/reference/gsheet-monthly-sheet-upload.md`；Skill `gsheet-monthly-order`。
- **实践**: 202607 已按该约定上表（旧 ws → `弃用2026年7月订单 20260911`），`物流商运费` 更新为 EN 预估尾程合并值（合计 711,513.38）。
- **调研**: 新增 `docs/research/2026-09-11-gsheet-write-efficiency.md`（官方限制/配额出处 + 各写法对比）；据此脚本新增 `--in-place`（仅覆盖指定列、不复制/不归档），并对 `2026年7月订单` 实跑原地覆盖（9604 格、2 次写请求、回读一致）。
- **整表替换**: 脚本新增 `--replace-sheet`（Drive 转换 xlsx→临时 Google 表格 + `sheets.copyTo` 一次拷入 → 改名/定索引 → 删临时表；依赖新增 `google-api-python-client`）。已在临时试跑表格端到端验证通过。

## 2026-08-14
- **Google Sheet**: 本地 service account（`secrets/gsheets-service-account.json`，gitignore）+ `gsheets.py` / `remap_gsheet_sku.py`；从 Colab notebook cell 0 bootstrap。
- **SKU 改名**: 井维护新名，订单表替换旧名；`lookup_tongtool_sku.py` 用 ERP2 goodsQuery 校验。已处理 `通途订单202606-特殊规则` 与 `通途订单202606` 各 3 张 FBA 相关表。
- **文档**: research 六月尾程缺口、lessons（gray60 / Foam97）、Skill `tongtool-order-cost`。

## 2026-08-13
- **FBA 尾程**: 正数/0 仍跳过（账期已含）；参考值 < 0 时写入 FBA `运费` 作为账期差异冲减。同步更新 AGENT_HANDOFF 验证要点与 README 示例规则表（20260813）。

## 2026-08-12
- **新增模块**: 本地 1.7.0 特殊规则引擎 + 多 Sheet 审计工作簿，用于 AMZBAINAUS 六月异议穿透核对。
