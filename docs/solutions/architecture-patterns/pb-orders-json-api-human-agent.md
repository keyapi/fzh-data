---
okf: v0.1
type: Reference
title: 人 + Agent 共用的订单 API —— PB 网页与 JSON API 共用一套服务层
date: 2026-10-29
category: architecture-patterns
module: pb_orders
problem_type: architecture_pattern
component: tooling
severity: medium
applies_when:
  - "给已有内部工具增加 Agent 可调用的 API，而不是另起一套逻辑"
  - "设计 API Key / OIDC 双鉴权、幂等与去重"
  - "要让外部系统安全地触发有副作用的批处理任务"
tags: [api, fastapi, agent, idempotency, oidc, api-key, pb-orders]
related_components: [pb_orders, api-gateway]
---

# 人 + Agent 共用的订单 API

## Context

PB 出件工具原本只有 HTML 表单（上传 PDF/CSV → RQ 任务 → 下载产物）。Agent 想批量操作
只能驱动浏览器，踩过「通途重复订单号未加 `-N`」的坑。2026-10 增加 `/api/v1`，目标不是
「再做一个接口」，而是**同一个业务动作，人和 Agent 都能安全地做**。

## Guidance

1. **唯一服务层**：网页表单与 API 都调 `web/jobs_service.py`（校验上传 → 落盘 → 建 job →
   登记输入 → 入队）。不存在「只有页面能做」的步骤；任务模型、产物、审计天然一致。
2. **鉴权分两条路**：机器用 `sk-` API Key（库里只存 sha256 + 前缀，带 scope、可吊销、
   按 principal 限速）；人/Agent 用公司 OIDC 用户 token（`/userinfo` 5s 超时 + 60s 缓存）。
   机器对机器不走 `client_credentials`（桥未实现）。
3. **API 不认 cookie**：`/api/` 绕过登录闸门与 CSRF，未带 token 返回 JSON 401
   （不是 303 去登录页）——Agent 需要可判定的状态码，而不是 HTML。
4. **幂等两层**：`Idempotency-Key` + 输入 SHA-256 指纹（同键同输入重放、不同输入 409）；
   另有短窗口按输入哈希去重（跳过 failed），避免重复提交产生重复任务。
5. **副作用要留登记**：通途订单号后缀 `-N` 存 `order_number_usage`，建任务时在
   `BEGIN IMMEDIATE` 里预留、worker 成功后回填实际写入值；失败保留预留（号跳过、不重复）。
6. **文档带前缀**：`/api/openapi.json`、`/api/docs`；反代挂 `/pb` 时 `servers` 自动带前缀，
   避免 Swagger 的 Try it out 打到域名根。
7. **一次性历史对齐做成 CLI**：`python -m web.backfill_order_numbers` 从已有产物 xlsx
   回填登记表（默认预演），避免新库第一次自动补发撞历史号。

## Why This Matters

- Agent 与人在同一入口操作，**审计与产物不会分叉**；出问题只需要查一套 job 记录。
- 幂等 + 去重把「网络重试」和「手滑重复点」变成安全操作；比让 Agent 自己判断是否已提交可靠。
- 服务端登记订单号，避免把「查历史后缀」这种易错逻辑留给调用方或人肉 CSV 编辑。
- 401/409/422 都是机器可判定的 JSON 错误，Agent 才能自动重试或停下报告。

## When to Apply

- 已有内部工具需要给 Agent / 脚本开放操作能力时；
- 任务有明确副作用（写 ERP、生成单据），必须可追溯、可重试；
- 需要区分机器身份与员工身份，并分别限权。

## Examples

```bash
# 机器身份
docker compose exec web python -m web.api_keys create --name agent --scopes check,fulfill,read
curl -s https://api.vilavi.cn/pb/api/v1/checks \
  -H "Authorization: Bearer $PB_ORDERS_API_KEY" \
  -F "raw_csv=@新订单.csv" -F "no_stock=SKU-1,SKU-2"
# 202 + Location -> 轮询 /api/v1/jobs/{id} -> 下载 /api/v1/artifacts/{id}/download
```

## Related

- `pb_orders/AGENT_HANDOFF.md` §4.5（接口表、鉴权、幂等与部署命令）
- `pb_orders/docs/reference/server-deployment-architecture.md` §11.6
- `pb_orders/docs/reference/workflow.md` §10（后缀与服务器侧登记）
- `.agents/skills/pb-orders/SKILL.md`（Agent 调用清单）
