---
okf: v0.1
type: Index
title: dingtalk_sheet — 钉钉表格读取
tags: [dingtalk, sheet, workbook, alidocs, readonly]
---

# dingtalk_sheet

读钉钉表格（workbook）文档内容的只读模块。与同目录 `dingtalk_robot`（群机器人 webhook）
用途不同：那个是**发消息**，这个是**读文档**。

| 标题 | 文件 |
|------|------|
| 钉钉表格 API 与两张供应链表结构 | [reference/dingtalk-sheet-api.md](reference/dingtalk-sheet-api.md) |
| reference 索引 | [reference/index.md](reference/index.md) |
| 变更日志 | [log.md](log.md) |

## 快速开始

```bash
# 列出文档所有 sheet
uv run python dingtalk/dingtalk_sheet/read_table.py \
    --url "https://alidocs.dingtalk.com/i/nodes/<baseId>" \
    --operator-env DINGTALK_OPERATOR_ID --list

# 读一张表
uv run python dingtalk/dingtalk_sheet/read_table.py \
    --url "https://alidocs.dingtalk.com/i/nodes/<baseId>" \
    --sheet "2026年度订单明细" --range A1:P2000 \
    --operator-env DINGTALK_OPERATOR_ORDER -o EN_API/out/订单明细.xlsx
```

## 代码地图

| 文件 | 作用 |
|------|------|
| `client.py` | accessToken、`parse_base_id`、`list_sheets`、`read_range`、`sheet_id_by_name` |
| `read_table.py` | CLI（列 sheet / 读区域 / 按列精确匹配 / 导出 xlsx） |
| `tests/test_client.py` | 离线单测（不连钉钉） |

## 边界

- **只读**：不写、不改任何钉钉文档。
- **operatorId 是个人信息**：unionId 只放本机 `.env`，任何情况下不进仓库。
- 文档接口对**每个文档**校验 operator 权限，不同文档可能要用**不同人**的 unionId。

## Related

- `dingtalk/dingtalk_robot/` — 钉钉自定义机器人（发消息 / 文件卡片）
- `EN_API/item_shipment_status.py` — EN 侧发货状态；本模块是它的头程补充数据源
- `docs/solutions/architecture-patterns/en-end-to-end-supply-chain-fulfillment-visibility.md`
