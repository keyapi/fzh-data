---
okf: v0.1
type: Reference
title: FedEx 官方批量 Track 查询 + 账号/组织恢复路径
date: 2026-09-04
category: workflow-issues
module: fedex_track
problem_type: workflow_issue
component: tracking-integration
severity: medium
applies_when:
  - "给一批 FedEx 跟踪码返回轨迹，且需要完整状态历史（建标/站点收件/交付）"
  - "FedEx 开发者账号/组织归属混乱、部分登录被强制重置、账号号被其他组织占用"
  - "需要判断仓库迟发/漏发（对比发货日期与站点收件时间）"
tags: [fedex, track, oauth2, integration, billing-account, organization, workflow]
related_components: [ups_track, sellfox_shipping, vite-api, yiglobal-api]
---

# FedEx 官方批量 Track 查询 + 账号/组织恢复路径

## Context

公司要做"给一堆 FedEx 跟踪码 → 返回轨迹"，同 `ups_track` 的思路。现实障碍：官方 FedEx 开发者账号（2023 年建）登录被强制重置且邮箱废弃；多货代（VITE / 蜴国际=M6180）出的 FedEx 尾程单号散落；`879197228` 这个唯一确认真实发货账号号被"另一组织占用"。另有一批销售凭证（`FEDEX_*`）在仓库 `config.yaml` 只是占位，从未真正接入。本条目记录：打通官方 Track API 的关键结论 + 账号/组织恢复路径 + 建成的 `fedex_track` 模块 + 三条踩坑教训。

## Guidance

1. **官方 Track API 是正解，且跨渠道可查**。`POST {base}/track/v1/trackingnumbers`，body `{"trackingInfo":[{"trackingNumberInfo":{"trackingNumber":"..."}}],"includeDetailedScans":true}`。**一次最多 30 个号**，超出分块；**不需要单号属于自有账号**（VITE/蜴国际 借货代 FedEx 账号出的单也能按号查到）；查号**不需要目的邮编**（只有"按 reference 查"才要）。配额：Track 能力 **10 万次/请求/日**、限速 **1400 次/10 秒** —— 注意是**按请求次数**，不是按跟踪号个数；30 个号/请求下，6752 个号 ≈ 225 次请求，远低于配额，不会触发超额/收费。
2. **生产 key 前置 = 组织里绑一个真实且未被其他组织占用的发货账号号**。FedEx 一个发货账号号只能绑进一个开发者组织；"已被另一组织使用"先查**自己的组织**，别先怀疑赛狐。
3. **账号/组织恢复路径**（本次实测走通）：
   - `lihui@vilavidress.com`（2023 主账号）被强制重置 + 邮箱废弃 → 用**腾讯企业邮箱管理员**把该邮箱转公共邮箱/备份规则，收 FedEx 重置验证码 → 重置 FedEx 密码 → 成功登录。
   - 登录后进入 2023 主组织 **Centrade(10548976)**（管理员=PAULA MA，显示名即邮箱 `lihui@`）；此组织绑定发货账号 `CentradeFedex01`=`879197228`（EULA Completed）。**占用 879197228 的"另一组织"就是它自己**，不是赛狐。
   - 其他组织：Centrade2=Paula→CENTRADE INC(10695072，无账号)；daneey=Eric→CENTRADE INC(10879188，无账号，有 `fzh_fedex_track` 项目仅 TEST)；leonzhao@daneey.com 登录失败。
   - 在 Centrade(10548976) 内新建项目（勾 **Basic Integrated Visibility = formerly Track API**，国家 United States，接受 DPLA + 超额费用条款）→ **Production Key** tab → 填 key name、选 `CentradeFedex01`→ 生成 prod key，**secret 只在那一屏显示一次，马上存 `.env`**。
4. **模块 `fedex_track/`（仿 ups_track）**：`client.py`(OAuth2 + `track_many` 批量≤30) / `models.py`(保留**完整 `scanEvents`** 升序 + 三时点：建标/站点收件/交付/取消) / `batch.py`(分块并发/重试/断点续跑；清单支持 txt/csv/**xlsx**，自动找跟踪号列) / `cli.py`(输出 summary.csv / timeline.csv=完整历史 / raw.json=每号原始响应)。`--filter-carrier fedex` 从混合单号里只留 FedEx；默认按号**去重**。
5. **关键时点用"事件码+描述关键字"提取**（词表在 `models.py`）：建标 `Label created`/`Shipment information sent to FedEx`；站点收件 `Picked up`/`Arrived at FedEx location`；交付 `eventType=DL`。**"已取消"= 仅当最终状态为取消(CA/CAF)且未交付**——FedEx 事件流里可能**残留一条 CA(cancelled) 节点但包裹实际已交付**（本次 4 个单被误标，已修正）。销售核查：**站点收件时间** 对比 备注里的 **发货日期/发货时间** → 有发货时间但一直无站点收件 = 漏发；站点收件比发货日晚很多 = 迟发；status=在途 超天数 = 卡件。
6. **同号多票（FedEx 复用跟踪号）**：FedEx 号码约 4–6 年一轮回、前段/SCC 常数段常绑指定发件账号，同一 12 位号可能对应两票（如 `382954490594`：6 月一票 Venus,TX 已交付 + 8 月一票 Sioux Falls,SD 已交付）。`fedex_track` 对每个号**保留全部 trackResult**，summary/timeline 用 `[n]` 后缀加 `多票`/`分票` 列区分；**判归属按建标/交付时间落在该单所属发货窗口的那一票**。机器生成的 pickup（如 `12:00 AM Picked up` 无前序建标）通常是旧票复用，注意与真实发货区分。

## Why This Matters

- **不要只信 headless 自动化探针**：FedEx（Akamai）会对无头/自动化返回**假的** `system-error` + "can't find that tracking number"，而真实浏览器能查到（本次两个真实号都被自动化"查无此号"，用户真实浏览器里一个是 Delivered、一个是 Cancelled）。下"查不到/行不通"结论前，**至少第二来源**（真实 Chrome / 官方 API / 用户实测 / 文档）；对反爬站，**同一会话内先暖会话（访问几页、接受 cookie）再重试**往往就过。
- **按"邮寄方式"关键词统计会漏**：方法列里 UPS 单(1Z)标的是 `Overstock>>OSTK`/`GLS-Poland` 这种**渠道名**，没写"UPS"；`Centrade>>Not Prime` 的 12 位数字其实**也是 FedEx**。可靠的分类是**12 位纯数字 → 基本是 FedEx**；统计必须**全文件去重**，抽样行数会严重低估（本次 1597 vs 去重后 6743）。
- **配额按"请求"不按"号"**：批量 30/请求，几万号也只在几百次请求内，不会触发每天 10 万的超额。别再被"超额费用"条款吓到而不敢批量。

## When to Apply

- 需要 FedEx 官方跟踪（跨渠道/货代单）且要完整历史时，直接用 `fedex_track`。
- 遇到 FedEx 账号"被另一组织占用 / 登录强制重置 / 邮箱收不到码" → 按上文恢复路径（先查自己的 org，用企业邮箱管理员收码）。
- 遇到"FedEx 查不到某号 / 自动化探针说不行" → 先核实是不是反爬假报错，再看是不是货代单未在 FedEx 生效。
- 要统计某文件里有多少 FedEx 单 → 用 12 位纯数字 + 全文件去重，不要抽样。

## Examples

```bash
set -a && . ./.env && set +a   # .env 含 FEDEX_API_KEY/SECRET/ACCOUNT/FEDEX_ENV=production
uv run python -m fedex_track.cli query \
  --input "通途非FBA订单202608.xlsx" \
  --env production --filter-carrier fedex --limit 100 --out result
# 输出 result.summary.csv（每号：当前状态/建标/站点收件/交付时间）result.timeline.csv（完整历史）result.raw.json
```

summary 片段（`站点收件时间`=FedEx Picked up）：
```
跟踪号        建标时间            站点收件时间        交付时间              交付城市
382915919064 2026-07-31 03:56  2026-07-31 15:15  2026-08-05 10:44      Newark,DE
```
备注列带 `承运=M6180蜴国际>>M6180蜴国际-Fedex | 发货日期=2026-08-01 | 发货时间=05:46`，可直接比对是否迟发/漏发。

## Related

- `ups_track`/`docs/solutions/workflow-issues/pb-reconciliation-monthly-update.md`（UPS 跟踪的同类实现）
- `docs/research/2026-09-04-fedex-track-account-investigation.md`（本次完整勘查、凭证实测、腾讯邮箱接收链路、URL）
- `fedex_track/docs/index.md`（模块说明）、`ups_track/docs/ups-developer-account-setup.md`（UPS 账号 runbook 模板）
- 货代网关备选：`vite-api/docs/carriers/fedex/`、`yiglobal-api/docs/api-reference.md`（蜴国际 M6180，API 无按号查轨迹端点）
