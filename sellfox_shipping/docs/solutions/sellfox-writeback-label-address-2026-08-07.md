---
okf: v0.1
type: Solution
title: 回写赛狐追踪号 + 蜴国际发货地址 — 全链路排查记录（2026-08-07）
description: submitToPlatform/quickOutbound 回写赛狐的完整排查（quantity/错误体/4xx分类/scope解除）、蜴国际面单发货地址错误（S0143借用→按仓库推导→蜴国际可能忽略）、分支叠加问题
timestamp: 2026-08-07
tags: [sellfox-shipping, submitToPlatform, quickOutbound, lizard, shipper-address, scope]
---

# 回写赛狐追踪号 + 蜴国际发货地址 — 全链路排查记录

## 背景

赛狐尾程打单：蜴国际生成面单 → 把追踪号写回赛狐包裹（让赛狐详情显示正确 trackNo）。
本次会话集中排查「回写」与「蜴国际面单发货地址」两大问题。

## 一、回写赛狐追踪号

### 现象
点击「回写面单追踪号到赛狐」反复失败，报错不断变化。

### 排查链（每个阶段发现的真实原因）

1. **`_get_client` NameError**：Web 端点调用 cli.py 私有函数，app.py 作用域没有 → 提取共享工厂 `get_sellfox_client()`（sellfox_client.py），app/cli 复用。
2. **HTTP 400 但看不到原因**：`DirectSellfoxClient._post` 用 `raise_for_status()` 丢失响应体 → 捕获 4xx 响应体，赛狐真实 `msg` 进 http_summary。
3. **quantity 类型不符**：官方 schema 要求 string，代码发 int → 转 `str(int(...))`。
4. **HTTP 400 全锁 scope**：任何异常都 `UNKNOWN_BLOCKED` → 4xx（赛狐明确拒绝，无副作用）= FAILED 不锁 scope；5xx/超时/网络 = UNKNOWN 锁 scope。
5. **scope 永久锁死**：无解除路径 + 旧 UNKNOWN intent 卡「cannot submit」→ 新增 `submission-scope-unblock` CLI（解除 scope + 重置 intent 为 READY）。
6. **submitToPlatform 拒绝**：错误体显示 **`仅支持未发货订单提交平台`**（订单状态 Unshipped 但包裹 apply_track_no，赛狐判定口径不明）。
7. **发现 quickOutbound**：`POST /api/packageShip/quickOutbound.json`（快速出库），入参 `packageSn+carrier+trackNo+shipmentType=0`（仅提交平台不扣库存），多平台订单写回。已接入客户端/service/CLI/Web。
8. **quickOutbound 也拒**：`该订单不需要提交平台`（Amazon FBM 订单，非多平台订单）。

### 当前结论
- **submitToPlatform**：Amazon/FBM 专属，但实测被拒（"仅支持未发货订单提交平台"）。
- **quickOutbound**：多平台订单（Walmart/TikTok）写回路径。
- 两类接口对这个 Amazon FBM 订单都返回"不需要提交平台"——需与赛狐确认正确写回方式（是否改用 applyTrackNo 物流下单发货，或订单类型确实无需提交）。

## 二、蜴国际面单发货地址错误

### 现象
CENTRADE（美东/NJ 仓）包裹创建面单，打印标签显示 TX 地址（Houston / Missouri City TX）。

### 根因
- 蜴国际 createOrder 的 `shipper_address` 来自 `shipper_address_for_code(shipper_code)`，`SHIPPER_CODE_DEFAULT="S0143"`（TX）。
- **蜴国际没有"发货代码"概念**——S0143 那套是 VITE 表格的概念，被代码借用，概念不对。
- 创建面单（create_label 蜴国际分支）没传 shipper_code → 恒用默认 S0143（TX）。

### 修复
- 新增 `build_shipper_address_from_warehouse(warehouse_name, warehouses_cfg)`：从 `config.yaml.warehouses[仓库].address` 推导 createOrder shipper_address（**fail-closed**：仓库缺失/地址不完整报错，不用默认）。
- `create_label` 蜴国际分支按 `package.logistics.warehouse_name` 传参。
- config `warehouses.CENTRADE` 更新为美东真实地址（Overstock.com, Centrade Inc / 389 Route 10 Unit R, East Hanover NJ 07936 / 7327622442 / service@icentrade.com）。
- 包裹详情页显示「发货仓库」。

### ⚠️ 仍未解决
**实测蜴国际可能忽略请求内的 `shipper_address`，改用其账户/产品配置的发货地址**（打印仍显示 Missouri City TX 77489 = 蜴国际账户地址，与注册表 S1261 一致）。创建面单用 `sm_code="FedEx-Ground-J-TX"`（TX 产品）。
→ **需要与蜴国际确认**：
1. createOrder 的 `shipper_address` 是否生效？
2. 是否有 CENTRADE/NJ 对应的产品（sm_code）？
3. 蜴国际账户发货地址能否配置为 NJ？

## 三、运费试算显示（用户决策）

- 用户明确要求：**运费试算只显示一条（路由建议承运商）**，不是两家卡片。
- 蜴国际无报价时显示原因（如"发货地区域不匹配"），不再静默 None。
- 另修复 ca_zone CENTRADE=0（此前漏掉导致蜴国际报价全部"发货地区域不匹配"）。

## 四、过程教训：问题为何"重复发生"

**根因是分支叠加 + 修复未合并固化**：
- 同一批修复分散在 PR #153/#154/#155 和当前分支，运行代码只含部分修复。
- ca_zone 修复在 PR #154，当前分支没合并 → CENTRADE 报价一直失败。
- 多次"修了又出现"实为**同一修复从未真正合并进运行代码**。

**教训**：修复要合并进一个分支并提交固化，不要跨多个未合并分支分散 + 工作树手动重放。

## 五、当前状态与待办（给新对话）

- **PR #158**（fix/sellfox-submit-quantity-errorbody）：本次全部改动已提交。PR #153/#154/#155 未合并（内容已被 #158 部分覆盖）。
- **待办**：
  1. 与赛狐确认正确写回 API（submitToPlatform/quickOutbound/applyTrackNo）。
  2. 与蜴国际确认 shipper_address 是否生效 + NJ 产品/账户配置。
  3. 同步 8 月包裹，重新验证。
- 测试基线：293 passed。

## 相关文件
- `sellfox_shipping/submission_service.py` — quickOutbound / 4xx 分类
- `sellfox_shipping/carriers/lizard/order_adapter.py` — build_shipper_address_from_warehouse
- `sellfox_shipping/carriers/lizard/api_shipment.py` — ship_package shipper_address
- `sellfox_shipping/label_service.py` — create_label 蜴国际分支
- `sellfox_shipping/package_repository.py` — resolve_submission_scope_block
- `SELLFOX_API/docs/api-reference/订单/订单处理/提交平台.md`、`多平台/订单/快速出库.md`
