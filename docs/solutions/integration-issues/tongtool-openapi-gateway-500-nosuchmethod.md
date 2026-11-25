---
okf: v0.1
type: Reference
title: 通途 OpenAPI 业务接口集体 500：NoSuchMethodError 是网关部署故障，不是鉴权/参数
date: 2026-11-25
category: integration-issues
module: tongtool_api
problem_type: integration_issue
component: api-gateway
severity: high
symptoms:
  - "ordersQuery / supplierQuery / purchaseOrderQuery / stocksQuery / warehouseQuery 合法请求返回 HTTP 500（text/html）"
  - "响应体含 java.lang.NoSuchMethodError: com.ibiz.openapi.common.Context.getIsNewApp()"
  - "appToken / getAppBuyerList 认证接口正常 200；错参数仍返回 200/code=525；错 token 返回 401/code=523"
root_cause: "通途网关服务端类版本不匹配（getIsNewApp 方法缺失），合法请求进入业务 handler 即崩"
resolution_type: "上报服务商 + 等待修复；客户端区分 HTTP 错误与网络错误"
tags: [tongtool, openapi, http-500, nosuchmethoderror, gateway, retry-backoff, incident]
---

# 通途 OpenAPI 大面积 500 的判定与排查

## Problem

2026-11-24 中午前一切正常（12:03 欧洲盘中库存快照仍 Success），下午起通途 OpenAPI 的**所有业务查询**对合法请求返回 HTTP 500，
EN 的订单同步、库存同步、DN→采购单（PO）全部受影响。需要回答：是我们的 App/权限/参数问题，还是通途服务端问题？

## Symptoms（可复现的故障签名）

- 业务端点（POST `/api-service/openapi/tongtool/*`）→ `HTTP 500`，`Content-Type: text/html`，
  Tomcat 异常页；核心一行：

  ```
  Handler dispatch failed; nested exception is java.lang.NoSuchMethodError:
  com.ibiz.openapi.common.Context.getIsNewApp()Ljava/lang/String;
  ```

- 同一时刻：`devApp/appToken`、`partnerOpenInfo/getAppBuyerList` **200 正常**；
  参数不合法 → **200 + code=525**；token 错误 → **401 + code=523**；响应耗时 0.2~0.4s（不是超时）。
- 换 Key 无效：3 个不同 App、2 个不同商户；换网络无效：本机与阿里云生产服务器均复现。

## What Didn't Work

- **换 App Key/Secret**：三个 App 全 500，排除了单 App 授权或密钥问题。
- **怀疑 524（未授权）**：524 是业务 JSON 错误，这里是 HTML 500，且鉴权接口同一 Key 正常。
- **把 `api_version` 加到 query 参数**：只会变成 `401 / code=519 sign fail`（签名覆盖参数），反而掩盖问题。
- **在 EN 里用 `bench execute` / 白名单接口验证**：见下面的退避陷阱，每次卡 30 分钟以上，什么都看不到。

## Solution

1. **三级探测法定位责任方**（适用于任何"外部 API 突然全挂"）：
   1. 认证接口是否 200 → 排除密钥/网络；
   2. 故意发非法参数 → 若仍能拿到业务错误码（525），说明已通过鉴权；
   3. 发**合法**请求 → 只有这一步失败且错误是服务端类/方法错误（Java `NoSuchMethodError`、Python `ImportError` 等），即为服务端部署问题，客户端无解。
   第 1、2 步通过、第 3 步 500，责任在服务端 —— 不要继续换 Key。
2. **本地直连、绕过业务客户端**：用 `requests` 直接调（`timeout=20`），不要走 app 里带重试的客户端。
   EN 的 `TongToolClient` 把 **HTTP 500 当成网络异常**，按 `retry_delay_minutes=5` 做 5/10/20 分钟退避 ×3，
   单次调用可卡约 35 分钟 —— "测个 API 怎么这么慢"的根因就在这。
3. **报障材料**：接口地址、精确异常文本、合法请求报文（header + body）、时间窗、以及"auth/参数校验正常"三条对照证据。
   本轮通途在当天 18:00 前恢复（18:01 美国盘中快照 Success 可佐证），11-25 四端点全部 200。

## Why This Works

`NoSuchMethodError` 是 JVM 链接期错误：请求已通过网关鉴权、进入业务 handler，随后引用了部署包中不存在的类/方法 →
只可能是服务端发布/回滚造成的版本不匹配。认证接口与业务 handler 分属不同模块，所以"认证正常、业务全崩"是这类故障的典型指纹。

## Prevention

- **客户端区分错误类型**：4xx 不重试；5xx 最多短重试 1 次；只有连接/超时才走长退避。当前 app 把 500 归入网络重试，是本次排查被拖慢的直接原因。
- **巡检看"业务请求是否成功"而不只看任务是否触发**：`Scheduled Job Log` 的 `Complete` 只代表投递/入队成功，
  真正的结果要看 app 自己的 Run 记录（本例 `Tongtool Stock Run`）与 Error Log。
- 记录故障签名到 handoff/skill，下次同错误 30 秒内定性，不再逐个换 Key 试。

## Related

- [通途 ERP2.0 采购单 API](../../../tongtool_api/docs/reference/purchase-orders.md) —— `purchaseOrderQuery/Create` 字段口径与 DN 映射链
- `tongtool_api/AGENT_HANDOFF.md` —— 错误码表（524/525/526/527）与共享限流事实
- `EN_API/docs/reference/en-server-access.md` —— 生产/测试 SSH 与 REST 入口
