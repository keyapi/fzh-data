---
okf: v0.1
type: Reference
title: 供应链复审与人工升级：能自动判的不要甩给人
date: 2026-10-30
category: workflow-issues
module: supply_chain
problem_type: workflow_issue
component: tooling
severity: high
applies_when:
  - "准备把低置信/待确认队列交给业务或老板"
  - "多 Agent 并行做 A/B/C 数据任务"
  - "复审发现“待审 0”但仍有大量低置信/隔离行"
tags: [review, human-escalation, agent-orchestration, naming, evidence]
---

# 供应链复审与人工升级：能自动判的不要甩给人

## Context

这次 A/B/C 反复出现同一类浪费：系统已经能取到 EN SO/DN、通途 2025/2026 订单、2026/180 天销量、库存仓，却把几十上百行「低置信」直接丢给用户。用户的原话很直接：

> 如果 EN SO、DN、通途订单、库存都指向一个归属，那还有疑问再说？人如果去查去判断，不也是依赖这些你能取到的数据么？

人工审核不是数据搬运。**能用数据判的，系统必须自己判；只有真冲突/真缺证才升级。** 这条适用于 A/B/C，也适用于后续 D 和财务。

## Guidance

### 1. 先自动裁决，再谈人工

证据顺序固定：

1. 已证销售/订单/DN（按正确形态）；
2. 2026 年销量、近 180 天销量；
3. 库存仓池（波兰 / 美东USNJ / 美中USTX）；
4. 只有「美东USNJ 与美中USTX 两侧都有库存，且订单/DN 无法决胜」才是真冲突；
5. 全部没有才是 `no_evidence`，不是 0。

每行必须输出 `auto_resolution / resolution_basis / market_confidence / human_required`；`human_required=是` 只能留给真冲突或真缺证。

### 2. 人工审核包只放「人该看的」

- 不要把 2,931 行主表或 26 个 sheet 丢给业务；
- 从全量里抽：真冲突、真共享、真缺失组件、老产品确认；
- 每行留 `人工结论 / 备注`，填「确认/不确认/改归属/需补证/观察」；
- 附一页「说明」写清哪些已自动处理、哪些已忽略（如 0 库存）。

实测收敛：B 的 89 条库存投放自动判后人工 **0**；C 的 CG 未知 47 → 2 → 0；254 行里 212 行 0 库存直接忽略；最终只剩 2 个真共享、20 条组件记录、151 个老产品。

### 3. 命名是硬规则

- 只用 `美东USNJ` / `美中USTX`；禁止 `East/Central`（美东公司名 CENTRADE，极易混）。
- 共享附表、证据表、报告正文都要扫；旧市场原值可保留但单独列。
- 每次交付前做全表文本扫描，命中 0 才算通过。

### 4. 复审状态要分层

- `worker 完成 ≠ 评审完成 ≠ 验收通过`；
- 每轮新版本，不覆盖旧版本；评审意见要带文件/行号/可复现数字；
- `accept-with-findings` 的 P1/P2 必须进下一版，P3 可记录后修；
- 未通过独立复审的 artifact 只能作「候选/附件」，不能称已验证。

### 5. 多 Agent 操作要点

- 终端上下文会满（1M tokens）；worker 报 API 400 时先 `/clear` 或新开 worker，不要把任务重派给同一爆上下文会话；
- worker 写脚本但跑不了（分类器/网络）时，工头自己 `uv run` 跑并回贴 traceback，不要干等；
- 黄色问号/权限提示要主动看终端；涉及业务口径的选择（如“成品可替代皮壳”）按已确认规则选，不要让它挂着；
- loop 只在有明确任务队列时开；空闲就停，避免空转。

### 6. 前后冲突要显式记录

这次被推翻的结论必须写进文档，而不是留在对话里：

- 「不凭库存仓反推」→ 库存仓是投放证据；
- 「共享码取第一个」→ 全候选/共享池；
- 「缺成品行=partial」→ 单一形态正常、成品可替代皮壳；
- 「套件是未知产品」→ 拆 Product Bundle；
- 「0 库存也隔离」→ 0 库存忽略；
- 「CG 分仓累加」→ 只取 `warehouse_id='CG'`；
- 「153/194 与 KS0001 共享」→ 源 SKU 专属，分开处理。

## Why This Matters

- 把可自动判的行丢给人，会消耗业务时间，也会让「待审 0」变成假象：数字清零了，但没人真正核过。
- 人工只该做三件事：确认业务例外、批准高影响动作、提供系统拿不到的外部事实。
- 复审分层能防止「worker 说完成」被误当成「已验证」，也能让每轮返修可回放。

## When to Apply

- 任何准备输出「待确认/低置信/异常清单」的场景；
- 多 Agent 并行做数据管道；
- 业务方问「为什么这个还要我看」。

## Examples

- B r10：89 条 stock_placement 自动判 89 / 冲突 0 / 缺证 0，`human_required=0`；依据是 2026/180 天销量、2025/2026 订单、DN、库存仓。
- C v13：254 行中 212 行 0 库存忽略，21 行补证，1 行拆包组装 29 个，20 行 `component_partial_nonblocking`，`blocking=false`。
- C v14：KS0248 153/194 的库存源 SKU 是 No/B 专属，零库存共享码不阻塞，2 行假 partial 归零。

## Related

- `docs/solutions/architecture-patterns/supply-chain-a-b-c-data-pipeline.md`
- `docs/solutions/best-practices/sku-normalization-uom-sets-split-package.md`
- `docs/solutions/best-practices/multi-agent-rework-review-status-separation.md`
- `docs/solutions/workflow-issues/orca-multi-agent-automation-claims-and-quota.md`
