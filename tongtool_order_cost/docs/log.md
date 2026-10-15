---
okf: v0.1
type: Log
title: tongtool_order_cost 变更日志
---
# 变更日志

## 2026-10-15
- **`default_material_request_type` 调查（只读，subagent）**：ERPNext 标准字段，挂在 **`Item`**（非 Item Group），Select 五值。
  实测分布 **Purchase 10,124(66.6%) / Manufacture 5,086(33.4%)**，全库只这两值；三个分公司的国外包装成品
  （`USTXBZCP#`/`USNJBZCP#`/`PLBZCP#`）**100% Purchase** —— **与「大部分是工单入库」的印象相反**。
  唯一活读取是 ERPNext 核心 Production Plan（+`work_order_task` 同义一行）；**无已装 app 写它**。
  与「绍兴发货方式」**正交、不冲突**（每个发货方式桶里两值都有）；**不能区分**三种绍兴发货情况。
  **2025 年起不再维护**（2024 M 4567>P 3176；2025 M 495<P 6198）→ 不能自证对错。详见
  `docs/reference/en-material-request-type-spec.md`。
- **PL「成品却带非零加工成本」16 个调查（只读，subagent）**：15 个启用项合计 **1463.17**（+停用 `KS0524-140` 158.53 = 1621.70）。
  **来源是 2025-02-21 建料批次的人工 `Item.valuation_rate` 残值**（`tabVersion` 留痕 `0.0→人民币NN`），**任何 docstatus 下都没有 BOM**；
  只有 `KS0524-140` 等于其自身 BOM 的 `total_cost`。**不是海绵那批**（横跨 16 条品线）。
  该值进 `波兰加工成本-PL → destination_processing_cost → 皮壳尾程前成本 pllc_cover`，**不影响绍兴总成本**；
  ⚠️ 但 `:1582-1583` 守卫在 `destination_processing_cost==0` 时会把整行 `pllc_cover` 置 0，故**按订单加权的实际差异 ≠ 1463.17**。
  皮壳侧另有 18 个同类残值 1707.801 未逐条展开。详见 `docs/reference/en-pl-finished-processing-nonzero-spec.md`。
- **KS0524 定性（用户说明）**：三角靠枕·碎海绵填充款（PP棉→海绵那批），目前只发 FBA、国外无海绵也不操作填充 → **国外加工成本应为 0**；
  其 `USTXBZCP#` 被禁用很可能与此相关。已回填 `en-shaoxing-ship-method-taxonomy-spec.md`。
- **绍兴发货方式 分类与「成品→国外加工=0」调查（只读，subagent）**：`绍兴发货方式` 不是物料组名，而是
  Item Group 自定义字段 `custom_shipment_type_to_branch`（Select：皮壳/成品/半成品），由物料代码推 KS 号再找
  `custom_model_id=KS` 的物料组读取（`bom_cost_list_v2.py:621/723/1383`）。401 个 KS 物料组：成品165/皮壳156/半成品62/空18。
  - **「成品 → 国外加工成本应为 0」在代码里未实现**；但**美中侧事实已满足**：sheet 上 `成品` **639 行、`美中加工成本, USTX` 非 0 行数 = 0**
    （`皮壳` 2760/2853 非 0、`半成品` 166/167 非 0）→ **现有 B2/B3 对成品行没有高估**。只有 **PL** 有 16 个成品非零（1621.70），是漏网。
  - **36 张「绍兴源 BOM 无 PP棉行」＝ 34 成品 + 2 皮壳**，行内容只有海绵/碎海绵 + 纸箱/袋类/扣胚等（6 张是单行自引用 = 自采形态）。
  - **无「国外加工成品 BOM」的任何证据**（只有「国外分公司BOM复制」，前缀全是「包装成品」）。
  - **三种绍兴发货情况（直接采购 / 不用加工 / 仍需加工后发成品）当前不可区分** —— 只有一个 `发货方式` 字段，「成品」是单一桶，缺「是否自采购/是否需二次加工」标记。
- **新增 B3 新工资情景**：`ustx-compare` 增加第 4 口径 B3 —— B2 基础上把美中「二次加工成本」
  按**新工资率 167.8→105** 调整（只动 `operating_cost`；`hour_rate = labour + manage`，167.8+34.24=202.04）。
  按「**9/3 快照数值**」匹配当时的 BOM（该物料可有多张 BOM，必须按 `total_cost` 值匹配，不能取当前默认，否则混入其它变量）。
  CLI 新增 `--wage-boms`（默认 `out/ustx_wage_sim/ustx_boms_all.csv`）；命中 3962/4379 行。
  **7 月美中**：A 526,225 → B2 791,137 → **B3 717,678**（ΔB2 +264,912 / ΔB3 **+191,453**）——
  工资率一项影响约 **7.3 万/月**。
- **踩坑**：首版把每个 sheet 行的 Δ **累加**到重量模板（同模板多行 → 被乘 N 倍，B3 变成 −192 万的负巨值）。
  改为「同模板 Δ 必须唯一，冲突判歧义不猜」后正常。
- **EN 美中 USTX 加工成本工资率链路逆向（只读）**：定位 `美中加工成本, USTX` 列来源 —— USTXBZCP# 物料
  「is_active=1 且 is_default=1」BOM 的 `total_cost`（无则回退 `Item.valuation_rate`）；
  `total_cost = raw + operating + scrap`（309 张 BOM 0 例外），**只有 `operating_cost` 随工资率变**。
- **167.8 定位**：存于 `Workstation` 记录 `美中USTX包装` 的 `hour_rate_labour`（同记录 `hour_rate_manage=34.24`，
  净 `hour_rate=202.04`）；**不是** 标准 `Workstation.hour_rate`，**也不是** 自定义 DocType `Hour Rate`（生产库 0 行）。
- **复制 BOM 机制**：`BOM.on_submit → auto_copy_bom_on_submit` → `utils/bom.copy_bom_with_new_item`（整张 BOM 复制，
  改价目表 + PP 棉筛选 + 工序工站/工费率改写后重算 `operating_cost`）。
- **167.8→105 复算**：净工费率 202.04→139.24；309 张 BOM，304 张受影响；`sum_delta=−7,217.3057`（等权逐 BOM）、
  仅 active+default 的 `sum_delta=−5,884.464667`。产出 `out/ustx_wage_sim/{ustx_bom_ops.csv, summary.json, build_sim.py}`。
- **文档**：`docs/reference/en-ustx-bom-wage-rate-spec.md`（完整规格 + 未证实项）。

## 2026-10-14
- **美中 USTX 三方案对比**：新增 `tongtool_order_cost/ustx_cost_compare.py` + CLI `ustx-compare`（纯离线）——
  A 现状(2CJG-SX) / B1 测算表 / B2 EN-import 重建 三口径逐行对比 + 仓库×品类×绍兴发货方式归因 + fail-closed 闸门。
  7 月美中 4,379 行：A 合计 526,225 → ΔB1 +226,629 / ΔB2 +264,912（￥加权）。
- **只读快照双冻结**：`audit_sources.SourceSpec.render_option ∈ {values, formulas}`，同一 worksheet 可分别冻结显示值与公式；
  `snapshot --with-finance` 注册 USTX 成本源（绍兴二次加工 / 测算美中USTX / import皮壳成本 / importBOMCostList）。
- **口径教训**：`测算 美中USTX二次加工成本` 的月度值是**手填、无公式** → B1(人工) 与 B2(import 重建) 在 57 个共有键上无一相等，
  **差异即结论**，不设「必须相等」阻断闸门；`import皮壳成本` 同键不同重量模板的冲突键不进索引、对应行排除（不猜值）。
- **文档**：`docs/reference/monthly-profitability-audit.md` 增 USTX 对比章节；学习正文见
  `docs/solutions/architecture-patterns/ustx-cost-caliber-comparison.md`。
- **头程口径核实（b）**：新增 `build_head_freight_index` —— 从 `EN产品BOM成本列表20260202`
  （`importBOMCostList` 的**超集**，前 25 列值完全一致）按 `绍兴发货方式` 取头程
  （半成品→半成品头程、成品→成品头程、皮壳→皮壳头程，缺则皮壳兜底，键=重量模板）。
  **结论：订单表 A 的头程本就等于该值（Colab 的 EN 覆盖层）→ Δ=0**，
  用户设想的「半成品用半成品重量」已在 A 生效。命中 4328/4379 行。
  唯一分歧点是「按皮壳重量」勾选项 —— 启用后头程再变 **−16,517**（7月，￥加权），已作为敏感度写入产出。
- **财务口径说明（c）**：新增 `docs/reference/ustx-cost-caliber-note.md` —— 给财务/业务的口径变更说明
  （A/B1/B2 差额表 + 分歧归因 + 4 项待确认：加工费口径 / 半成品包装成本 / 头程重量基准 / 工资 167.8→105）。
- **最终差额**：美中四项合计 A 526,225 → B2 791,137（ΔB2 **+264,912**，+50%）；
  主由二次加工 +225,982、绍兴二次加工 +38,930；皮壳/头程 Δ=0。

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
