---
okf: v0.1
type: Spec
title: 渠道账号表同步到 EN 的规则
timestamp: 2026-08-25
---
# 渠道账号表同步到 EN 的规则

1. Sheet 是运营事实源。对账后只追加，不删历史 Owner。
2. Owner 行：对每月 `运营人员YYYYMM` 取有效值，**连续同人折叠成一段** `from_date=YYYY-MM-01`。已有账号只插入「晚于 EN 最新 from_date 且人名变了」的段。
3. 有效值：`待分配` / `待定` 原样写。开卖前空/`样品`/`null` 跳过；开卖后空月写成 `待分配`。`荆春雨&张振朋` 整串当一个人名。
4. 新建账号时第一段 role=`Operator`，之后切变 `Primary Owner`。追加切变一律 `Primary Owner`。
5. 别名：Sheet 别名 ∪ canonical name；`Illiosenergy` 行还要把 sheet 名挂到 `ILLIOSPL`。旧 EUR 账号名只挂在 `AMZFZHSXDE`。
6. 新建 Sales Channel 仅当 Sheet 渠道在 EN 不存在。Kaufland 区域按需补 `AT,IT,FR`，**不要**给 Amazon 加 EUR。
7. 跳过 sheet `渠道账号=null`。
8. 默认 dry-run；`--apply` 须用户确认。报告：总行 / 新建 / 别名 / 负责人 / 跳过原因。
