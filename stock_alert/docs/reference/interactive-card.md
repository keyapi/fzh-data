---
okf: v0.1
type: Reference
title: stock_alert 钉钉互动卡片接入
description: 用企业内部应用与卡片模板实现居中标题、蓝底头部、统计框和通栏按钮；配置不全时回退 ActionCard。
---
# 钉钉互动卡片

> **默认不需要本页**：`stock_alert` 默认用 `card_image.py` 渲染 PNG 图片卡片，通过现有群机器人发送。
> 本页仅用于需要钉钉**原生互动卡片**（可更新卡片、模板级布局）时。

## 为什么需要它

现有 `dingtalk/dingtalk_robot` 用的是**自定义机器人 Webhook + ActionCard**，正文只支持
钉钉 Markdown 子集：不能做居中标题、背景色、统计框、右对齐数字或自定义按钮颜色。
Codex 的预览图属于**卡片模板**效果，必须走**企业内部应用 + 互动卡片**。

配置不全或发送失败时，`stock_alert` 自动回退到现有 ActionCard，不影响每日提醒。

## 前置条件

1. **企业内部应用**：拿到 Client ID / Client Secret。
2. **应用机器人已安装到目标群**：`robotCode` 默认等于 Client ID；群会话需要
   `openConversationId`（不是 Webhook 的 access_token）。
3. **卡片模板**：在钉钉**卡片平台**新建并**发布**两个模板，变量名必须与下面完全一致。
4. 应用权限至少包含 `Card.Instance.Write`；获取群 ID 还需要群会话相关权限
   （`qyapi_chat_read` / `qyapi_chat_manage` 等，视企业开通情况）。

### 获取 openConversationId

如果只知道群 `chatId`：

```http
POST https://api.dingtalk.com/v1.0/im/chat/{chatId}/convertToOpenConversationId
x-acs-dingtalk-access-token: <accessToken>
```

返回的 `openConversationId` 即填到 `DINGTALK_OPEN_CONVERSATION_ID`。
也可以让管理员在钉钉开发者工具/客户端选择会话时拿到。

## 配置（只放根 `.env`，已 gitignore）

```dotenv
DINGTALK_CLIENT_ID=...
DINGTALK_CLIENT_SECRET=...
DINGTALK_ROBOT_CODE=...                 # 可省略，默认 = Client ID
DINGTALK_OPEN_CONVERSATION_ID=...       # 形如 cid...==
DINGTALK_OPERATOR_ID=...                # 可选，卡片创建人 userId
DINGTALK_LOW_STOCK_TEMPLATE_ID=...
DINGTALK_INBOUND_TEMPLATE_ID=...
```

模板 ID 在卡片平台「保存 → 发布」后生成。修改模板后必须重新发布。

## 模板变量（全部字符串）

### 低库存模板 `DINGTALK_LOW_STOCK_TEMPLATE_ID`

| 变量 | 说明 | 示例 |
|---|---|---|
| `title` | 卡片标题（模板里设置居中） | 通途低库存提醒 |
| `subtitle` | 日期 | 2026-11-17 |
| `overview` | 概览（可放统计框） | 今日新增 **18** 个 |
| `body` | 分仓明细 Markdown | `### 美中-FZH-DANEEY\n\n今日新增 **6** 个 · 在途 **2723** 件` |
| `btn1Title` | 按钮 1 文案 | 下载今日新增（18） |
| `btn1Url` | 按钮 1 链接 | https://erpnext.vilavi.cn/files/...xlsx |
| `btn2Title` | 按钮 2 文案 | 下载全部低库存（411） |
| `btn2Url` | 按钮 2 链接 | https://erpnext.vilavi.cn/files/...xlsx |
| `footnote` | 口径脚注 | 口径：可用库存 < 5，排除可用=0且在途=0。 |

### 采购入库模板 `DINGTALK_INBOUND_TEMPLATE_ID`

| 变量 | 说明 | 示例 |
|---|---|---|
| `title` | 卡片标题（模板里设置居中） | 通途采购入库提醒 |
| `subtitle` | 日期 + 说明 | 2026-11-16 · 昨日入库 |
| `overview` | 概览（可放统计框） | 共 **1** 个 SKU · 入库 **45** 个 |
| `body` | 分仓/产品明细 Markdown | `### 美中-FZH-DANEEY\n\n入库：**45** 个 · **1** 个 SKU` |
| `btn1Title` | 按钮文案 | 下载全部采购入库明细 |
| `btn1Url` | 按钮链接 | https://erpnext.vilavi.cn/files/...xlsx |
| `footnote` | 口径脚注 | 统计口径：采购单（02）正向入库事件，不代表采购单全部到货。 |

建议模板布局（对齐 Codex 预览图）：

- 深蓝头部：`title` 居中、白色加粗大字；`subtitle` 在下方；
- 浅蓝圆角统计框：`overview`；
- 内容区：`body` 用 Markdown 组件；
- 底部：`btn1` / `btn2` 通栏青绿色按钮；
- 最底部：`footnote` 灰色小字。

## 发送流程

1. `POST https://api.dingtalk.com/v1.0/oauth2/accessToken`，body `{appKey, appSecret}` → `accessToken`。
2. `POST https://api.dingtalk.com/v1.0/card/instances/createAndDeliver`，
   header `x-acs-dingtalk-access-token`，body：

```json
{
  "cardTemplateId": "模板 ID",
  "outTrackId": "stock_alert_<uuid>",
  "openSpaceId": "openConversationId",
  "cardData": {"cardParamMap": {"title": "...", "body": "..."}},
  "imGroupOpenSpaceModel": {"supportForward": true},
  "imGroupOpenDeliverModel": {"robotCode": "应用 Client ID"},
  "userId": "可选 operator userId"
}
```

实现见 `stock_alert/card.py`。

## 测试步骤

```bash
# 1. 配置根 .env 后，dry-run 会多出 card_preview（模板变量与真实数据）
uv run python -m stock_alert.cli run --dry-run | tail -60

# 2. 真发（成功后返回 mode=interactive）
uv run python -m stock_alert.cli run --notify
uv run python -m stock_alert.cli inbound --notify
```

- 返回 `mode=interactive`：互动卡片发送成功。
- 返回 `mode` 不是 `interactive`：查看 stderr 的 `[warn] 互动卡片...`，会说明回退原因；
  提醒本身仍会通过 ActionCard 发出。
- 配置不全（缺模板 ID/群 ID/应用凭证）时不会尝试互动卡片，直接走 ActionCard。

## 排障

| 表现 | 检查 |
|---|---|
| `accessToken 失败` | Client ID/Secret、应用是否启用 |
| `createAndDeliver 失败 param.error` | 模板是否已发布、变量名是否完全一致、群 ID/robotCode 是否正确 |
| 卡片空白 | 模板变量未绑定或未重新发布 |
| 群收不到 | 机器人是否安装到该群、openConversationId 是否属于该群 |
| 一直回退 ActionCard | 检查 7 个环境变量是否齐全；看 stderr 的 warn |
