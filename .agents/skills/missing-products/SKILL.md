---
name: missing-products
description: >
  通途有库存 SKU 的 EN/ERPNext/赛狐三方一致性审计、客户物料号补登和赛狐多属性 SKU 补齐。
  当用户提到"缺失商品"、"missing_products"、"通途有库存"、"通途SKU未登记"、
  "三方一致性"、"Cover"、"Foam"、"赛狐缺SKU"、"EN赛狐核对"、库存同步映射、
  "皮壳变体"、"成品缺皮壳"、"一键创建配套物料"时触发。
  不用于只计算采购成本、商品重尺。
  不把 PK#/HM1510 建成赛狐**有库存普通商品**；三角皮壳 Listing 的共享库存代理走 sellfox-cover-inventory，已有独立普通 PK# 的评估也走该模块。
---

# 通途有库存 SKU 三方补齐

## Read First

1. `missing_products/AGENT_HANDOFF.md` — 当前状态、历史例外和数据源。
2. `docs/solutions/conventions/tongtu-en-sellfox-instock-sku-mainline.md` — 主线规则、设计过程、写入边界和验证清单。
3. `missing_products/docs/lessons/2026-08-11-tongtu-en-sellfox-mainline-completion.md` — 完整复盘、失败模式和防护。
4. 用户提到 Amazon 在线商品、MSKU、配对建议、未配对或别名匹配时，先读 `amazon_pairing/AGENT_HANDOFF.md` 和 `docs/solutions/conventions/amazon-online-product-pairing-candidate-workflow.md`。证据传播分支再读 `amazon_pairing/docs/reference/` 与 `amazon_pairing/knowledge/golden-cases.yaml`。PR 173（LTR）与 `feature/amazon-pairing-evidence` 是 sibling：本轮高可信用当前已配对唯一目标，不重训 LTR，不调用配对写接口。
5. 需要新增 EN 变体时再读 `.agents/skills/erpnext-item-create/SKILL.md` 和 `docs/solutions/conventions/erpnext-item-variant-creation-convention.md`。
5b. 成品↔皮壳 1:1 审计、独立 `PK#` 重建、cover-only 暂缓：`docs/solutions/conventions/erpnext-product-cover-variant-pairing.md`；脚本 `missing_products/fix_missing_cover_variants.py`（默认 dry-run）。
5c. 赛狐皮壳 Listing / `PK#` 组合代理 / 通途并行期共享库存：改走 `.agents/skills/sellfox-cover-inventory/SKILL.md`，不要在本流程创建赛狐 `PK#` 普通商品。
6. 需要赛狐 API 时再读 `.agents/skills/sellfox-api/SKILL.md` 和 `.agents/skills/multi-attr/SKILL.md`。

不要根据旧 xlsx、单个 BOM 报表列、SPU 名称或记忆直接下结论；先重新取数。

## 不能违反的业务契约

- 每个有库存的**完整**通途 SKU（含 `-Cover`、`-Foam`）必须登记到至少一个 EN `KS` 产品成品变体的 `customer_items.ref_code`；匹配大小写不敏感。
- 去尾缀后的基码只能找候选，绝不能把“仅基码匹配”报告为“已登记”。
- `PK#` 皮壳、`HM1510` 海绵、BOM 组件或辅料上的客户码不能替代产品成品登记。
- 原因：EN 销售订单 Excel 先用通途 SKU 找到 EN 产品，再由“皮壳/成品/半成品”列决定交付形态。
- 赛狐三方主线对象仍是 EN 产品 `item_code`（`KS` 普通商品）。不要用通途 `-Cover/-Foam` 原码、`HM1510` 或把 `PK#` 建成**有库存普通商品**。该禁止针对本流程的创建主线；三角类确有皮壳 Listing 时的 `PK# -> KS x1` 组合代理不走本流程，见 `sellfox-cover-inventory`。若赛狐已有独立普通 `PK#` 且业务确认独立数量池，也由 `sellfox-cover-inventory` 评估，不在本流程创建或自动改类型。
- 一个通途码已正确挂在多个 EN 产品时，保留全部关系并报告；本流程不清理历史一对多。
- 不修改既有赛狐 SKU 的在售/停售状态；赛狐属性缺失时先生成导入 Excel，等用户确认导入成功后才 API 创建 SKU。
- Amazon 配对属于独立的在线商品机制；先输出并审阅候选，只有用户批准明确的 MSKU/店铺/赛狐 SKU 范围后才可导入或调用写接口。
- 套件、其他非产品项、主体骨架，以及配套物料上的既有客户码都属于暂缓/只读范围；除非用户明确授权，不迁移、不删除、不纳入本轮写入。

## 标准流程

### 1. 建立新鲜、可复现的只读快照

1. 重新生成 EN BOM Cost List。服务器 Script Report `key_test.bom_cost_list` 的 6 个 filters 不可缺少：`item_group=产品`、`show_disabled=1`、`show_ref_code=1`、`sum_columns_at_end=1`、`pllc_sfg_missing_use_cover=0`、`simplified_column_view=0`。
2. 获取最新通途合并库存导出，只统计 `可用库存 > 0` 的完整 SKU。
3. 通过 EN REST 拉取范围内产品 Item 的完整 `customer_items` 子表；BOM 报表的单列客户码不能作为完整关系来源。
4. 通过赛狐 API 分页拉取全部商品 SKU，并保存 SPU、SKU、名称和属性。
5. 运行 `uv run python missing_products/audit_three_systems.py`；保留输出，不要手工删未匹配行。

### 2. 以完整码判定 EN 登记

允许的四种状态：

| 状态 | 含义 | 后续动作 |
|---|---|---|
| 已精确登记 | 完整码存在于至少一个 EN 产品 | 检查这些产品的赛狐 SKU |
| 仅基码匹配 | 仅去 `-Cover/-Foam` 后缀后的码有候选 | 不能算完成；核对属性和适用关系 |
| 真正未登记 | 完整码和基码都没有产品关系 | 分类，保留给业务判断 |
| 候选不唯一 | 有多个候选但没有可靠属性证据 | 不写入，单列请用户确认 |

对拉链款弧形靠枕等共用皮壳场景，只要完整 `-Cover` 码在至少一个正确 EN 产品上即达到主线要求；已有多挂关系保留。

### 3. 先报告、后写 EN

1. 按产品、皮壳、海绵、主体骨架、套件、其他非产品项拆分报告；任何输入记录都必须进入一个分类，并做 `输入 = 精确登记 + 暂缓 + 待确认` 对账。
2. 只把“完整码未登记、目标产品为 KS 成品、基码和属性均支持、客户码未被其他产品占用”的记录放入写入候选。
3. 先 dry-run；得到用户确认后才以显式 allowlist 执行 `--apply`。绝不根据名称模糊匹配批量写生产。
4. 写入后逐条回读目标 Item 的 `customer_items`，确认完整码存在；同时检查全局占用，避免写到错误属性组合。

当前已验证的最小写入脚本是 `missing_products/register_product_customer_codes.py`。扩展前先增加测试和 dry-run 输出，不把批准范围隐含在推断逻辑中。

### 4. 核验或创建赛狐产品 SKU

1. 只对已有 EN 产品精确映射的 `item_code` 检查赛狐；先检查 SPU、SKU、名称、属性名和属性值。
2. 若 EN 产品 SKU 已存在，保持状态不变；报告名称或属性差异，不顺手改状态。
3. 缺赛狐属性时，生成属性管理导入 Excel，使用已有赛狐模板；OpenAPI 没有创建属性簇/属性值的端点。用户导入成功前停止。
4. 用户确认属性已导入后，调用赛狐商品 API 创建缺失 SKU。新 SKU 的编号和名称必须与 EN 的 `item_code`、`item_name` 完全一致，属性顺序采用面料、尺寸、颜色。
5. 创建后重新分页获取赛狐全量 SKU 列表回读验证。缺口为零才可报告成功。

### 5. 生成业务工作簿

复用 `missing_products/build_mainline_report.mjs`，至少包含：汇总、套件暂缓、其他非产品项暂缓、皮壳通途 SKU、海绵通途 SKU、主体骨架后续、一对多历史关系、通途映射全量。每行需有完整通途 SKU、库存、EN 精确登记次数和产品、候选与依据、赛狐产品 SKU 状态和建议动作。

## 完成关口

1. 重新取数后总数对账成立，且未匹配项没有被静默省略。
2. 皮壳和海绵有库存 SKU 中，除用户显式暂缓或候选待确认项外，EN 产品完整码未登记为 0。
3. 上述 EN 产品在赛狐的对应产品 SKU 缺口为 0。
4. 新增 EN 登记逐条回读；新增赛狐 SKU 从全量列表回读。
5. 跑 `uv run pytest tests/missing_products -q`、Python 编译检查和 `git diff --check`；PR 前执行凭证扫描。

## 已知起点与后续边界

2026-08-11 已验证基线：通途有库存 1411 个 SKU，1397 个精确登记 EN 产品，剩余 14 个为 2 套件 + 12 已知非产品项；108 个皮壳和 25 个海绵通途 SKU 均已精确登记，映射的 EN 产品 SKU 均已存在于赛狐。该数字是当日快照，每次任务仍必须重新取数。

主线结束后才做只读调查：PK#/HM1510 已有客户码、同一通途码在产品与配套物料上的重叠、弧形靠枕共用皮壳和海绵的长期维护策略。不要把调查倒灌为本轮产品登记的替代方案。

## 入口脚本

- 审计：`missing_products/audit_three_systems.py`
- 已批准客户码写入：`missing_products/register_product_customer_codes.py`
- 业务工作簿：`missing_products/build_mainline_report.mjs`
- 配套物料只读调查：`missing_products/investigate_supporting_customer_codes.py`
