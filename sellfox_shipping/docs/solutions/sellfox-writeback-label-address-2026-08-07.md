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

### 2026-08-10 已与蜴国际确认根因（决定性）
**蜴国际产品（sm_code）↔ 发件人（已备案地址）关联绑定；createOrder 的 `shipper_address` 字段无效——面单 FROM 地址由所选产品绑定的发件人决定。**

- 蜴国际后台「选择发件人」下拉框显示的绑定关系：
  - `FedEx-21-AHS-USEA` → Qiang Ma, 389 STATE ROUTE 10 UNIT R, **East Hanover NJ 07936**（美东 NJ ✓）
  - `FedEx-Ground-20-OS-TX` → A_TX_77091, 10812 Fallstone Rd, **Houston TX 77099**（德州 TX ✓）
  - `FedEx-Economy-10-USEA` → EHN1#3232, 1450 Mission Blvd, **Ontario CA 91761**（加州 CA，非 NJ）
- 实测验证：传 NJ 已备案地址（S0656），选 TX 产品打印 Missouri City TX；选 `FedEx-Economy-10-USEA` 打印 Ontario CA——均非所传地址。**shipper_address 被完全忽略。**
- **代码无法控制 FROM 地址；正确做法是选对产品（产品决定发件人）。**

**⚠️ 当前卡点：`FedEx-21-AHS-USEA`（绑定 NJ 发件人的产品）已下线（渠道已关闭），NJ 暂无可用产品。**
- ratesv2 不再返回该产品；createOrder 报 `400 FedEx-21-AHS-USEA 物流渠道已关闭`（已与蜴国际确认，非代码问题）。
- `FedEx-Economy-10-USEA` 可用但绑定 Ontario CA（非 NJ）。
- **修复路径（蜴国际侧）**：① 重新开通 `FedEx-21-AHS-USEA`；或 ② 把 NJ 发件人（Overstock.com, Centrade Inc / 389 STATE ROUTE 10 UNIT R, EAST HANOVER NJ 07936 / 7327622442）绑定到另一个可用美东产品。

**代码侧尝试（2026-08-10）已还原**：曾实现 `build_shipper_address_from_warehouse` 按仓库映射已备案地址 + 区域感知产品选择 + 下拉框区域过滤，但因 ① 蜴国际忽略 shipper_address、② NJ 产品下线，无法解决，已 `git restore` 还原，未提交。

**待实现（后续，本次不做）：仓库 → 下拉框固定服务类型（warehouse → fixed sm_code）**。
- 一旦蜴国际开通可用 NJ 产品，代码可按仓库映射默认产品：CENTRADE →（蜴国际确认后的 NJ 产品）、DANEEY → `FedEx-Ground-20-OS-TX`。
- 注意 `FedEx-21-AHS-USEA` 已下线，勿再映射；`FedEx-Economy-10-USEA` 绑定 Ontario CA，不适合 NJ。
- 当前保持下拉框列出全部产品、由人工选择；不做区域过滤（用户决策）。

**备注**：S0656/S0795 备案人是 Qiang Ma/1234567890，与业务想要的 Overstock.com, Centrade Inc./7327622442 不同；若必须打印业务名字，需在 Lizard 后台把该地址备案成业务名（属 Lizard 侧）。

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
- **蜴国际发货地址事项（2026-08-10）已与蜴国际确认**：产品↔发件人关联绑定、`shipper_address` 无效、`FedEx-21-AHS-USEA` 已下线。**当前卡点：NJ 无可用产品，需蜴国际开通 NJ 产品后，再实现「仓库→固定服务类型」**（本次不做）。
- **待办**：
  1. 与赛狐确认正确写回 API（submitToPlatform/quickOutbound/applyTrackNo）。
  2. 等蜴国际开通 NJ 产品 → 实现仓库→下拉框固定服务类型（见上节"待实现"）。
  3. 同步 8 月包裹，重新验证。
- 测试基线：293 passed。

## 相关文件
- `sellfox_shipping/submission_service.py` — quickOutbound / 4xx 分类
- `sellfox_shipping/carriers/lizard/order_adapter.py` — build_shipper_address_from_warehouse
- `sellfox_shipping/carriers/lizard/api_shipment.py` — ship_package shipper_address
- `sellfox_shipping/label_service.py` — create_label 蜴国际分支
- `sellfox_shipping/package_repository.py` — resolve_submission_scope_block
- `SELLFOX_API/docs/api-reference/订单/订单处理/提交平台.md`、`多平台/订单/快速出库.md`
