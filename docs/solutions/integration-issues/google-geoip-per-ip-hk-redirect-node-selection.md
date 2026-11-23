---
okf: v0.1
type: Reference
title: Google 按「具体 IP」判地区 —— 日本节点仍跳 google.com.hk 的定界与换节点
date: 2026-11-23
category: integration-issues
module: office-network-openclash
problem_type: integration_issue
component: network
severity: low
applies_when:
  - "访问 google.com 被 302 到 google.com.hk，但 ipinfo 显示出口在日本/美国"
  - "Google One / AI Pro 提示 not available in your area，要区分线路还是账号"
  - "OpenClash / Clash Verge 选节点，想判断哪个节点 Google 认作目标国"
tags: [openclash, clash-verge, geoip, google, google-one, proxy, eons, hkredirect]
related_components: [us_openai_api_proxy, openwrt]
---

# Google 按「具体 IP」判地区 —— 日本节点仍跳 google.com.hk

## Context
2026-11-23：办公室 FZH-5G 的 OpenClash「自动选择=日本04」出口 `64.118.149.178`（ipinfo 显示 Tokyo/JP、Cloudflare colo=NRT，确实从日本出），但 `www.google.com` 仍 302 到 `google.com.hk?...pref=hkredirect`；换 Accept-Language、加 `gl=us&hl=en` 都不解决。用户想买黑五 Google AI Pro（$99.99/首年），one.google.com 提示「not available in your area」。

要区分两件事：**搜索跳 .hk 是线路/节点 IP 问题；Google One 买不了是账号付款国家问题**。

## 实测（直连光猫 + 本地 Clash Verge v1.19.29，逐节点切换）
判据：经代理 `curl -D - -o NUL https://www.google.com/`，看是否 `302 ... google.com.hk / hkredirect`。**不看 ipinfo**。

| 节点 | 出口 IP | ipinfo 国家 | ASN | Google 判定 |
|---|---|---|---|---|
| 日本1 | 64.118.148.223 | JP | AS138997 Eons Data | HK（跳 .hk）|
| 日本2 | 147.79.59.16 | JP | AS51847 Nearoute | HK |
| 日本3 | 64.118.148.222 | JP | AS138997 | HK |
| 日本4 | 64.118.149.178 | JP | AS138997 | HK（办公室自动选择当前落点）|
| 日本5 | 104.28.243.105 | JP | AS13335 Cloudflare | HK |
| 日本6/7/8 | 64.118.148.221 | JP | AS138997 | **干净（200，不跳）** |
| 美国1 | 64.118.152.53 | US | AS138997 | HK |
| 美国2 | 64.118.152.45 | US | AS138997 | HK |
| 美国3/4 | 5.34.217.8 / .26 | US | AS38136 Akari | **干净（200，不跳）** |

## 根因
不是「整个运营商被判香港」。**同一个 AS138997 的 `.221` Google 认作干净，`.178/.222/.223/.53/.45` 才判香港** —— 是**具体 IP** 在 Google 自家 GeoIP 库里的归属不同，与第三方库也常不一致（本例 ifconfig.co 甚至把该段误报 US/WINDSTREAM）。所以「IP 查是东京」不能证明 Google 也认为是东京。

AS138997（Eons Data Communications）注册在香港，这解释了这批 IP 容易被判 HK；但同段仍有干净 IP。

## Guidance
1. **判地区用 Google 自己的反应，别用 ipinfo**：`curl -D - -o NUL https://www.google.com/`，出现 `google.com.hk`/`hkredirect` 即「Google 认为你在港/中」，200 无跳转即「干净」。
2. **换到干净节点**：本例 日本 6/7/8（`64.118.148.221`）或 美国 3/4（`5.34.217.x` Akari）。办公室 OpenClash 的 `自动选择` 落在 日本4(.178) = 脏 IP，是 .hk 的直接原因。
3. **本地隔离测试**：办公室 FZH-5G 经 OpenClash，叠加本地 Clash Verge 会二次代理；实测境外 TLS `SSL_ERROR_SYSCALL`（exit 35），国内正常。要在 **直连光猫** 的网络上用本地 Clash Verge 测。
4. **Google One 资格另说**：买不买得到看账号/付款资料国家，换节点无效（见 Constraints）。

### Clash Verge 无 TCP 控制器时怎么切节点
Clash Verge 默认 `external-controller: ''`，走 named pipe `\\.\pipe\verge-mihomo`。可用 Python `open(r"\\.\pipe\verge-mihomo","r+b")` 直接发 HTTP：`GET /proxies`、`PUT /proxies/{组}` body `{"name":"<节点>"}`；响应可能 chunked，需自行解 chunk。

## Why This Matters
- .hk 只是表象；根因是「节点 IP 在 Google 眼里是香港」，换节点而不是改语言/清 cookie 才有效。
- 同一机场不同 IP 结论相反 ⇒ 不能一句「机场线路被判港」概括，必须逐 IP 验。
- 把「线路」和「账号资格」分开，避免在换节点上白花时间却仍买不了。

## Constraints
- **Google One / AI Pro 购买资格 = 账号国家 + 付款资料国家**，不是 IP。大陆不支持；改区需当地地址 + **当地发行**的付款方式（中国卡填美国地址大概率国家校验失败），Play 改区有冷却期。换任何节点都不会让中国区账号变成可购买。
- 2026 黑五 AI Pro 首年 $99.99（美区价）：老订阅 11/20–26 抢先，**新用户 11/27（黑五）起**；以当天 one.google.com 实际页面为准。
- 办公室路由器共用；改 OpenClash 节点影响全体同事，需先征得同意。

## Related
- [../best-practices/openclash-per-target-direct-rule.md](../best-practices/openclash-per-target-direct-rule.md) — OpenClash 目标级规则与排查。
- `docs/solutions/architecture-patterns/office-dual-wan-direct-ssid.md` — FZH-5G vs 直连 SSID 拓扑（在分支 `claude/brave-mcclintock-cdaa8c`，当前分支无此文件）。
- `docs/research/2026-09-21-jev-typesafe-research.md`（分支 `claude/brave-mcclintock-cdaa8c`）— 早先记录 `64.118.148.221` = 东京 AS138997。
- `us_openai_api_proxy/docs/operations.md` — AI 出口按国家分组（香港出口 ChatGPT 打不开）。

## 本次记录
- 2026-11-23：直连光猫 + 本地 Clash Verge 逐 12 节点实测；找到干净节点 日本6/7/8、美国3/4；测得办公室自动选择落在脏 IP `64.118.149.178`。未改共用 OpenClash。调研中确认该记录原先只存在于另一分支、主分支无——本篇补上。
