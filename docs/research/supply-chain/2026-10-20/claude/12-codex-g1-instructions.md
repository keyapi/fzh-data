---
okf: v0.1
type: Handoff
title: G1 阶段给 Codex 的执行清单（三角靠枕切片）
description: #301 冻结基线、G1 合规模拟样例、08 定向复核；不重做综述、不写生产适配器
date: 2026-10-20
tags: [supply-chain, codex, g1, handoff]
---

# 12 — G1 阶段给 Codex 的执行清单

> 目的：研究阶段收尾，进入契约确认与本地验证。Codex 负责**契约/样例/复核**；
> Claude 负责 **G1 脱敏快照本地回放**。不重写综述、不合并 #301、不写生产。

## 1. 冻结 #301 的共同基线

- 把 #301 **`5708609d`** 记为 G0 基线版本，覆盖：
  - `common-framework.md`
  - `alignment-status.md` §3
  - `semantic-examples.md`（C01–C13）
  - `decisions.md`（D01–D05 / B01–B07）
- 在 #301 增加 `baseline.md`（或等价说明），写明：
  - 以上文件对应 commit `5708609d`；
  - Claude 侧基线标签 `supply-chain-g0-baseline-20261020`（#300 提交 `b23c319a`）；
  - 后续实现引用这两个固定版本，不用“最新分支”。
- **不把 #301 并入 #300**；两个 PR 分别审核合并。

## 2. 补 G1 合规模拟样例（C14–C18）

在现有 C01–C13 基础上，只补三角靠枕切片相关、且能作为负例的样例：

| 编号 | 样例 | 保护的契约 |
|---|---|---|
| C14 | KS0001 三角靠枕 × 1 件 + KS0248 三角靠枕无扣 × 1 件 → family 汇总 2 件；leaf 仍分开 | family 聚合不合并 SKU、不重复计数 |
| C15 | 同一通途订单行同时命中 KS0001/KS0248 → `ambiguous`，拒绝自动归并 | 歧义 fail-closed |
| C16 | 桶预测 100、订单 30 已全部发完 → `consumed=30`、`net=70`、桶总需求 100；部分发/取消/跨桶各一例 | 桶内已发继续冲减，交付不使需求复活 |
| C17 | on_hand 100 已含新收 20 → 不能再加 received 20；采购/头程两源冲突 → 异常，不相加/取 max | 同 cutoff 互斥余额 |
| C18 | 收货 R1 修订 70→69+1 坏；R2 30；同一 revision 重播拒绝；R1 分摊到两个 DN 行 | revision 替换不累计、收货分摊 |

要求：

- 每个样例给出**可复算预期**与负例（拒绝/异常），不要只写说明。
- 用 `uv run --no-project python contract_examples.py` 实跑，输出 PASS/FAIL 与总数。
- 只证明算例自洽；不得写成“真实数据已验证”。

## 3. 定向复核 Claude 08（只看 §2.1/§2.3/§2.4）

- 对照 `alignment-status.md` §3，逐条记录：接受 / 部分接受 / 不接受 + 依据。
- 重点：
  1. 新收是否与 `on_hand_available` 重复；
  2. 采购/头程在途是否只保留一个 crosswalk 余额；
  3. WIP 是否只含未完成部分；
  4. accepted 是否明确不等于 available；
  5. 桶内已发订单是否用 `consumed_order_qty` 而不是 `open_order_qty` 冲减。
- 不重开总体架构、不重做 02/03/04 文献综述。

## 4. 三角靠枕 G1 切片输入说明（只做映射说明，不取数）

- **数据来源默认用现有数据**：GSheet `通途订单YYYYMM`（PR #304 服务账号直读 43 个月）
  + 本地 `D:/Work/王忠于/成本核算/2026年{4..9}月订单_order_cost_*.xlsx`；业务导出只作兜底。
- **映射优先级**：**P1 EN `Tongtool Order` 明细的客户物料号** →
  **P2 `Item Customer Detail.ref_code`（可复用 PR #303 `EN_API/query_customer_items_suffix.py`）/ `importBOMCostList.客户物料号`** →
  **P3 Colab 4.2 派生物（仅缺失兜底，标 `fallback=true`）**。
  现有记录见 `13-g1-data-sources.md` §1.3；不要重复造映射。
- EN：叶子物料组 `KS0001 三角靠枕`、`KS0248 三角靠枕无扣`；保留 leaf group/SKU。
- 通途 GSheet：`品类orig` 多为「自产-三角靠枕-*」；`品类/品类统一名` 是 Colab 4.2 派生物，
  **可能不一致，不能当主键**；以完整通途SKU/客户码精确匹配为准。
- 列出预计的未匹配/歧义类别：后缀（`-Cover/-Foam`）、无扣 vs 有扣、组合/套件、历史改名、
  同时命中 KS0001/KS0248。
- 仓与窗口：**两仓（美中-FZH-DANEEY + 美东-CENTRADE）× 2026-04..09（G1 6 个月）**；
  G2/G3 另用 2023-01..2026-07（43 个月）。
- **不访问生产、不导出真实明细**；只写映射规则与预期异常。

## 5. 交付与边界

- 在 #301 增加：`baseline.md`、`g1-slice.md`、更新 `semantic-examples.md`/`contract_examples.py`、`review-08-g0.md`。
- 不修改 Claude 文件；不合并 #301 到 #300；不写生产适配器。
- 完成后由 Claude 用同一批样例跑 G1 本地回放，双方再交叉审核实际实现。

## 6. 可直接复制的提示词

```text
研究阶段收尾，进入 G1 契约确认。请只做以下四件事，不重做综述、不写生产适配器：

1. 把 #301 的 5708609d 记为 G0 基线（common-framework / alignment-status §3 /
   semantic-examples C01–C13 / decisions D01–D05、B01–B07），新增 baseline.md，
   引用 Claude #300 的标签 supply-chain-g0-baseline-20261020（提交 b23c319a）。
2. 补 C14–C18 五个三角靠枕切片的合成样例（family 映射、歧义拒绝、桶内已发冲减、
   互斥供应余额、收货 revision/分摊），实跑并报告 PASS/FAIL。
3. 只复核 Claude 08 的 §2.1/§2.3/§2.4，逐条记录接受/部分接受/不接受及依据。
4. 写 g1-slice.md：KS0001/KS0248、通途「三角」、两仓（DANEEY + CENTRADE）、
   2026-04..09 的映射规则与预计未匹配/歧义；不取真实数据、不访问生产。

边界：不修改 Claude 文件；不合并 #301 到 #300；不写生产适配器。
```
