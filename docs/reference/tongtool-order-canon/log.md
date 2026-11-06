---
okf: v0.1
type: Log
title: 通途订单规则库（canon）变更日志
---
# 变更日志

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
