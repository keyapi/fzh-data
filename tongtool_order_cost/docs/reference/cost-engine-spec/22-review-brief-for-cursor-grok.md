---
okf: v0.1
type: Reference
title: 给 Cursor/Grok 的自足评审说明（不依赖 Codex 上下文）
description: 让任何独立审阅者（Cursor Grok / 另一个 Claude 对话）在零上下文下复核「离线证据表 v2」：要审什么、怎么独立复算、输出格式、已审过的历史（避免重复报）
date: 2026-10-16
module: tongtool_order_cost
tags: [cost, review, brief, cursor, grok, evidence-table]
---

# 给 Cursor/Grok 的自足评审说明

> **前提**：你**没有**本项目的任何上下文。**只需读本页 + 下面点名的 4 个文件**即可开工。
> **任务**：独立复核一张「离线证据表」是否**可靠到可以交给业务**。
> **不要**以任何文档的表述当事实证据——**只用一手数据与源码**。

## 0. 背景（30 秒）

ERPNext 生产库（`erpnext.vilavi.cn`）里，物料 `USTXBZCP#...`（美中包装成品）的成本 = 其 active+default BOM 的 `total_cost`；
该值被导出成 Google Sheet「EN产品BOM成本列表20260202」（**2026-09-03 导出**）。
公司要用它替换美中订单现在「借用绍兴包装成品成本」的做法。

**争议点**：美中订单行**怎么找到**对应的 `USTXBZCP#` 物料。有两条候选路径：

| 路径 | 说明 |
|---|---|
| **A 旧路径** | 从订单「产品名称」解析出 `品类尺寸面料编码` → 查 `import皮壳成本` 得 `EN重量模板物料号` → 查重量模板的成本 |
| **B 直连** | 订单 `通途SKU` → EN 的 `客户物料号`（`Item Customer Detail`）→ `importBOMCostList` → 该产品的 USTX 成本 |

**本次要你审的是**：一张 **4379 行的离线证据表**（7 月美中订单），它逐行给出两条路径的取值与「成本来源状态/处置分类」。

## 1. 要审的产物（**唯一评审对象**）

```
D:/Work/赛狐/Cursor/.claude/worktrees/hardcore-cerf-de2df7/tongtool_order_cost/out/ustx_wage_sim/
  offline_evidence_ustx_rows_v2.csv    ← 4379 行，评审对象
  offline_evidence_manifest.json       ← 输入哈希 + 别名规则版本 + 计数
  build_evidence_table_v2.py           ← 生成脚本（只读，可复跑核对）
```
（`out/` 已 gitignore，**不在 git 里**，是本机产物。）

**它有 17 列**，关键 5 列：
- `直连值 / 直连成本来源`（路径 B）
- `旧路径值 / 旧路径成本来源`（路径 A）
- `两路对比` = `same / DIFF / direct_only / old_only / neither`
- `处置分类` = 给业务的工作清单（`auto_ok` / `review_*` / `business_exempt_zero`）
- `候选数 / 候选(产品编号/发货方式/USTX)` = 同一客户码的**全部候选**

**输入（一手）**：
```
…/out/profitability_audit/2026年7月订单_ustx2/
  writeback/写回2026年7月订单.csv              ← 订单侧（4379 美中行）
  bom_cost_import_values/importBOMCostList.csv ← 客户码→产品的成本
  shell_cost_import_values/import皮壳成本.csv   ← 品类尺寸面料编码→重量模板
  en_bom_cost/EN产品BOM成本列表20260202.csv     ← 重量模板→成本
  …/out/ustx_wage_sim/ustx_boms_all.csv        ← USTXBZCP# 的 BOM（判「有无 BOM」）
```
**每条输入的最新 sha256 前缀在 manifest 里**——请先核对，再看结论。

## 2. 必须证伪的断言（逐条给「已证实/证伪/未证实 + 证据」）

1. **行数守恒**：表 4379 行 = 订单里 `发货仓按销售汇总分类=='USTX分公司'` 的行数；**无静默丢行**。
2. **成本来源三分类正确**（这是 T1）：
   - `bom_cost` 当且仅当该 USTX 物料在 `ustx_boms_all.csv` 里 `is_active=1 且 is_default=1`；
   - `fallback_zero` = 无上述 BOM **且**值为 0；`fallback_nonzero` = 无 BOM 且值非 0。
   - **反例检查**：有没有 `bom_cost` 其实没有 BOM 的？有没有把「有 BOM 但值为 0」误判成 `fallback_zero`？
3. **`ambiguous_customer_code` 判定**：当且仅当**同一完整客户码**指向多个产品**且成本不同**时标记，且**不取 max/首值**。
   - **请自己复算**：`importBOMCostList` 里哪些客户码命中多产品多值？是 3 行吗？
4. **`review_alias_pending` 只有 2 行**：规则是「先精确匹配；**仅当无匹配**时才去末尾 `-Cover` 再查，且标 pending」。
   - **反例**：有没有本该精确匹配却被去尾的？
5. **`处置分类` 的优先级正确**：`business_exempt_zero` > `bundle` > `ambiguous` > `alias` > `DIFF` > `direct_only` > `neither` > `zero_source` > `auto_ok`。**请检查有没有分类覆盖/漏判。**
6. **两路对比口径**：`same` 用 |差| < 0.005；`direct_only` = 只有 B 有值；`old_only` = 只有 A 有值。**合计应 = 4379。**

## 3. 已知历史（**别重复报**，但可复核我们改对了没）

前 3 轮已由另一个 Agent（Codex）审过，**已修正**的包括：
- 早期公式 **搜错列**（`VLOOKUP(wt, A:Y, 21)` 搜的是 A 列=产品编号；应为 `INDEX(U:U, MATCH(wt, Y:Y, 0))`）；
- 早期把 23 处差异**统一归因**为「模板取 max 抹平 FOAM/PP」——**错**，应为 `3 客户码歧义 + 3 旧WT歧义 + 17 其余`；
- 早期**比较脚本对客户码取 `max`** → **掩盖了多候选**（自证反例：`TT0031187K0063920-Cover` 同时指向 PP 件 85.75843 与海绵件 0）；**v2 已改为阻断歧义**；
- 早期把「**7 行未命中**」说成尾缀问题——实为 **2 针线扣 + 1 棉包 + 4 五件套**；
- 「**0**」来自**无 BOM 的估值回退**，不等于「BOM 已证明加工费为 0」。

**若你发现上述任一「修正」本身也有问题，请明确指出。**

## 4. 已知**未证实**（不用你解决，但别当成已知）

- **7 月当时的登记状态**：现表可还原「9/3 导出对 7 月订单的重估」，**不能**冒充 7 月当时（反例：五件套客户码 `creation=2026-05-21`，但 Version 显示 `2026-08-11` 才 added）。
- 17 处 DIFF 的**业务最终归属**（需通途商品主档/实物）。
- `fallback_zero` 里哪些是「真 0」哪些是「回退 0」（表已分类，但**业务语义**未定）。

## 5. 输出格式（**必须照此**）

```markdown
## 结论总览
- 表可用 / 表不可用（给业务前必须先修）
- 已证实 N 条 / 证伪 M 条 / 未证实 K 条

## 逐条核验（对应 §2 的 1~6）
### [编号]
- 结论：已证实 / 证伪 / 未证实
- 证据：<文件:行 | 复算命令 | 数字>
- （若证伪）反例：<最小复现>

## 你认为**未被覆盖**的问题
## 与文档冲突之处
```

## 6. 硬性约束

- **对 EN / Google Sheet 只读**；不改任何文件；不写任何表。
- **不打印凭证**。
- **不要**因为文档写得像样就判通过；**不要**以文档表述当证据。
- 不确定就写「未证实」并说明试过什么——**不要猜**。
- 中文 UTF-8。
