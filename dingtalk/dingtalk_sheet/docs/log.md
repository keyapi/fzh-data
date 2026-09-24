---
okf: v0.1
type: Log
title: dingtalk_sheet — 变更日志
tags: [dingtalk, sheet, log]
---

# 变更日志

## 2026-09-15
- **新增**: `README.md` —— 人读入口（模块定位、两张供应链表、快速命令、限制）。
- **新增**: 模块 `dingtalk/dingtalk_sheet/`（`client.py` + `read_table.py` + 8 条离线单测）。
- **背景**: 计划物流同事指出 EN 的 `po_no` 不是客户 PO 号，真实头程数据在钉钉表格里，
  要求先把两张表读出来。由此定位出钉钉**表格文档**（workbook）只读接口。
- **实测**: 两个文档的 baseId 就藏在 alidocs 链接的 `/nodes/<baseId>` 里；
  文档接口必须带 `operatorId`（**操作人 unionId**）且该人须对本文档有访问权限 ——
  实测两张表要分别用两位同事的 unionId 才能都读到（无权限时 403 `forbidden.accessDenied`）。
- **反例**: `/v1.0/notable/bases/{id}/...` 对普通表格返回 400「baseId is incorrect,
  please check the document type」；notable 只适用 AI 表格（.多维表）。
- **修正（同日，重要）**: **接口会用空行把请求区域补满** —— 读超出数据的区域会稳定返回
  满额空行而非空列表。原先「返回行数 < 请求块行数 就停」的翻页条件永不触发，
  因此一度误报「某表有 40000 行」，实际只有 380 行。新增 `read_sheet_all()`
  （按「整块全空才停」翻页 + 只裁末尾补齐空行）与 CLI `--all`；实测各表真实规模
  合计约 3500 行（最大 1090 行）。
- **加固（同日）**: `http_json` 对 **5xx 与网络异常退避重试**（4xx 不重试）——
  实测整表扫描中途会偶发 `503 ServiceUnavailable`。另发现单次 range 上限为
  **30000 单元格**（`A1:P2000` 会报 400），新增 `chunk_rows_for()` / `col_letter()`。
  单测 8 → 19 条，全绿。
- **产出**: 读通「2026年下单表」15 张 sheet 与「发货信息总表」9 张 sheet，
  表结构记入 `docs/reference/dingtalk-sheet-api.md`。
- **补齐（同日）**: 记录两张表的**完整链接与 baseId**、**外部调研来源**（钉钉官方
  notable ListRecords / AI 表格 OpenAPI 文档 / 第三方 api-reference），
  并写明一个重要事实：**这些资料只覆盖 `notable`（AI 表格）**，
  而本次是普通表格，走通的 `doc/workbooks` 端点来自**逐端点探测**而非查资料；
  探测方法（按状态码语义区分「接口不存在 / 参数不对 / 缺权限」）也已记录。
