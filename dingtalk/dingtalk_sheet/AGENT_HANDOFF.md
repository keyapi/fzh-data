# dingtalk_sheet — Agent Handoff

> **模块**: `dingtalk/dingtalk_sheet/`
> **能力**: 只读钉钉表格（workbook）文档 —— 列 sheet、读区域、按列精确匹配、导出 xlsx
> **回答的问题**: 头程数据在哪、怎么机器读到

## 快速操作

```bash
ENV="D:/Work/赛狐/Cursor/.env"      # worktree 里没有 .env，指到主仓库

# 列出文档所有 sheet
uv run python dingtalk/dingtalk_sheet/read_table.py \
    --url "https://alidocs.dingtalk.com/i/nodes/<baseId>" \
    --operator-env DINGTALK_OPERATOR_ID --list --env-file "$ENV"

# 读一张表（整表，推荐 —— 自动分块并剔除补齐空行）
uv run python dingtalk/dingtalk_sheet/read_table.py \
    --url "https://alidocs.dingtalk.com/i/nodes/<baseId>" \
    --sheet "2026年度订单明细" --all \
    --operator-env DINGTALK_OPERATOR_ORDER --out EN_API/out/订单明细.xlsx --env-file "$ENV"

# 读指定区域（会包含尾部补齐空行，谨慎用于数行数）
uv run python dingtalk/dingtalk_sheet/read_table.py \
    --url "https://alidocs.dingtalk.com/i/nodes/<baseId>" \
    --sheet "2026年度订单明细" --range A1:P500 \
    --operator-env DINGTALK_OPERATOR_ORDER --env-file "$ENV"

# 在某列里精确匹配（找 SO / 批次号）—— 配合 --all 才可靠
uv run python dingtalk/dingtalk_sheet/read_table.py \
    --url "https://alidocs.dingtalk.com/i/nodes/<baseId>" \
    --sheet "2026年度订单明细" --all \
    --operator-env DINGTALK_OPERATOR_ORDER --find-col B --find SO-26-00101 --env-file "$ENV"
```

## 凭证与身份（两个都要）

| 名称 | 放哪 | 说明 |
|------|------|------|
| `DINGTALK_CLIENT_ID` / `DINGTALK_CLIENT_SECRET` | 本机 `.env` | 企业内部应用的 Client ID / Secret |
| `DINGTALK_OPERATOR_ORDER` / `DINGTALK_OPERATOR_SHIP` | 本机 `.env` | **各文档自己的 unionId**，见下 |

**operatorId 必须是操作人的 unionId，且该人要对本文档有权限。**
实测两张供应链表要分属两位同事的 unionId 才能都读到 —— 换文档就要确认权限，
不是配一次终身通用。（同一**个人**的 unionId 跨应用不变，可复用。）

unionId 属个人信息：**只放本机 `.env`，永不提交**。

## 核心 API（实测）

```text
POST /v1.0/oauth2/accessToken                              → accessToken
GET  /v1.0/doc/workbooks/{baseId}/sheets?operatorId=       → 列 sheet
GET  /v1.0/doc/workbooks/{baseId}/sheets/{sid}/ranges/{A1:Z100}?operatorId=  → displayValues
```

- `baseId` 就是 alidocs 链接里 `/nodes/` 后面那段。
- **不要走 `notable`**：`/v1.0/notable/bases/{id}` 只适用 AI 表格（多维表）；
  对普通表格返回 400「document type」类错误。
- 范围里的冒号要 URL 编码成 `%3A`。

## 三个实测陷阱（都会让人给出错误结论）

1. **接口会用空行把请求区域补满** —— 读超出数据的区域会稳定返回满额空行，不是空列表。
   所以「返回行数 < 请求行数 就停」的翻页条件**永远不触发**。
   **曾据此误报某表有 40000 行，实际只有 380 行。**
   → 用 `--all`（内部按「整块全空才停」翻页），不要自己循环 `--range` 数行数。
2. **单次 range ≤ 30000 单元格** —— `A1:P2000`（32000）会报
   `400 ... at most 30000 cells`。`chunk_rows_for(n_cols)` 按列数算安全行数。
3. **会偶发 503** —— 长扫描中途遇到 `503 ServiceUnavailable` 要退避重试，
   不要当致命错误。`http_json` 已内置（5xx/网络重试 3 次；4xx 不重试）。

**全部 sheet 合计只有约 3500 行**（最大一张 1090 行），整表读很快。

## 错误码对照

| 现象 | 说明 |
|------|------|
| `400 MissingoperatorId` | 没带 operatorId |
| `400 paramError-operatorId` | 带了但不是 unionId（appKey/AgentId/userId 都不行） |
| `403 forbidden.accessDenied` | unionId 合法但**没这个文档的权限** → 换人 |
| `400 ... baseId is incorrect ... document type` | 用错 API（拿 notable 读普通表格） |
| `404 InvalidAction.NotFound` | 路径不存在 |

## 供应链两张表（详见 reference）

| 文档 | 链接（整条传给 `--url`） | 关键 sheet |
|------|--------------------------|------------|
| 2026年下单表 | `https://alidocs.dingtalk.com/i/nodes/QOG9lyrgJPjjrl10uXDDw7RwWzN67Mw4` | `物流信息表`（通途采购单号→`ZMT…`物流号）、`2026年度订单明细` |
| 发货信息总表 | `https://alidocs.dingtalk.com/i/nodes/qXomz1wAyjKVXd1x2xoxV3Y9pRBx5OrE` | `物流跟踪Tracking`（**批次号 + 离港/到港/入库**）、美东/美中/欧洲/FBA 下单表与发货明细 |

> baseId 由链接 `/nodes/` 后那段自动解析，**不用手抠**。
> 表会改名、加 sheet、换文档，所以脚本里**不要硬编码 baseId** —— 用 `--url` 传。

字段级结构、错误码、外部调研来源与探测方法：
`docs/reference/dingtalk-sheet-api.md`。

## 关键口径

1. **`2026年度订单明细` 一行 = (EN销售订单编号 × 通途SKU)**，不是一单一行。
   同一张 SO 会有几十行。
2. **join key 是 `EN销售订单编号`**（= `Sales Order.name`）。
   **不是** EN 的 `po_no`（那是离职同事自编的内部流转号，见下）。
3. **工厂四件套**：`工厂确认交期` → `包装完成日期` → `实际包装完成量` → `物流发票编号`。
   逐级为空 = 生产完成但还没进头程。这四列是「为什么还没发」的直接证据。
4. **批次号是头程主键**：`NJHY…`(美东) / `TXHY…`(美中) / `PL…`(波兰) / `LEFBAUK…`(FBA)。
   在「下单表」里**只写在批次首行**，后续行留空 —— 读出来要向下填充。
5. **离港 / 到港 / 入库**是实际事件日期，是「多久能上架」最硬的证据；
   没有它们时不能拿「下单 + N 月」当事实。
6. 「美东发货明细」有「美国签收日期 / 美国到货数量」两列（国外仓签收事实），
   美中那张**没有** —— 不同分公司的登记完整度不一样，别默认通用。

## 与 EN 的关系（这是 V2 的方向）

```
EN Sales Order ──(SO编号)──► 2026年度订单明细 ──► 工厂四件套（是否已进头程）
                                        │
                                  目的仓库 + 下单量
                                        ▼
                             发货信息总表 / 物流跟踪Tracking
                             批次号 → 离港/到港/入库 → 时效
```

EN 侧只到「工厂出库」；本模块补「工厂出库之后」。两边用 **SO 编号**接。
参考蓝图 §5 数据来源矩阵与 §6 头程数据模型。

## 已知限制

- 只读；不写入、不修改文档。
- 区域靠 `--range`，需要预估行数；没有「自动取整张已用区域」的便捷接口
  （`GET .../sheets/{sid}` 单表元信息实测要 operatorId，暂未用）。
- 读的是**单元格显示值**（`displayValues`），日期/金额都是格式化后的字符串，
  要自己解析（如 `2026/8/30`、`¥34,790.00`）。
- 批次号/日期等存在**合并单元格**（只写首行），解析时必须向下填充。
