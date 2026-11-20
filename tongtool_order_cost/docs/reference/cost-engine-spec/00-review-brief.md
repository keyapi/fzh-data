---
okf: v0.1
type: Reference
title: 评审任务书 · 请独立核验「成本引擎」bundle（给其它 Agent / 其它对话）
description: 把本 bundle 交给另一个 Agent（Codex / Cursor / 另一个 Claude 对话）做独立核验时的任务书：待证伪的断言清单、证据要求、输出格式、已知易错点、禁止事项
date: 2026-10-15
module: tongtool_order_cost
tags: [cost, review, audit, brief, verification]
---

# 评审任务书 · 请独立核验本 bundle

> **用法**：把本文件的**路径**给评审方（Codex / Cursor / 另一个 Claude 对话），并附一句「按 `00-review-brief.md` 执行」。
> 目的：让**不是写它的人**来证伪，而不是复述。

## ⚠️ 第一轮复核（Codex，2026-10-16）已完成 —— 先读这条

第一轮的结果与**全部更正**在 [**13-codex-review-corrections.md**](13-codex-review-corrections.md)（**与其它页冲突时以它为准**）。
第一轮抓到并已修正的错误（**不要重复报，但可复核我们改对了没有**）：

| 第一轮指出 | 现状 |
|---|---|
| 新表公式 `VLOOKUP(wt, importBOMCostList!$A:$Y, 21)` **搜错列**（A 是产品编号，wt 在 Y） | 已改为 `INDEX($U:$U, MATCH(wt,$Y:$Y,0))`；见 [11](11-plan-new-ustx-processing-table.md) §3.2 |
| **「改来源码无影响」是错误归因**（cell125 会按来源码重取） | 已更正；该结论**只对头程成立**；见 [13](13-codex-review-corrections.md) §4 |
| **第 15 条真问题是幂等**，不是「表单缺 PP棉 闸门」（三个入口都有） | A6 **作废**、A5 改述为幂等；见 [09](09-known-issues-register.md) §A |
| 「51 行 / B 组 10 键」**分类太粗** | 已改 Codex 的 4 类分法（白名单 3 / 源映射空 41 / 五件套 4 / 双模板冲突 3）；见 [11](11-plan-new-ustx-processing-table.md) §3.3、[15](15-exception-rows-monthly-impact.md) |
| `colab-engine-cell-by-cell.md` **漏 cell049**、**cell045/096 写反**、`eval_delivery_en` 现状过期、`idxmax` 无消费者 | 已**就地返工**；见该文件头部警示与 [13](13-codex-review-corrections.md) §6 |
| 时点：**四种状态不能混用** | [01](01-overview-and-glossary.md) §4 已改为五段时点表 |
| 18 条方抱枕是**历史成本代理**（非 parser 拼错） | 已记；见 [13](13-codex-review-corrections.md) §5.2 |

**格式要求不变**：逐条给「已证实 / 证伪 / 未证实 + 证据（路径:行号 或 SQL 或数据）」，证伪给最小反例；**不要以 bundle 自身表述当证据**。

---

## 0. 一句话任务

独立核验 `tongtool_order_cost/docs/reference/cost-engine-spec/`（下称 **bundle**）里的结论——
**能用一手证据（EN 代码 / SQL / 原始数据）证实的，标「已证实」；证伪的，给出反例；无法判定的，标「未证实」。**
**不要以 bundle 自身的表述作为证据。**

## 1. 材料与访问

- **被评对象**：`tongtool_order_cost/docs/reference/cost-engine-spec/`（入口 `index.md`）；相邻专项文档在同目录 `../`。
- **一手来源**（必须用这些，而不是二手转述）：
  - EN 生产库：`ssh 阿里云-FZH-ERPNext-frappe`（用户 frappe，bench 根 `/home/frappe/frappe-bench`）；只读 SQL
    `cd /home/frappe/frappe-bench && bench --site erpnext.vilavi.cn mariadb --execute "SELECT ..."`。
  - **2026-09-03 数据快照**（冻结副本，可离线核对）：
    `tongtool_order_cost/out/profitability_audit/2026年7月订单_ustx2/`
    （`en_bom_cost/EN产品BOM成本列表20260202.csv`、`writeback/写回2026年7月订单.csv`、`shell_cost_import_values/import皮壳成本.csv`、`sx_processing_values/绍兴二次加工成本.csv` 等）。
  - Colab notebook 备份：`C:\Users\zhang\.claude\backups\colab\1T5hZYvnJhS8xzORb3tuYRoXXWn9uSzNl_20261010_163404.ipynb`
    （或 `uv run python colab_kit/colab_kit.py fetch <id> --out /tmp/nb.ipynb`）。

## 2. 待**证伪**的断言清单（逐条给结论）

> 每条都要：**结论（证实/证伪/未证实）+ 证据（路径:行号 或 SQL 或数据）+ 若证伪则给反例**。

### A. 口径与公式
1. `美中加工成本, USTX` = `USTXBZCP#` 物料「`is_active=1` 且 `is_default=1`」BOM 的 `total_cost`；无 BOM 回退 `Item.valuation_rate`；`disabled=1` 置 None。
2. `total_cost = raw_material_cost + operating_cost + scrap_material_cost`；**只有 `operating_cost` 随工资率变**。
3. 工资率 167.8 存于 `Workstation` 记录「美中USTX包装」的 `hour_rate_labour`（同记录 `hour_rate_manage=34.24`）。
4. 「按发货方式组合绍兴成本」在 EN 有 **≥3 处**实现且口径不同：报表 `sx_cost_all`（半成品→皮壳+成品成本−剔除，**不加半成品**）／订单同步 `sx_shipping_cost`（半成品→皮壳+半成品成本）／`pllc_cover`。
5. `绍兴总成本`（报表列）= `皮壳成本 + 绍兴包装成品成本`，**不是**「皮壳+半成品+成品」三段相加。
6. **剔除额**（Jack，2026-10-10）：= `半成品 BOM 的 operating_cost + 其「包装箱/包装袋」子树物料 amount`，×「成品 BOM 引用半成品整件那行的 qty」；
   **只影响** 报表 `绍兴包装成品成本`/`绍兴总成本`/`发成品尾程前成本` 与 订单同步 `cost_sxbzcp`/`sx_cost_all`/**FBA 仓 `sx_shipping_cost`**；
   **不影响** 非 FBA 的 `sx_shipping_cost`、皮壳成本、绍兴包装半成品成本、加工成本三列、头程。
7. **FBA 的国外加工成本 = 0**（`Tongtu Shipping Warehouse` 里 FBA 各行 `processing_cost_name` 为空）；海外仓复用「美中加工成本 USTX」。

### B. 数据与覆盖率
8. `绍兴二次加工成本` ws 覆盖 7 月**美中订单全部 177 个键（100%）**；`import皮壳成本` 同样 177/177。
9. 现有原型 `测算 美中USTX二次加工成本`（615 键）**只覆盖美中 100/177（56.5%）**。
10. 7 月美中键里：**166 可解析**（其中 **42 个 EN 值为字面 0**）、**10 个键拿不到重量模板**（清单见 [11](11-plan-new-ustx-processing-table.md) §3.3）、**1 个 wt 不在 EN BOM 表**。
11. 7 月美中 4379 行：**A 与「按绍兴发货方式取 EN 头程」逐行相等（Δ 恰好 0）**；`head_src` 非空 4328 行。
12. 7 月 USTX 行：`绍兴二次加工成本` **非 0 行数 = 0**（非空的是 PL 180 行 + USNJ 22 行）。
13. 7 月美中四方对比：A 526,225 / B1 752,854 / B2 791,137 / B3 717,678（￥加权，按 `发货数量`）。

### C. 结构性问题
14. `import皮壳成本` 的列名「绍兴/美国/波兰**二次加工成本**」实际装的是各地**包装成品成本**；绍兴列与 `importBOMCostList.绍兴包装成品成本` 在 4328/4331 行相同。
15. **BOM 复制缺幂等**：`check_bom_exists`（`utils/bom.py:127–145`）只查 `docstatus=0`，而 `:290–299` 插入后立即 `submit()`；三个入口（表单/自动/批量）**都有** PP棉 资格检查。
16. **2026-09-03 快照尚未含剔除额**（与 Jack 10-10 提交时序一致）。

### D. 第二轮新增断言（2026-10-16 之后新增/返工的内容，**重点核验**）

17. **主键推导链**（[14](14-colab-key-derivation-chain.md)）：
    - `品类编码` 来自 GS `品类使用面料`（每行「品类 → 品类编码 + 面料清单 + 品类别名」），且编码**须唯一**并 = `产品用料工时明细.品类尺寸编码` 的前 2 段；
    - **面料**来自 GS `材料价格明细`（**仅 `材料类别=='面料'`**），取 `材料编码`，拼键时去掉 `ML-`；
    - **尺寸**有两条路径：4.2（`cell_066`，从产品名称解析、默认取最大、带特例）与 4.7.2（`cell_141`）；
    - **海绵三层特例**：品类层（「弧形+海绵→弧形海绵」）· 面料提取层（「海绵」强制排末位）· 物料层（`面料/海绵 → ML-HM`，键尾 `-HM`；填充物 `HM-HX*` 不参与）。
18. **`cell049` 存在且含字面 1:2:4**：`fill_shipping_cost`（L72–129）docstring 写「半成品 = 2×皮壳，成品 = 2×半成品 = 4×皮壳」；`select_by_sx_delivery`（L134–187）是 `绍兴发货方式` 的**真实消费点**；`df_final` 构造于 L211。
    - **仍待判定**：该函数**只更新已存在的发货方式行、不给缺失方式新建行** → 1:2:4 **实际触发面**未证实。
19. **异常行月度影响**（[15](15-exception-rows-monthly-impact.md)）：161 空键命中美中的行数 **7 月 41/4379、8 月 36/5479、9 月 21/2959**；**51 行非 7 月特有**（7/8/9 = 51/48/61）；161 空键本季**仅 17 个**被真正用到；**空键逐月新增**（8 月 +6、9 月真正新增 1 → 累计 +7，**断链在扩大**）。
20. **`colab-engine-cell-by-cell.md` 的返工**：`cell045`=**19 列**、`cell096`=**6 列**；`has_sx_delivery` 分支归 `cell045`；`idxmax` 无面料兜底（`df_cost_2prod_nofabric_nodups`）**无订单侧消费者**（`cell_109` 整格注释）；`eval_delivery_en` 仅**当前 10/14 版** `cell36=True`，10/10 备份无。

## 3. 必查的「易错点」（评审时务必先看）

1. **时点**：`EN产品BOM成本列表20260202` 是 **2026-09-03** 导出（名字里的日期是旧的）；EN 线上已变。**跨时点对比必错**。
2. **命名坑**：「国外加工**成品** BOM」是口误 → 实际只有国外**包装**成品；`HEAD-*` 是头程编码不是加工成本。
3. **不要把「平凡成立」当证据**：例如「`绍兴总成本` = 皮壳+半成品+成品」在大量「半成品成本=0」的行上会**假命中**——必须**只在相关行非 0 的子集里**验证。

## 4. 输出格式（必须照此给）

```markdown
## 结论总览
- 已证实 N 条 / 证伪 M 条 / 未证实 K 条

## 逐条核验
### [编号+简短标题]
- 结论：已证实 / 证伪 / 未证实
- 证据：<路径:行号 | SQL | 数据文件:行>
- （若证伪）反例：<最小复现>

## 你认为**未被覆盖**的关键问题
<列出 bundle 漏掉的、你在一手证据里发现的>

## 与 bundle 冲突之处
<逐条列出，并说明谁对>
```

## 5. 禁止事项

- **对 EN 只读**：不得 INSERT/UPDATE/DELETE、不得 migrate/restart/build。
- **不打印凭证**；notebook 里若内嵌私钥，写「(私钥已略)」。
- **不要只看 bundle 就下结论**；也不要因为「文档写得像样」就判通过。
- **不要修改任何现有文件**；评审结论写在**新文件**或回话里。
- 不确定就写「未证实」并说明试过什么——**不要猜**。

## 6. 额外任务（若时间允许）

- 另有一份更早的深挖对话（标题约「排查Colab成本核算笔记本疑似历史问题 btw特殊规则」），其结论沉淀在 `../colab-cost-engine-spec.md`。
  **请把它与 [colab-engine-cell-by-cell.md](colab-engine-cell-by-cell.md) 对照**：前者是否有遗漏、是否有与后者冲突之处。
