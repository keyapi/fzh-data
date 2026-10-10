---
okf: v0.1
type: Research
title: Amazon FBA 同步缺口只读候选与源码边界
description: 保留 89 个原生账户订单缺口，验证候选字段覆盖、账户键碰撞和零数量风险，不执行同步或导入。
tags: [amazon, fba, sync, technical-validation]
---

# FBA 同步缺口技术验证

2026-10-10，只读既有通途 8 月购买日快照、EN 同范围订单、渠道账号快照及私有生产 `order_sync.py`。复用既有数据，不重新扫全商户 API，没有创建或更新 EN 记录。

## 原生范围守恒

既有 2,137 个 `(account, order id)` 订单，2,048 个精确连接成功，89 个账户订单范围缺口。候选保留全部 89 单、92 子件，不能称为 89 个全局订单号缺失：其中一单在 EN 另一账号下有同号订单。

| 验证 | 计数 | 解释 |
|---|---:|---|
| 当前 Channel Account 存在 | 89 | 仅当前配置；不证明历史调度配置 |
| 身份与正数量字段完整 | 88 | 可用于技术证据连接，未验证真实导入 |
| 子件零数量待核 | 1 单 | 零数量保留；不能按源码默认改成 1 |
| EN 另一账号同号 | 1 | 账户键冲突，禁止按全局订单号补单 |
| 全量同步字段缺失 | 89 | 已脱敏快照不可直接用于生产创建 |
| 已导入 | 0 | 所有候选 `write_action=none` |

## 可复现源码问题

私有源码 `_process_fba_order`（247 行起）通过 `order_id_code=orderId` 查询既有记录，没有加入 `account`，命中后调用更新。实际两账户共享订单号的记录证明此键不足以区分账户。下一技术修复应在生产应用的测试中重现两账户同号，再设计带账户的幂等身份及旧键兼容迁移；本数据仓库没有部署或改写生产应用。它可解释账户范围缺失风险，历史具体失败原因仍需同步日志。

`_process_fba_order_items`（695 行起）使用 `quantityPurchased or 1`，将明确的零数量转换成 1。本候选一单的第二子件为零数量，应核查该子件取消/调整语义后再确定处理规则，不自动计入成本。

`_sync_fba_orders`（163 行起）按每日 purchase-date 窗口分页，不包含账户白名单过滤；每条处理异常会记录 Error Log，取页异常会结束该日期分页。账户当前存在和源码没有白名单，不足以证明历史调度跑过或分页完整。其余缺口具体原因仍需调度及异常日志证据，不能归因于渠道账号漏登记或财务未确认。

## 不执行回填的字段边界

私有上游快照仅含 `orderId/account/purchaseDate/currency/salesChannel/orderItem`。全部缺少 `paymentsDate/totalItemPrice/totalShippingPrice`，子件亦缺部分税、重量字段。生产 `_create_fba_order`（376 行起）读取这些字段，缺失货币总额会默认 0，随后还调用汇率/物料匹配等函数。不得将精简探针伪装成完整导入数据，也不能伪造零金额。

新增纯函数 `fba_sync_gap_validation.build_gap_report(scope_details, upstream, en_orders, channel_accounts)` 输出只读候选与字段缺口。测试先红后绿，覆盖精简快照 hold、缺上游仍保留、重复范围键拒绝和账户盲键碰撞。候选 JSON 在仓库外既有技术目录的 `account-cost-bridge/fba_sync_gap_candidates.json`，订单及金额数据不提交 Git。
