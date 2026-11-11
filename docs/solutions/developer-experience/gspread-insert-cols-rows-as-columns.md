---
okf: v0.1
type: Reference
title: gspread 的 insert_cols 把「行」当「列」——一次差 252 列的抢救
date: 2026-10-15
category: developer-experience
module: tongtool_order_cost
problem_type: developer_experience
component: tooling
severity: high
applies_when:
  - "要给 Google Sheet 插一列/一行（gspread）"
  - "插错了列/行，把表搞乱，想复原"
tags: [gspread, gsheet, api, pitfall, recovery]
---

# gspread `insert_cols` 把「行」当「列」

## Context

往共享 gsheet 的一张表里、在 `通途SKU` 右边插一列 `产品名称`。
直觉是"传一列数据"，于是构造了 **252 个各含 1 个元素的行** 传进去。

## Problem

`ws.insert_cols(values, col=3)` **每个内层 list 是"一列"，不是"一行"**。
传 252 个 1 元素 list → **插了 252 列**，整表被右推 252 列（36 列 → 289 列）。

更坑的是：`insert_cols` **没有 `row` 参数**（本版签名只有 `col` / `value_input_option` /
`inherit_from_before`），想从第 46 行开始填，只能**前面补 45 个空列**。

## Solution

1. **正确写法**：一列 = **一个内层 list**，行数用空格补齐到目标行。
   ```python
   col = [[""] * 45 + ["产品名称"] + names]     # 一个内层 list
   ws.insert_cols(col, col=3)
   ```
2. **抢救（本次实测可行）**：Google Sheets 插列是**整表位移**，数据没丢，只是右移。
   ```python
   ws.delete_columns(start_index=3, end_index=254)   # 删掉误插的 252 列 → 原位移回
   ```
   删完先 `get_all_values()` 逐行核对表头与首末行，再做正确插入。
3. 插完复核：`ws.get_all_values()` 看目标行表头 + `ws.col_count`。
   另注意 `add_cols()` 若先调用过，会多出一列空列，记得删。

## Why This Works

Sheets 的 insert/delete column 都是**服务端整表位移**，单元格内容与**格式一起移动**
（用户手涂的颜色会跟着走），所以"插错→反向删掉"是**无损可逆**的。

## Prevention

- 用 gspread 的 `insert_*` 前，先 `inspect.signature()` 或读一行文档，**别凭直觉**。
- 对**共享的、有人在上面手工标注**的表：改动前先 `get_all_values()` 取快照，
  改完立刻回读核对；涉及格式的先确认"位移是否保格式"。
- 一次性、破坏性风险高的写，**先在一个临时表上试**。

## Related

- [审核派生成本的独立验证法](../best-practices/auditing-derived-costs-independent-verification.md)
  —— 这次插列就是在给"规则核验表"加列时发生的
