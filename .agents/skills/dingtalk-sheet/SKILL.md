---
name: dingtalk-sheet
description: 钉钉表格（workbook/alidocs）只读读取 —— 列 sheet、读区域、按列精确匹配、导出 Excel。用于取头程/物流/下单登记表等人工维护数据。触发词: 钉钉表格、钉钉文档、alidocs、智能表格、AI表格、发货信息总表、2026年下单表、批次号、头程、物流跟踪、operatorId、unionId。
---

# 钉钉表格读取

用户提到钉钉表格 / 钉钉文档 / alidocs 链接 / 头程登记表 / 发货信息总表 / 2026年下单表 时加载。

## 前置：两个身份，缺一不可

| 身份 | 放哪 | 说明 |
|------|------|------|
| `DINGTALK_CLIENT_ID` / `DINGTALK_CLIENT_SECRET` | 本机 `.env` | 钉钉企业内部应用 Client ID / Secret |
| `operatorId` = **操作人 unionId** | 本机 `.env`（`DINGTALK_OPERATOR_*`） | **每个文档单独校验权限**，可能要不同人 |

**unionId 属个人信息，只放本机 `.env`，绝不写进仓库或提交。**

缺 operatorId 或权限不对会分别报 `400 MissingoperatorId` / `403 forbidden.accessDenied`。

## 用法

```bash
ENV="<主仓库>/.env"     # worktree 里没有 .env

# 1. 先列 sheet，确认目标表名
uv run python dingtalk/dingtalk_sheet/read_table.py \
    --url "<alidocs 链接>" --operator-env DINGTALK_OPERATOR_ID --list --env-file "$ENV"

# 2. 读区域（先小范围看表头，再放大）
uv run python dingtalk/dingtalk_sheet/read_table.py \
    --url "<alidocs 链接>" --sheet "<sheet 名>" --range A1:P4 \
    --operator-env DINGTALK_OPERATOR_ID --env-file "$ENV"

# 3. 按列精确匹配 + 导出
uv run python dingtalk/dingtalk_sheet/read_table.py \
    --url "<alidocs 链接>" --sheet "<sheet 名>" --range A1:P2000 \
    --operator-env DINGTALK_OPERATOR_ID --find-col B --find SO-26-00101 \
    --out EN_API/out/明细.xlsx --env-file "$ENV"
```

## 四条必知

1. **baseId 就在链接里** —— `https://alidocs.dingtalk.com/i/nodes/<baseId>`，
   直接把整条链接传给 `--url` 即可。
2. **不要走 notable API** —— `/v1.0/notable/bases/...` 只适用 AI 表格（多维表）；
   普通钉钉表格走 `/v1.0/doc/workbooks/...`。用错会报「baseId is incorrect ... document type」。
3. **读整表用 `--all`，不要自己数行数** —— 接口会用**空行把请求区域补满**，
   「返回行数 < 请求行数 就停」的翻页条件永远不触发（曾因此误报某表 4 万行，实际 380 行）。
   `--all` 按「整块全空才停」翻页。单次 range 还有 **30000 单元格**上限。
4. **合并单元格只写首行** —— 批次号这类列读出来要向下填充。

> 会偶发 `503 ServiceUnavailable`（`http_json` 已内置重试）；
> 4xx 是确定性的（权限/参数错），不要重试。

## 供应链两张表（头程数据源）

EN 只到「工厂出库」；出库以后的头程在这两张表里：

- **2026年下单表** → `物流信息表`（通途采购单号 → `ZMT…` 物流号）、
  `2026年度订单明细`（**一行 = EN销售订单编号 × 通途SKU**；含「工厂四件套」）
- **发货信息总表** → `物流跟踪Tracking`（**批次号 + 离港/到港/入库**）、
  美东/美中/欧洲/FBA 的下单表与发货明细

**join key 是 EN 销售订单编号（`Sales Order.name`）**，不是 EN 的 `po_no`
（那个是离职同事自编的内部流转号，非客户 PO，待废弃）。

字段口径、错误码、真实样例见 `dingtalk/dingtalk_sheet/docs/reference/dingtalk-sheet-api.md`
和 `dingtalk/dingtalk_sheet/AGENT_HANDOFF.md`。
