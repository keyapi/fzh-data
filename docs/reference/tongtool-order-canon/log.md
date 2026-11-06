---
okf: v0.1
type: Log
title: 通途订单规则库（canon）变更日志
---
# 变更日志

## 2026-11-06（裁决更新）

- **C9 关闭（退货）**：用户口径——通途订单不含退货，正常发货都算销售额，退货只在钉钉账期；“退货产品仓”只是发货仓。数据：202608/202609 负数数量 0 行。`UNIV-004` 改 canon，01 §6 重写。
- **C14 关闭（负成本）**：无业务场景，按数据错误处理（本地阻断暴露，不 clamp）；1.7.0 的负数规则只针对 FBA 尾程参考值，不适用于四列成本。数据：两月四列负值 0 行。`PRICE-008` 改 canon。
- **C2 裁决（ADR-0001）**：本地 38 矩阵为唯一应然口径；OS/CR 对齐，DN/DNF 只读复用；迁移顺序 OS 先修、双跑切换。新增 `adr/0001-cost-authority-and-migration.md`。
- `rules.yaml`：decision-needed 清零（23 条：canon + unverified）。

## 2026-11-06（C3 裁决 + Codex 完整复审）

- **C3 裁决（并入 ADR-0001）**：FBA 唯一判据 = `Tongtu Shipping Warehouse.warehouse_classification`；客户名/order_type 降为兼容告警；`needs_last_leg` 不是身份；未知映射阻断。新增 `FBA-001` resolver 规则，`UNIV-003`、01 §5、07 C3 同步。
- **Codex 复审 must-fix 已修**：
  - index 权威顺序改为「ADR > 规范 > 冲突 > 实现 > 证据」；
  - 07 状态值统一到枚举（open/in-progress/decision-needed/decided/verified/resolved/closed/blocked），closed 可无截止日；
  - 03 后缀矩阵标注「仅单独卖单品；拆单组内组件行成本 0」；
  - rules.yaml 证据统一加 `[SPEC]/[EN现状]/[LOCAL实现]/[DATA]` 标签；
  - 旧页横幅经复核确实存在（Codex 误看了另一个 worktree）。
- rules.yaml 增至 23 条（21 canon + 1 unverified + 1 FBA resolver canon）。

## 2026-11-06

### MVP 规范落地（canon v0.1）

- **新建 `01-order-universe.md`**：三个来源与权威顺序；未拆单即原始订单；拆单证据；`invalid=1` 只作锚；FBA 分账；退货/补发/取消现状；守恒约束。
- **新建 `02-grouping-and-merge.md`**：拆单/拆包裹识别；合并与不合并条件；件数取谁；共享皮壳→填充行定产品、共享填充物→皮壳定产品；单独卖 `-Cover/-Foam/-PPCotton` 不是产品歧义；不重不漏断言。
- **新建 `03-price-matrix.md`**：非 FBA 后缀 × 发货方式矩阵；四目的地加工/头程来源；FBA 绕过后缀；合并组不套后缀；单位成本与数量口径。
- **新建 `rules.yaml`**：22 条 MVP 规则；`status` 仅 canon / decision-needed / unverified；每条均有 evidence。
- **新建 `07-conflicts.md`**：15 条冲突逐条落表（owner/截止日/影响/下一动作/状态），另列 1 条边界观察（`-FOAM` + 皮壳档）。
- **更新 `index.md`**：阅读路径改为 01→02→03，再按需 04–07；标注 04/05/06 未建。

### 证据补强（生产库只读元数据）

- `tabTongtool Order Item.warehouse_name` **不存在**（无列、无同名 Custom Field）；`tabTongtool Cost Review Item.warehouse_name` 存在 → C1 在 DB 层坐实。
- `tabItem.custom_split_package_cost_factor` **不存在**；全库仅 `tabItem Customer Detail.custom_split_package_cost_factor` → C12 字段位置错误坐实。
- 00 的 G1/G2 状态改为「已证实（2026-11-06 DB 只读）」。

### 旧页降级

- `cost-engine-spec/01、04、08、30、38` 顶部加一行横幅：保留为证据，规范见本目录。

### 边界

- 本次仍为只读：未改业务代码、未写 GS/EN、未提交 git。

## 2026-11-06（调研）

- **新建本 bundle（调研态）**：四路并行审计旧 Colab+GS、EN 生产源码、本地引擎、文档/PR 决策史。
- **00-audit-report.md**：24 个规则主题三层对照；15 条冲突（严重 3：拆单系数恒 1、后缀五链不一致、FBA 三套判据）；12 项缺口/未证实。
- **01-proposed-structure.md**：建议多文件 OKF bundle + `rules.yaml` + skill 仅指针；给出与 `cost-engine-spec`、`AGENTS.md`、`SKILL.md` 的保留/合并/废弃关系及 6 阶段迁移。
