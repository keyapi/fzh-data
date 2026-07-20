---
okf: v0.1
type: Reference
title: 蜴国际 P0 样例放置路径
description: 同事提供的 Excel/PDF 原始样例应放的本地路径（不入 Git）与当前开发分支
timestamp: 2026-07-17
---

# 蜴国际 P0 样例放置路径

## 当前 Agent 工作位置

| 项 | 值 |
|----|-----|
| 工作区 | `D:\Work\赛狐\Cursor`（主目录，**不是** `.claude/worktrees/...`） |
| 分支 | `feature/sellfox-shipping-p1a-rest` |

## 请把 4 个文件放到这里

```
D:\Work\赛狐\Cursor\sellfox_shipping\数据源\蜥蜴国际-p0-样例\
```

建议命名（也可保留原名，只要在该文件夹内）：

| # | 内容 | 建议文件名 |
|---|------|------------|
| 1 | 赛狐订单导出（按包裹样式；是否真「按包裹」待确认） | `01-sellfox-export-by-package.xlsx` |
| 2 | 上传到蜴国际的 Excel | `02-lizard-upload.xlsx` |
| 3 | 蜴国际返回追踪号 Excel | `03-lizard-tracking-return.xlsx` |
| 4 | 7.15 蜴国际面单 PDF | `04-lizard-labels-2026-07-15.pdf` |

该目录被 `.gitignore` 忽略（含地址/电话等 PII，**不要 commit**）。

## 与 API 的关系

- 主路径：赛狐 API `packages-sync` 拉包裹。
- ① 赛狐导出 Excel：API 失效时的**兜底** + 与 API 字段对照，仍请提供。
- ②③：P1B Excel 闭环硬前置。
- ④：P2 PDF；P1B 可先不做。

放好后回复：「样例已放到 蜥蜴国际-p0-样例」，即可开始 P0 列分析。

## 状态（2026-07-17）

- 四文件已到位（前缀 + 原名）；列分析见 [lizard-p0-column-mapping-2026-07-17.md](../research/lizard-p0-column-mapping-2026-07-17.md)。
- ① 目前只有表头 `包裹号`，需重导有数据的赛狐按包裹导出。
- ② 实际为 `.xls`（非 xlsx）；④ 文件名带额外前缀 `4 `，不影响使用。
