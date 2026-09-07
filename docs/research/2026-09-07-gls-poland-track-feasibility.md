---
type: Research
title: GLS 跟踪可行性 — 公开无鉴权 API 无需开发者账号；官方 API 需波兰 GLS 客户开通
description: 读 GLS 轨迹不需开发者账号：公开 REST rstt029/rstt028 免登录实测可行（明细需目的邮编）；官方 ShipIT/MyGLS 要 GLS 波兰客户号 + WebAPI 开通，纯开发者账号替代不了
---

# GLS 跟踪调研：是否需要开发者账号？能否不用波兰 GLS 客户账号？(2026-09-07)

## 一句话结论

读 GLS 轨迹有两条路，**都不需要"开发者账号"**：

1. **公开无鉴权 REST（本次已实证，零账号零登录）**：`https://gls-group.com/app/service/open/rest/PL/en/…`
   - 摘要 `rstt029`：免任何入参 → 状态 / 交付时间 / 阶段进度。
   - 明细 `rstt028`：需**目的邮编** → 完整 scan 时间线（建标/收件/中转/交付/签收）。邮编在通途订单数据里已有。
   - 实测 `curl` 直连即 200 JSON，无 cookie / 无 JS / 无登录。
2. **官方 API（ShipIT / MyGLS）**：**要"客户账号"，不是"纯开发者账号"**。
   - `dev-portal.gls-group.net`（GLS ITS/德国集团侧，免费自助）注册+建 App 是**必要非充分**；
   - 真正解锁 = **GLS 波兰客户号/合同 + 当地开通 WebAPI**（ADE plus/Uni-Portal 登录，office@gls-poland.com 或客户经理）。凭波兰客户关系，非开发者账号可替代。

→ 若目标是进同一份运营异常报表（迟发/承运延误/卡件），**公开路径即可覆盖，无需注册任何账号**；官方通道仅在你想要更正式/SLA 时才需要，且必须靠波兰分公司向 GLS 波兰申请。

## 为什么调研

`parcel_track`（PR #215）把 GLS/GOFO 行停放（`route.py` 内 `unsupported:gls`）。波兰分公司经 GLS 波兰自发货，2026-08 样本 1265 行 GLS（去重 1176 单号），>1000/月、可能每几天跑一次，最终也想走官方进入与 UPS/FedEx 相同的异常报表。

## 样本与号形态（只读，勿提交数据）

- 样本 xlsx：`D:\Work\王忠于\成本核算\通途非FBA订单202608 202609030947 无需填0售价 加预估尾程.xlsx`（10912 行，91 列）。
- **GLS-Poland 行 1265** = `GLS-Poland>>GLS-Poland` 1046 + `>>HOME24 GLS DE` 197 + `>>GLS-NL` 18 + `>>GLS-Poland-RueduCommerce` 2 + `>>GLS-PT` 2。
- 渠道：亚马逊 582 / Mirakl 379 / allegro 106 / kaufland.de 64 / Wayfair 48 / Cdiscount 36 / manomano 26…
- 收货国：DE / FR / PL / AT / IT / GB / CH / NL…；发货仓 `波兰-FZHPoland-covers`。
- **跟踪号**：非空行 1226 → 去重 **1176 单号**；主流 **11 位数字、`2` 开头、递增**（如 `29626585597`）；同单多订单行重复同号 → 查询前先去重。39 行（部分 Wayfair）无跟踪号需另排查。

## 公开无鉴权路径实证（Playwright + curl，2026-09-07）

页面 `https://gls-group.com/PL/en/parcel-tracking/`：「只需单号、无需登录」。浏览器提交真实号后抓 network 反解出真实 XHR（均为 open REST，`rstt` 前缀 = Track&Trace open 组）：

- **摘要**：`GET /app/service/open/rest/PL/en/rstt029?match={跟踪号}&type=&caller=witt002&millis={epoch_ms}` → `{"tuStatus":[{…,"statusInfo":"DELIVERED","arrivalTime":{…"03-Sep-2026 at 12:39…"}}]}`
- **明细**：`GET /app/service/open/rest/PL/en/rstt028/{跟踪号}?caller=witt002&millis={…}&postalCode={目的邮编}` → `{…,"history":[{date,time,evtDscr,address{city,countryCode}}, …]}`
- `caller=witt002` = 该跟踪 widget 的应用标识（页面自带）；`millis` 时间戳可选。**邮编是解锁明细的唯一钥匙**（收货人侧用它验证身份），我们订单 `邮编` 列有。

直连 curl（无浏览器 cookie/JS）实测同号 `29626585597` / 目的邮编 `21706`（Drochtersen DE）→ 200，history 10 条，恰好覆盖 ops_report 需要的关键时点：

| 时间 | 城市 | 事件（对应判定） |
|---|---|---|
| 2026-08-31 07:06 | Strykow PL | parcel data entered, not yet handed（≈建标/预报）|
| 2026-08-31 20:20 | Strykow PL | handed over to GLS + reached parcel center（≈收件首扫）|
| 2026-09-01 21:34 | Neuenstein DE | reached / left parcel center（中转）|
| 2026-09-02 07:39 | Geestland DE | reached parcel center（目的站）|
| 2026-09-03 12:39 | Geestland DE | delivered + signature（交付）|

detail 还含 `references`（含 `CUSTREF` P8… = 发货时客户引用，可回连订单）、`infos`（product=EuroBusinessSmallParcel / weight / services）、`signature`。风险注：单号 2 次请求（摘要+明细）；本测试 + 多个浏览器/curl 并发未触发限流/captcha；1176/月量级低，建议并发 1–2 + 交付后缓存即可。

## 官方解锁路径（GLS 波兰）—— 回答「开发者账号能否不用波兰 GLS 账号」

**不能。** 走官方 API 需要的是 GLS 客户身份，流程：

1. 已签约 GLS 客户（波兰分公司已是 → 已有客户号/合同）。
2. 门户登录：GLS 波兰客户门户 = **ADE plus**（跟踪页 Login 指向 `adeplus.gls-poland.com`；旧集成商文档称 Uni-Portal）。API 文档从**客户经理或 ADE plus** 获取（GLS 波兰官网 FAQ 原文）。
3. **GLS 波兰开通 API/WebAPI**：`office@gls-poland.com` 或客户顾问；未开通报 `err_user_webapi_blocked`（GLS 波兰集成商记录）。
4. ShipIT base URL 由你的 GLS 联系人下发；服务/条件随国家与合同关系而异。

为什么「注册开发者账号」替代不了：
- `dev-portal.gls-group.net` 是 GLS ITS/德国侧 Apigee：注册 + 建 App（勾 Authentication + ShipIT-Farm API）免费自助，但按 ShipStation / Pickware / SendCloud，**激活仍要 GLS 客户合同 + GLS Contact ID + 当地 GLS 批准**；ShipStation 明确无 `portal_username/portal_password/customer_id` → tracking 不工作。
- GLS 各国门户分散（NL 有自家 Azure portal；波兰 ADE plus/Uni-Portal），集团 dev portal 未必覆盖波兰 ShipIT。
- → 开发者账号是「你要自建 App 集成时」的壳，不是 Tracking 的钥匙。波兰钥匙在分公司 GLS 客户关系里。

## 给分公司的请求（解锁官方通道，可选）

> 「请让 GLS 波兰客户经理：(1) 开通我方客户号的 WebAPI/API 访问；(2) 提供 ADE plus(Uni-Portal) 登录或 API 凭证（客户号 / Contact ID / portal user）。用途：把 GLS 单号自动同步进轨迹报表。若只要轨迹状态，公开接口已够，此请求仅用于更正式/更大批量时的官方通道。」

## 建议

- **当前即可用公开无鉴权路径做 GLS 跟踪（零账号）**。落地模块建议等 PR #215 合入后放进 `parcel_track` 做 GLS adapter（复用现有 classify / route），查询先去重、带目的邮编。
- 官方通道（更稳/SLA）需上面清单 → 属分公司业务协调，非技术侧能自助。
- 风险：GLS 公开接口未承诺 SLA/可能改版；波兰官方 API 侧集成商曾报约每 2-3 个月数据更新（版本迁动）。缓存已交付号、降速重试应对。

## 参考 URL

- GLS 波兰跟踪页（Login=ADE plus）：https://gls-group.com/PL/en/parcel-tracking/
- GLS 波兰 eCommerce/API FAQ（文档走客户经理或 ADE plus）：https://gls-group.com/PL/en/ecommerce
- 实测 endpoint（curl 200，open REST）：`https://gls-group.com/app/service/open/rest/PL/en/rstt029?match=…`、`…/rstt028/{no}?postalCode=…`
- GLS Developer Portal（德国集团侧）：https://dev-portal.gls-group.net（/get-started）；综述 https://apis.io/providers/gls-group
- ShipStation GLS ShipIT（track 需 portal/customer 凭据）：https://docs.shipstation.com/apis/docs/carriers/gls-germany-shipit-guide
- Pickware 新 GLS API 激活流程：https://help.pickware.com/en/articles/659340-how-do-i-get-access-credentials-for-the-new-gls-api
- SendCloud GLS Europe 合同激活（奥地利）：https://support.sendcloud.com/hc/en-us/articles/35683288483089-GLS-Europe-Contract-Activation-Austria
- GLS 波兰集成商记录（Uni-Portal WebAPI / err_user_webapi_blocked / 每 2-3 月更新）：https://metakocka.freshdesk.com/en/support/solutions/articles/3000071815-integration-with-gls-poland
- ShipIT 文档（URL 由 GLS 联系人给、国家各异）：https://shipit.gls-group.com/webservices/3_3_20/doxygen/WS-SOAP-API/index.html

## 原型 `gls_track` 与实测（2026-09-07）

落地了最小客户端 `gls_track/`（公开 REST，免账号）：`client.py`(httpx, rstt029/028) + `models.py`(归一化/关键时点) + `cli.py`(`python -m gls_track.cli query --input … --out …`) + 离线单测。README 见 `gls_track/README.md`。

实测 2026-08 通途样本前 25 号：24/25 查通（DELIVERED 23 / INTRANSIT 1，交付号带回 `CUSTREF` P8… 可回连订单）；1 个 `1048249357601U`(allegro 行) 404 = **非 GLS 单号**（U 后缀不是 GLS parcel，将来 route 需按号形态过滤）。发现边界：部分包裹先 DELIVERED 后回退（返件 `29626350320` 08-10 派送→08-14 回 Strykow），GLS 头条状态 INTRANSIT——头条以 `statusInfo` 为准，history 保留回退细节。

## 未决 / 风险

- 公开接口限流/反爬规模未压测；ToS 未细读（页面「可一次输入多号」暗示批量是被允许用法，仍建议低频+缓存）。
- 39 行 GLS-Poland 无跟踪号（部分 Wayfair 未发）需另排查。
- 明细需目的邮编：从订单文件带 `邮编`；个别行/国家可能缺失。
- endpoint 挂在 PL 实例（`/PL/en/`）；若未来接入非 PL 货主国单号，可能要按货主国换页/换 host。
