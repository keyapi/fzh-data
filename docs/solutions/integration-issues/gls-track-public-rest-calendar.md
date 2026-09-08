---
okf: v0.1
type: Reference
title: GLS 波兰自发货跟踪——公开无鉴权 REST 免账号可行 + 口径坑（日历/脏单元格/返件）
date: 2026-09-07
last_updated: 2026-09-08
category: integration-issues
module: gls_track
problem_type: integration_issue
component: tracking-integration
severity: medium
applies_when:
  - "要给 GLS（波兰分公司自发货）单号批量取轨迹/出运营异常表"
  - "判断 GLS 迟发/漏发/卡件/承运延误，或把 GLS 接进多承运商统一报表"
---

# GLS 波兰自发货跟踪：公开无鉴权免账号 + 口径坑

## Context

FedEx/UPS 已有官方 Track 客户端 + 运营异常表。波兰分公司经 GLS 波兰自发货，8 月样本 ~1265 行(去重~1176 单号，>1000/月)，
需要进入同一套运营异常判定。直觉假设是"像 UPS/FedEx 一样注册开发者账号"，但**手头没有波兰 GLS 登录凭证**。
要回答：GLS 跟踪是否必须注册开发者账号？能否不靠波兰 GLS 客户账号？

## Guidance（本学习沉淀的做法）

1. **读轨迹免账号**：GLS 消费级网页跟踪底层是**公开无鉴权 REST**，浏览器提交单号后反解出真实 XHR：
   - 摘要 `GET https://gls-group.com/app/service/open/rest/PL/en/rstt029?match={号}&type=&caller=witt002&millis={ms}`（免任何入参）
   - 明细 `GET .../rstt028/{号}?caller=witt002&millis={ms}&postalCode={目的邮编}`（全量 history；**钥匙=目的邮编**，订单 `邮编` 列已有）
   - `curl` 直连无 cookie/JS 即 200 JSON。官方 ShipIT/MyGLS 则要 GLS 波兰客户 + WebAPI 开通，是**要客户账号不是纯开发者账号**；`dev-portal.gls-group.net`(德国集团侧)注册是必要非充分。
2. **口径不能照抄 FedEx**：时点映射 建标≈数据录入 GLS IT、收件≈交接 GLS、交付=delivered；
   `HANDLING_DAYS` 现已与 UPS/FedEx **统一为 3**（日历仍用波兰假日，勿照抄美国联邦假日）；
   落地初期曾用 `HANDLING_DAYS=2`(当时 FedEx=1) 消化「周四录入→周一交接」误判。
   「Amazon是否判迟」**仅 Amazon/亚马逊 渠道**(中文 亚马逊要单独匹配)。
3. **loader 拆一格多号**：通途 `跟踪号` 单元格会一格塞多号/混入 UPS `1Z`、allegro `…U`、截断碎片 → 按号拆分去重，整月单命令直出正确集合(ok 1148/err 39)。
4. **限流**：公开接口无速率头/无公开限流文档；**共享 httpx 连接池 ≤8 并发实测安全**(默认 4)；每请求新建 TLS 会零星 transport 失败 → 共享 client + 重试。整月 ~1187 单 `--workers 4` ≈ 3m45s。

## Why This Matters

- 不必等/申请波兰 GLS 开发者-客户体系即可先落地免账号跟踪；把"官方通道"降级为可选项。
- 日历若沿用 FedEx(美国联邦)会给欧盟单引入与事实不符的假日；**欧盟无统一假日**，Amazon 判迟本身按各站点国家历——统一多承运商报表要能按 承运商/区域 选日历，这是 GLS 给 parcel_track 的关键输入。
- 脏单元格/返件/窗口抖动是 404 与误判主因，拆号 + 明确判定规则避免运营误读。

## When to Apply

- 接 GLS 进 parcel_track(PR #215 Cursor 统一多承运商)时按 `gls_track/AGENT_HANDOFF.md` 末节的归一字段接入，并给 classify 加日历配置。
- 任何"GLS 要不要注册/要账号吗"的提问，直接引用本文结论。

## Examples

```bash
python -m gls_track.cli monthly --input <当月通途xlsx> --out gls_202608 --workers 4
# → gls_202608.summary.csv / .timeline.csv / gls_202608_ops.xlsx（FedEx 风格 8-Sheet）
```

输出映射样例（ok 集）：正常交付/承运延误/迟发/卡件/漏发未交接/在途/数据异常·查无。

## 参考

- 调研与口径：`docs/research/2026-09-07-gls-poland-track-feasibility.md`
- 混合统一处理天数 / `--workers` 语义（取代本文早期 HANDLING=2 数值）：`docs/solutions/conventions/parcel-track-handling-days-sequential-workers.md`
- 模块：`gls_track/AGENT_HANDOFF.md`、`gls_track/docs/index.md`
- 相似先例：`docs/research/2026-09-04-fedex-track-account-investigation.md`、`docs/solutions/workflow-issues/fedex-track-batch-query.md`
