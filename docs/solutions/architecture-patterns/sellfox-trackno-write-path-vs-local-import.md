---
title: 赛狐 trackNo 写路径 vs 本地 import vs 通途/自动推送
date: 2026-07-20
category: docs/solutions/architecture-patterns/
module: sellfox_shipping
problem_type: architecture_pattern
component: documentation
severity: high
applies_when:
  - "Colleague or agent asks how to write tracking / trackNo back to Sellfox"
  - "Assuming a separate OpenAPI update-trackNo-only endpoint under 订单处理"
  - "Local lizard-import shows FedEx numbers but Sellfox packageDetail still shows trackNo=packageSn"
  - "Comparing Tongtu Amazon push vs Sellfox submitToPlatform / sales-platform autopush"
  - "Handoff uses Tongtu P814 reference codes that map to has_shipped Sellfox packages"
symptoms:
  - "Expectation that write tracking to Sellfox is distinct from submitToPlatform / Amazon push"
  - "Local lizard-import updates SQLite only; Sellfox packageDetail still shows trackNo=packageSn placeholder"
  - "Live submitToPlatform via sellfox-api-proxy returned HTTP 401"
  - "Autopush to sales platforms is OFF while Tongtu still writes Amazon"
root_cause: inadequate_documentation
resolution_type: documentation_update
related_components:
  - development_workflow
  - tooling
tags:
  - sellfox-shipping
  - trackno
  - submit-to-platform
  - openapi
  - lizard-import
  - tongtu
  - package-detail
  - api-boundary
---

# 赛狐 trackNo 写路径 vs 本地 import vs 通途/自动推送

## Context

尾程打单闭环里，「追踪号」出现在三处，语义不同，易被同事 Agent 混为一谈：

| 位置 | 含义 | 本仓库现状 |
|------|------|------------|
| 本地 SQLite `tracking_number` | `lizard-import` / `ImportLizardTrackingService` 写入 `PackageRepository` | 已实现；**不**调赛狐写 API |
| 赛狐详情 `packageDetail.logistics.trackNo` | 运营在赛狐 UI / 详情看到的运单号 | 仅本地 import **不会**更新；常仍为 packageSn 占位或 null |
| 销售平台（Amazon 等） | 通途写回；或赛狐「自动推送」/ `submitToPlatform` 可能副作用 | 业务：通途仍写平台；赛狐自动推送已关 |

OpenAPI「订单处理」下文档化、请求体含 `trackNo` 的写入口，目前可见的是 `POST /api/packageShip/submitToPlatform.json`（见 `SELLFOX_API/docs/api-reference/订单/订单处理/提交平台.md`：`PackageSubmitToPlatformOpenQO` 含 `trackNo`，响应 `PackageSubmitAmazonResultDTO`）。**未**另见「只改物流、不提交平台」的第二套官方 API。

本模块 wire 映射在 `sellfox_shipping/submission_service.py`：`canonical_to_wire_body` → `shopId` / `orderId` / `carrierName` / `trackNo` / `items`，经 `SellfoxClient.submit_to_platform` 发出。边界与探针结论见 [`sellfox_shipping/docs/research/submit-to-platform-vs-autopush-2026-07-20.md`](../../../sellfox_shipping/docs/research/submit-to-platform-vs-autopush-2026-07-20.md)。

2026-07-20 同事样例（`sellfox_shipping/数据源/.../20260720`，gitignore）：通途 `P#` 参考编号 → 映射赛狐 `has_shipped` 三票；remapped 本地 import **3/3 persisted**；赛狐详情仍占位/空。对 `to_process` 票 live 探针：代理对 `submitToPlatform` 返回 **HTTP 401**，intent scope → `UNKNOWN_BLOCKED`——**尚不能**证明「关自动推送下 submitToPlatform 能否只填赛狐号」。P1A–P1C 代码已合入 PR #96；20260720 文档在 PR #97。

## Guidance

1. **不要把 `lizard-import` 等同于赛狐 UI 的 `trackNo`。**  
   `ImportLizardTrackingService`（`sellfox_shipping/lizard_batch.py`）只更新本地 `PackageRepository.tracking_number`，类注释写明不调用 `submitToPlatform`。只读对照（如 `P2AJA9T726203`）：本地已有真实 FedEx 号，赛狐 `trackNo` 仍可为 packageSn 占位且 `submitTime=null`。

2. **「只写赛狐、暂不推 Amazon」尚无第二套已文档化的 API。**  
   候选仍是 `submitToPlatform`。自动推送关闭后，对 Amazon / 通途是否仍有副作用，**必须以具备写权限的代理 Key 做 live 调用 + 回读 + 人工核对后再下结论**。勿把 dry-run READY 当成赛狐侧已写入。

3. **永远不要对 `has_shipped` 历史样例真调 `submitToPlatform`。**  
   20260720 三票已是 `has_shipped`，Amazon 侧通途已写 Shipped——真调违反项目规则，且无法安全观察「仅填号」行为。

4. **蜴国际打单生产默认仍走 Excel 本地闭环**（导出 → 人工上传 → 返回表 import → 对账），不依赖本系统推销售平台。`SubmissionIntent` 骨架保留备用；Web 不开放真调按钮。

5. **401 / `UNKNOWN_BLOCKED` 后勿盲重放。**  
   先确认代理 Key 对 `submitToPlatform` 有写权限（只读 `packageDetail` / `getPackagePage` 可用不等于可写）；再解阻或新建 intent，另选 **`to_process`** 测试票，经用户确认范围后再 `--no-dry-run`。

## Why This Matters

- **误判履约状态：** Agent 若见本地 DB 有真实运单号，会以为赛狐 UI / 平台已同步；运营实际仍看到占位号，排查会指向错误系统。
- **双写与合规风险：** 通途已写 Amazon、赛狐自动推送关闭时，误用 `submitToPlatform` 可能造成平台侧重复或未知副作用；在未验证「关推送仍只填号」前，不能当「只写赛狐」捷径。
- **写路径假阳性：** dry-run 与 wire 预览通过，只证明本地 Intent 组装正确；401 说明代理权限/网关挡住了真写，赛狐侧 `trackNo` 不会变。
- **样例污染：** 通途 `P#` ≠ 赛狐 `packageSn`；未 remap 的 lizard 返回表无法匹配本地库。历史 `has_shipped` 票上的占位 `trackNo` 不能当回写测试数据。

## When to Apply

- 排查「本地已有追踪号但赛狐详情仍空/占位」时
- 设计或评审「只写赛狐 trackNo」能力、或评估是否调用 `submitToPlatform` 时
- 处理 `lizard-import` / Excel 对账 / 通途参考编号映射时
- 对任意包裹准备 `packages-submit-intent --no-dry-run` 之前（尤其 status=`has_shipped` 或 intent=`UNKNOWN_BLOCKED`）
- 向同事解释自动推送关闭 vs 通途写平台 vs 本模块 Intent 骨架时

## Examples

### 反例：把本地 import 当成赛狐已填号

```text
# 本地：ImportLizardTrackingService → PackageRepository.tracking_number = 382619179937
# 赛狐只读：packageDetail.logistics.trackNo 仍 = P2AJA9T726203（占位）
# 错误结论：「已经写进赛狐了」
# 正确结论：仅本地 DB；UI 可见号需要另经文档化写路径（候选 submitToPlatform，live 未证实）
```

### 正例：三层分离（20260720 样例口径）

| 层 | 20260720 三票观察 |
|----|-------------------|
| 通途 / Amazon | 已 Shipped（通途写平台） |
| 本地 import（remapped） | 3/3 persisted，真实 FedEx 物流单号在 SQLite |
| 赛狐详情 trackNo | 仍占位或 null → **禁止**对这些 `has_shipped` 票 submitToPlatform |

### 正例：wire 与 OpenAPI 对齐（代码路径）

`sellfox_shipping/submission_service.py` 中 `canonical_to_wire_body` 将内部 `tracking_number` 映射为官方字段 `trackNo`（另含 `shopId`、`orderId`、`carrierName`、`items`）。OpenAPI 请求 schema：`PackageSubmitToPlatformOpenQO`；响应：`PackageSubmitAmazonResultDTO`（`SELLFOX_API/docs/api-reference/订单/订单处理/提交平台.md`）。

### 正例：live 受阻时的安全停手

```text
packages-prepare-submit / packages-submit-intent（dry-run）→ READY，wire 含 trackNo
packages-submit-intent --no-dry-run → 代理 HTTP 401
→ intent/attempt UNKNOWN，scope UNKNOWN_BLOCKED，回读 trackNo 仍 null
→ 结论：写路径受阻；勿盲重放；先修 Key/权限，再换 to_process 票探针
```

### Related

- [`sellfox_shipping/docs/research/submit-to-platform-vs-autopush-2026-07-20.md`](../../../sellfox_shipping/docs/research/submit-to-platform-vs-autopush-2026-07-20.md) — 术语、探针协议、结论位
- `sellfox_shipping/lizard_batch.py` — `ImportLizardTrackingService`（仅本地）
- `sellfox_shipping/submission_service.py` — `canonical_to_wire_body` / `SubmissionService`
- `SELLFOX_API/docs/api-reference/订单/订单处理/提交平台.md` — OpenAPI
- PR #96（P1A–P1C 已合）；PR #97（20260720 文档）
- 早期架构：[`sellfox-shipping-research-and-architecture.md`](sellfox-shipping-research-and-architecture.md)；代理：[`sellfox-api-proxy-design.md`](sellfox-api-proxy-design.md)
