---
okf: v0.1
type: Solution
title: sellfox_shipping 可靠性收口与蜴国际面单链路修复（2026-08）
description: 本次会话处理的全部问题记录——分页count、resume并发、证据化结案、蜴国际API、报价展示、赛狐回写、批量面单、async阻塞、参考号重复
timestamp: 2026-08-06
tags: [sellfox-shipping, lizard, vite, submitToPlatform, reliability]
---

# sellfox_shipping 可靠性收口与蜴国际面单链路修复

本文记录 2026-08 一次完整会话中出现的所有问题、根因、解决方案与验证方式，作为后续排查与开发的可复用知识。

## 背景

- 项目：sellfox_shipping（赛狐尾程打单）
- 基线：`origin/main@d6e09b9`，203 tests passed
- 目标：可靠性收口 + 蜴国际面单链路可用 + 赛狐追踪号回写
- 承运商：Vite、蜴国际（Lizard）

## 一、分页与可靠性收口（PR A/B/C）

### 1. 分页 count 放大（PR A）

**现象**：包裹列表分页总数错误，翻页不准确。

**根因**：`count_packages()` 用 `select(func.count())`。当 `date_field=order` JOIN `PackageOrderRow`（一包多单）或 `date_field=label` LEFT JOIN `ShippingLabelRow`（一包多标签）时产生重复行，`count(*)` 统计了放大后的行数。第 1890 行 `.distinct()` 对 `count(*)` 无效——count 已聚合为单一标量。

**修复**：`select(func.count(func.distinct(PackageRow.id)))`（package_repository.py:1851）。

**测试**：多订单/多标签/仅取消标签/有效+取消并存/日期边界/分页一致性，共 9 个。

### 2. resume 并发与幂等（PR B）

**现象**：两个 Agent 可同时对同一 operation 执行 resume，重复调用承运商 API、重复写标签。

**根因**：`resume_label_acquisition()` 只检查状态，无 claim/lease 机制；CLI actor 硬编码 `cli-resume`。

**修复**：
- Migration 0016：`shipping_label_operations` 新增 `claimed_by`/`claimed_at`
- `acquire_resume_lease()`/`release_resume_lease()` — SQLite 原子 lease
- SUCCEEDED 操作幂等返回既有结果
- CLI 增加必填 `--actor`

### 3. UNKNOWN_BLOCKED 证据化结案（PR C）

**现象**：`--note + --confirm` 即可解除阻断，无证据记录。

**修复**：
- Migration 0017：`shipping_label_investigations` append-only 表
- `label-operation-investigate` CLI：仅记录调查，不解除阻断
- `resolve_unknown_blocked()` 必须提供归属于同一 operation 的 `evidence_id`

## 二、蜴国际（Lizard）面单链路修复

### 4. Vite 报价 "warehouse address incomplete"

**现象**：`VITE warehouse address incomplete: missing address1, city, postal_code, phone`。

**根因**：`config.yaml` 的 `warehouses.DANEEY` 地址字段全空。Vite 报价校验要求 name/address1/city/state/postal_code/phone 非空。

**修复**：从蜴国际 `order_adapter.py` 已备案 shipper 地址同步：
- CENTRADE → S0145：389 Route 10 Unit R, East Hanover, NJ 07936
- DANEEY → S0143：10812 Fallstone Rd, Suite 402, Houston, TX 77099

**教训**：`app.py` 的 `BASE_DIR = Path(__file__).parent` 指向 `sellfox_shipping/` 子目录，config 需覆盖**该目录**的 `config.yaml`，不是工作区根目录。

### 5. 蜴国际报价不展示（只显示 Vite）

**现象**：点"获取 VITE + 蜴国际 报价"，只返回 Vite 报价。

**根因**（两个 bug）：
1. `_get_lizard_rate()` 始终 `return None`（调用后丢弃结果）
2. `_LIZARD_CA_ZONE["DANEEY"]=1` 导致 API 不返回有效报价（S0143 不在 CA zone）

**修复**：
- `_get_lizard_rate` 改为返回最佳报价
- `_LIZARD_CA_ZONE["DANEEY"]` 改为 0
- 保持路由逻辑：按 `routing_result` 展示建议承运商报价

**教训**：改动前先确认原始设计意图（路由选承运商展示），不要轻易改成双列。

### 6. 承运商未启用，下拉只有 VITE

**现象**：创建面单下拉只有 VITE，无蜴国际。

**根因**：`config.yaml` 的 `carriers.vite/lizard` 为 `enabled: false`（main 分支默认值）。`_get_enabled_carriers()` 只返回 enabled 的承运商。

**修复**：将 vite/lizard 设为 `enabled: true`。

### 7. 蜴国际 API 传参与解析问题

**现象**：
1. 创建面单报"限制发货"
2. 标签就绪但报 `label ready but missing label_url`

**根因**：
1. `weight_unit_type="1"`（声明 LBS/Inches）但实际传 KG/CM 值 → 蜴国际拒绝
2. 实际 API 返回 `labels` 为**数组**，代码按**对象**解析 → 取不到 `label_url`

**修复**：
- `weight_unit_type` 改为 `"2"`（KG/CM）
- 新增 `_labels_as_dict()` 兼容数组/对象两种形状

**验证**：真实蜴国际面单创建成功（订单 M6180202608066073915，追踪号 875397181317）。

### 8. 蜴国际面单取消接口未接线

**现象**：取消蜴国际面单报 `Cancel not supported for carrier 'lizard'`。

**根因**：`cancel_label()` 只实现了 Vite 分支；蜴国际 `cancel_order` 方法已在 api_client 实现但未接线。

**修复**：`cancel_label` 新增 lizard 分支，调用 `/api/svc/cancelOrder`。

### 9. 蜴国际订单错误时静默空等

**现象**：创建面单后蜴国际订单报错，但系统空等 180 秒只报"标签未就绪"。

**根因**：`ship_package` 轮询 getLabel 不检查 `logistics_err` 字段，订单进入错误状态仍盲目轮询到超时。

**修复**：检测到 `logistics_err` 立即抛 `LizardApiError` 展示承运商真实错误。

### 10. 参考号重复

**现象**：蜴国际端取消订单后，重新创建仍报 `参考号重复，请更换参考号重新下单`。

**根因**：蜴国际**取消的订单仍保留参考号**（package_sn）。代码每次都把 `package_sn` 当 `reference_no`，所以重复下单被拒。

**修复**：参考号改为 **generation 作用域**后缀策略：
- generation 1 → 基础参考号 `{package_sn}`
- 后续 → `{package_sn}-1`、`-2`、`-3`（按同事指导）
- createOrder/getLabel/cancelOrder 全链路一致使用

### 11. 面单记录新增"派生包裹号"列

**需求**：在面单记录表格的追踪号后增加"派生包裹号"列，记录实际使用的尾缀参考号；Vite 无此情况留空。

**实现**：
- Migration 0018：`shipping_labels` 新增 `derived_reference_no` 列
- 创建/恢复蜴国际面单时记录实际使用的派生参考号
- Vite 面单此列为空

### 12. 创建面单自动释放卡住的 operation

**需求**：遇到 `active label operation exists`（如 LABEL_PENDING）时自动释放并重试，避免手动清理。

**实现**：
- `release_active_label_operation()`：释放 RESERVED/ACCEPTED/LABEL_PENDING/SUCCEEDED → CANCELLED
- **UNKNOWN_BLOCKED 不自动释放**（承运商可能已创建订单，结果不确定，必须走证据化结案）
- 已有有效面单仍阻止重复创建（"已存在有效面单"）

## 三、赛狐追踪号回写

### 13. 有效面单追踪号写回赛狐

**需求**：将包裹**有效（未取消）面单记录**的追踪号写回赛狐，让赛狐 UI 显示真实运单号。

**API**：`POST /api/packageShip/submitToPlatform.json`，传参 `{shopId, orderId, trackNo, carrierName, items:[{orderItemId, quantity}]}`。赛狐技术支持：所有字段选填，报错缺什么补什么。

**关键缺口**：`.env` 配 SELLFOX_APP_ID/SECRET 时走 `DirectSellfoxClient`，但该客户端**没有 `submit_to_platform`**，真实提交会崩。

**实现**：
- `DirectSellfoxClient` 新增 `submit_to_platform`/`fetch_package_detail`
- `SubmissionService.submit_label_tracking()`：从有效面单取追踪号 → prepare → 真实提交
- 包裹详情页新增"回写面单追踪号到赛狐"按钮

**历史探针**：P2AMA9T726848 之前走代理 401；直连官方 openapi.sellfox.com 可能绕过。

## 四、Transactions 批量创建面单

### 14. 批量操作栏新增"创建面单"

**需求**：Transactions 页签勾选包裹后，批量创建面单。

**实现**：
- `POST /api/packages/batch-create-labels`：`carrier: auto/vite/lizard`，逐包独立 try/except
- packages.html 批量栏新增按钮 + Modal（承运商选择 + 操作者 + 逐条结果）

## 五、运行时问题

### 15. async 端点阻塞事件循环导致页面卡死

**现象**：点创建面单后页面卡住不动，刷新无反应。

**根因**：`async def` 端点内直接调用**同步阻塞**的代码（承运商 HTTP）。蜴国际创建面单轮询 getLabel 最长 **180 秒**，期间阻塞整个 FastAPI 事件循环，所有请求（含刷新）挂起。

**修复**：用 `starlette.concurrency.run_in_threadpool` 将阻塞调用移入线程池：
- `package_create_label_form`（create-label）
- `package_fetch_rates`（fetch-rates）
- `package_submit_label_tracking_form`（submit-label-tracking）
- `batch_create_labels`（batch-create-labels）

**教训**：FastAPI `async def` 端点中调用同步 HTTP/长轮询代码会阻塞事件循环，必须用 `run_in_threadpool` 或改成 `def`（FastAPI 自动线程池化）。

## 六、批量打印与批量操作栏优化

### 16. 批量操作栏按钮顺序与动态禁用

**需求**：
1. "创建面单"按钮移到"批量打印"左侧，顺序：创建面单、批量打印、导出 Excel
2. 勾选的包裹**全部有有效面单**时，创建面单按钮灰色禁用（防止重复创建）

**实现**：
- packages.html 重排 batch-bar 按钮顺序
- 复选框加 `data-has-label` 属性（依据 `label_created_at` 判断是否有有效面单）
- `updateBatchBar()` 检测全部选中包裹都有面单 → 禁用创建面单按钮

### 17. 批量打印以面单数量为锚点，缺失背贴空白页占位

**需求**：三种打印模式（背贴 / Label面单 / 面单+背贴）都以**面单数量**为准。勾选包裹中面单数量 N → 背贴也打印 N 张；缺失背贴用**空白页占位**保持顺序；面单+背贴按包裹顺序先背贴后面单，背贴缺失则空白页。

**实现**（app.py `batch_print_packages` 重写）：
- **锚定逻辑**：只处理有有效（非取消）面单的包裹，这些确定打印数量
- 背贴生成失败或缺失 → `_blank_or_pdf()` 生成 A4 空白页占位（不跳过、不拒绝）
- 无面单包裹不参与打印
- 移除之前的 422 硬拒绝与"仅打印有效包裹"回退逻辑（被空白占位取代）

**验证**：选择 `[有面单 + 无面单]` 包裹：
- 背贴 → 1 页；Label → 1 页；面单+背贴 → 2 页

## 七、总结与建议

### 已修复
| 类别 | 问题 | 文件 |
|------|------|------|
| 分页 | count 放大 | package_repository.py |
| 并发 | resume 无 lease | package_repository.py / label_service.py |
| 结案 | 无证据记录 | migration 0017 |
| 报价 | Lizard 不返回 + ca_zone | app.py |
| 承运商 | enabled=false | config.yaml |
| API | weight_unit_type / labels 数组 | order_adapter.py / api_client.py |
| 取消 | 蜴国际未接线 | label_service.py |
| 空等 | 不检查 logistics_err | api_shipment.py |
| 参考号 | 重复被拒 | label_service.py |
| 派生列 | 无派生包裹号 | migration 0018 |
| 卡死 | async 阻塞 | app.py |
| 批量操作栏 | 按钮顺序/动态禁用 | packages.html |
| 批量打印 | 锚定面单/空白占位 | app.py |

### 设计原则沉淀
1. **真实副作用 API 用显式确认**：submitToPlatform、创建面单都要求用户显式动作。
2. **UNKNOWN_BLOCKED 不自动释放**：承运商结果不确定时必须人工证据化结案。
3. **async 端点不调用同步阻塞代码**：HTTP/长轮询必须线程池化。
4. **取消的订单仍占用参考号**：蜴国际需要唯一参考号（后缀策略）。
5. **先确认设计意图再改动**：报价展示改双列前应先理解路由选承运商的原始逻辑。
6. **打印以面单为锚点**：背贴/面单/双模式数量一致，缺失项空白占位保持顺序。
7. **HTTP 头只能用 latin-1**：中文错误信息不能放响应头，用数量或 JSON body 返回。
