---
okf: v0.1
type: Reference
title: 钉钉表格 API 与两张供应链表结构
date: 2026-09-15
last_updated: 2026-09-15
category: reference
module: dingtalk_sheet
tags: [dingtalk, workbook, alidocs, operatorId, unionId, 头程, 物流, 批次号, 供应链]
---

# 钉钉表格 API 与两张供应链表结构

## 1. 为什么读这两张表

EN（ERPNext）只到「工厂出库」为止。工厂出库之后到国外仓签收这一段（头程）**不在 EN 里**，
而在两张钉钉表：计划/物流同事人工维护。要回答「货现在到哪了、什么时候能上架」，
必须接这两张表。

原先以为入口是 EN 的 `po_no`，**实测是错的**（见 §4）。

## 2. API 调用方式（实测 2026-09-15）

### 2.1 两个必填身份

| 身份 | 怎么来 | 注意 |
|------|--------|------|
| `accessToken` | `POST https://api.dingtalk.com/v1.0/oauth2/accessToken`，body `{appKey, appSecret}` | 之后请求带 header `x-acs-dingtalk-access-token` |
| `operatorId` | **操作人的 unionId** | **每个文档单独校验权限**；不同文档可能要不同人的 unionId |

`appKey`/`appSecret` 就是钉钉企业内部应用的 Client ID / Client Secret。
`operatorId` **不能**用 appKey、AgentId 或 userId 代替 —— 实测这三个都返回
`400 paramError-operatorId`。

### 2.2 baseId 就在链接里

```
https://alidocs.dingtalk.com/i/nodes/<baseId>?utm_scene=...
                                  ^^^^^^^^ 这就是 baseId，不需要另找
```

### 2.3 两个端点足够

```text
列 sheet:  GET /v1.0/doc/workbooks/{baseId}/sheets?operatorId={unionId}&maxResults=200
读区域:    GET /v1.0/doc/workbooks/{baseId}/sheets/{sheetId}/ranges/{A1:Z1000}?operatorId={unionId}
```

读区域返回 `displayValues` —— 二维数组，就是单元格文本，`A1:P4` 这种范围直接给行列表。

### 2.4 错误码语义（别混淆）

| 现象 | 含义 |
|------|------|
| `400 MissingoperatorId` | 完全没带 operatorId |
| `400 paramError-operatorId` | 带了，但不是 unionId（appKey/AgentId/userId 都会这样） |
| `403 forbidden.accessDenied` / `The operator has no permission.` | unionId 合法，但该人**没有这个文档**的权限 |
| `400 ... The given baseId is incorrect. Please check the document type.` | 用错 API —— 普通表格不能走 notable |
| `404 InvalidAction.NotFound` | 路径本身不存在（如 `workbooks/{id}` 不带 `/sheets`、`.../values`、`ranges?range=`） |

### 2.5 已排除的端点

- `/v1.0/notable/bases/{baseId}/...` —— notable 是 **AI 表格（.able 多维表）** 的接口。
  对普通钉钉表格返回上文那条 400。**这两个文档都是普通表格，走 `doc/workbooks`。**
- `/v1.0/doc/workbooks/{baseId}`（无 `/sheets`）→ 404。
- `/v1.0/doc/workbooks/{baseId}/sheets/{sid}/values`、`.../ranges?range=`→ 404。
- `/v2.0/wiki/nodes/{id}`、`/v1.0/storage/spaces/{id}` → 403，需要 Wiki.Node.Read /
  Storage.Space.Read，本应用未开通（也不需要）。

> 探测方法值得复用：拿 accessToken 后，对同一 baseId 批量打一组候选路径，
> **只看状态码语义** —— 404 = 路径不存在；400 带参数名（`MissingoperatorId` /
> `paramError-operatorId` / `InvalidVersion`）= **路径存在、参数不对**；
> 403 = 存在但缺权限。据此能快速把「有没有这个接口」和「参数对不对」分开。
> `aiTable` 路径就是这样被识别为存在（400 InvalidVersion）但非本类文档所需。


### 2.6 unionId 怎么拿（需要通讯录权限）

老版 topapi 三步，本应用实测可用：

```text
GET  https://oapi.dingtalk.com/gettoken?appkey=&appsecret=   → access_token
POST https://oapi.dingtalk.com/topapi/user/listid            → dept_id 下的 userid 列表
POST https://oapi.dingtalk.com/topapi/v2/user/get            → userid → unionid（带 name）
```

unionId 跨企业/跨应用唯一，**同一个人的 unionId 在别的应用里也是同一个值**，
拿到一次可复用到其它应用配置。

> **隐私**：unionId 属个人信息，只写本机 `.env`（`DINGTALK_OPERATOR_*`），不写进仓库。

## 3. 两张表的结构

### 3.1 「2026年下单表」（15 张 sheet）

关键 sheet 与列：

**`物流信息表`** —— 工厂出库后的运输段（**「ZM 海运号」在这里**）

| 通途采购单号 | 物流单号 | 物流方式 | 送货地 | 件数 | 工厂发货日期 | 预计到货日期 | 实际签收日期 | 备注 |
|---|---|---|---|---|---|---|---|---|
| PO021704 | `ZMT26081353` | 普船 | NJ 07936-389 | 97 | 8月20日 | | | |

注意：键是**通途采购单号**（`PO…`），值里才有 `ZMT…` 物流号。别把两者搞反。

**`2026年度订单明细`** —— 一行一个 **(EN销售订单编号 × 通途SKU)**

| # | 列名 | 备注 |
|---|------|------|
| 1 | 日期 | |
| 2 | **EN销售订单编号** | 如 `SO-26-00101` —— **与 EN 的 join key** |
| 3 | 通途SKU | 如 `CENKZ1325-Yellow-138` |
| 4 | 物料名称 | |
| 5 | 是否皮壳 | 皮壳 / 成品 / 半成品 |
| 6 | 目的仓库 | 美中仓 / 美东仓 / 波兰 |
| 7 | 标签组合 | 如 `PP000-SX004-XH001` |
| 8 | 下单量 | |
| 9 | 需求交货日期 | |
| 10 | **订单信息备注** | 例：`SO-26-00099作废` |
| 11 | 生产类型 | 自制 / 外购 |
| 12 | 工厂确认交期（工厂） | 空 = 工厂还没确认 |
| 13 | 包装完成日期（工厂） | 空 = 未包装 |
| 14 | 实际包装完成量（工厂） | 空 = 未包装 |
| 15 | 物流发票编号（工厂） | 空 = 未交物流 |
| 16 | 出厂价（工厂） | |

**这张表第 12–15 列就是「工厂四件套」**：工厂确认交期 → 包装完成日期 → 实际包装完成量 →
物流发票编号。四列逐级为空，就是「生产完成了但还没进头程」的证据。

其它 sheet：`2026年度FBA订单（新）`、`2026年度配件订单`、`FBA（旧）`、`标签信息`、
`Sheet14`，以及一批按日期的历史 sheet（`2026.3.3`、`2026.3.25`…）。

### 3.2 「发货信息总表」（9 张 sheet）

| sheet | 内容 |
|-------|------|
| `物流跟踪Tracking` | **头程批次总表**（见下） |
| `美东下单表` / `美东发货明细` | 美东分公司批次 → 箱号级明细 |
| `美中下单表` / `美中发货明细` | 美中分公司批次 → 箱号级明细 |
| `欧洲下单Order` / `Packing List-PL` | 波兰批次 → 箱号/体积 |
| `FBA下单表` / `FBA发货明细` | FBA 批次 → 箱签号级明细 |

**`物流跟踪Tracking`** —— 一个批次一行：

| 下单日期 | 批次号 | 目的仓库 | 发货总数量 | 实际发货日期 | 发货渠道 | 物流单号 | 船名航次 | 离港日期 | 到港日期 | 入库日期 | 时效（天） | 运费总金额/CNY | 税金/EUR | 头程每公斤单价 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 2025/9/24 | `PL20250924 新品皮壳+真空袋` | 波兰分公司 | 1216 | 2025/10/31 | 业华-海运卡派如森递延 | HPL2510398 | EVER GLORY | 2025/11/9 | 2025/12/26 | 2026/1/16 | 77 | ¥34,790 | ¥4,897.75 | ¥10.10 |

**「批次号」是头程的主键**，形如 `NJHY…`（美东）/ `TXHY…`（美中）/ `PL…`（波兰）/
`LEFBAUK…`（FBA）。离港 / 到港 / 入库三列是**实际事件日期**，是「多久能上架」的最硬证据。

**`美中下单表` / `美东下单表` / `欧洲下单Order`** 列：
`日期 | 批次号 | SKU | 产品名称 | 数量`（批次号只写在该批首行，后续行留空 —— 读取要**向下填充**）。

**`美中发货明细` / `美东发货明细`** 列：
`需求单号 | 采购单号 | 产品名称 | SKU | 产品类型 | 采购数量 | 包裹号/箱号 | 外箱尺寸 | 重量(kg) | [美国签收日期 | 美国到货数量] | 备注`
—— 美东那张多两列「美国签收日期 / 美国到货数量」（**国外仓签收事实**），美中那张没有。

**`Packing List-PL`** 列：`批次号/Shipment ID | 箱号 | SKU | 名称 | 产品类型 | 数量 | 重量 | 外箱尺寸 | 体积 | 备注`

**`FBA发货明细`** 列：`批次编号 | 时间 | 编号 | 箱签编号 | SKU | 商品名称 | 仓库 | 产品类型 | 数量 | 重量 | 货物尺寸 | 外箱尺寸 | 体积 | 备注`

## 4. 由此修正的业务口径

### 4.1 EN 的 `po_no` 不是客户 PO 号

经计划物流同事 2026-09-15 核实：EN 销售订单上的 `po_no` / 行级 `purchase_order`
是**离职同事自编的内部流转号**，不是客户给的采购订单号。当年的用途是「一张 SO 对应多个
客户 PO 时，区分下单日期 / 仓库」。**现在 SO 自己就有下单日期和仓库，所以意义有限、之后可能弃用。**

→ 报表里只能当「内部流转号」展示并标待废弃；**不得对外称客户 PO，也不得拿它查头程**。

### 4.2 真实 join key 是 EN 销售订单编号

`Sales Order.name` == 「2026年度订单明细」第 2 列的 `EN销售订单编号`。
这正是计划同事说的「现在 SO 反正有下单日期和仓库，之后有个表格匹配就行了」。

### 4.3 实测案例（`CENKZ1325-Yellow-138`）

在「2026年度订单明细」里命中 `SO-26-00101` 的多行，其中本物料那行：

- 目的仓库 `美中仓`，下单量 40，需求交货日期 `2026/8/30`
- **第 12–15 列（工厂确认交期 / 包装完成日期 / 实际包装完成量 / 物流发票编号）全空**
  → 这 40 件还没有任何工厂侧的头程动作
- 同表 `SO-26-00101` 某行第 10 列备注写着 **`SO-26-00099作废`**
  → 证明 EN 里那张 `Closed` 的 `SO-26-00099` 在业务上确已作废（印证了「疑似重复」的判断）

`SO-26-00110`（80 件）同样在表里，也是工厂四件套全空。

## 5. 三个实测陷阱（每一个都能让人给出错误结论）

### 5.1 接口会用**空行把请求区域补满**

读 `A701:E1200`（超出数据范围）**不会返回空列表，而是稳定返回 500 行全空**。

后果：用「返回行数 < 请求行数 就停」做翻页条件**永远不触发**，
会把补齐的空行当数据一路读下去。**我据此误报过某张表有 40000 行，实际只有 380 行。**

正确做法：**遇到整块全空才停**，最后只裁掉末尾空行（中间空行是真实留白/分段，要保留）。
`client.read_sheet_all()` 就是这么做的；CLI 用 `--all`。

### 5.2 单次 range ≤ 30000 个单元格

`A1:P2000`（16 列 × 2000 行 = 32000）直接报：

```
400 invalidRequest.inputArgs.invalid
    This operation can only be performed on a range with at most 30000 cells
```

按列数算每块行数：`chunk_rows_for(n_cols)`；默认 500 行/块对 ≤60 列都安全。

### 5.3 会偶发 503，必须退避重试

整表扫描中途会遇到：

```
503 ServiceUnavailable / The request has failed due to a temporary failure of the server.
```

把它当致命错误会让长扫描整段失败。`http_json` 默认对 **5xx 与网络异常重试 3 次**
（指数退避），**4xx 不重试**（权限/参数错重试多少次都一样）。

### 5.4 各 sheet 的真实规模（2026-09-15 实测）

| sheet | 真实数据末行 |
|-------|-------------|
| 下单表 / 2026年度订单明细 | 516 |
| 下单表 / 物流信息表 | 12 |
| 下单表 / 2026年度FBA订单（新） | 97 |
| 发货总表 / 物流跟踪Tracking | 152 |
| 发货总表 / 美中下单表 | 380 |
| 发货总表 / 美中发货明细 | 1090 |
| 发货总表 / 美东下单表 | 249 |
| 发货总表 / 美东发货明细 | 1009 |

**全部 sheet 合计约 3500 行** —— 数据量很小，可以放心整表读。
凡是把某张表读成「几万行」的，一定是命中了 5.1 的补齐空行。

## 6. 文档来源（两个钉钉文档）

| 文档 | 链接 | baseId |
|------|------|--------|
| 2026年下单表 | https://alidocs.dingtalk.com/i/nodes/QOG9lyrgJPjjrl10uXDDw7RwWzN67Mw4 | `QOG9lyrgJPjjrl10uXDDw7RwWzN67Mw4` |
| 发货信息总表 | https://alidocs.dingtalk.com/i/nodes/qXomz1wAyjKVXd1x2xoxV3Y9pRBx5OrE | `qXomz1wAyjKVXd1x2xoxV3Y9pRBx5OrE` |

链接由计划物流同事 2026-09-15 提供。读取时把**整条链接**传给 `--url` 即可，不用手抠 baseId。
链接里的 `?utm_scene=` 参数与取数无关。

> baseId 只是文档标识，单独拿到它没有凭证和权限读不到内容；
> 但**表会改名、加 sheet、换文档**，所以后续脚本不要把 baseId 硬编码 —— 用 `--url` 传。

## 7. 外部调研来源

定位这套接口时用到的官方/第三方资料（按使用顺序）：

- [List multiple records — DingTalk Help Center](https://help.dingtalk.io/open/development/api-notable-listrecords)
  —— notable「列多行记录」接口（`operatorId`=unionId、`maxResults`≤100、`nextToken` 分页）；
  是判断「operatorId 到底要什么」的主要依据。
- [AI 表格 (多维表) OpenAPI 帮助文档](https://alidocs.dingtalk.com/h5/d?dt_editor_toolbar=true&biz_ver=10&showCommentPanel=false&docId=AJdl64r2VK4vqke1&from=dingnote&dd_user_keyboard=false&dd_full_screen=true&dontjump=true&utm_scene=team_space&mainsiteOrigin=mainsite&workspaceId=e3RmQ7jbWbdEQzaP&utm_source=portal&docKey=AJdl64r2VK4vqke1&dentryKey=xbwqjNg3I5yrQBn4&type=d#/preview)
  —— 钉钉自家放出的 AI 表格 OpenAPI 文档（**发布在 alidocs 里**）。
- [概要 — DingTalk Help Center (ai-table-overview)](https://help.dingtalk.io/ja/open/development/ai-table-overview)
  —— 概念层级：Base（一篇文档）/ Sheet（数据表）/ Field / Record。
- [dingtalk-ai-table API reference](https://github.com/aliramw/dingtalk-ai-table/blob/main/references/api-reference.md)
  —— 第三方整理的 API 参考，含 `baseId` 提取规则与错误码
  （`invalidRequest.document.notFound` / `typeIllegal` / `stillInitializing`）。

**这些资料只描述了 `notable`（AI 表格）这一条路**，而本次的两个文档是**普通钉钉表格**，
所以文档里的 notable 路径实测不可用（返回 baseId/document type 错误）。
最终走通的 `doc/workbooks` 端点是通过**逐端点探测**得到的，不是查到的 ——
探测过程见 `../log.md` 与 §2.5。
