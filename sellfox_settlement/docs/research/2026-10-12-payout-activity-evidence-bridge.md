---
okf: v0.1
type: Research
title: 非 V2 活动行与 V2 原币结算事件技术证据桥
description: 用稳定账号、订单、SKU、类型和原币连接两个既有快照，保留所有候选、科目未知项及时间差异，不选择报税规则
tags: [amazon, settlement, non-v2, traceability, technical-validation]
timestamp: 2026-10-12
---

# 非 V2 与 V2 的事件证据桥

## 范围与复用

已有 `account_cost_bridge.py` 连接非 V2 与 EN/通途账号，`monthly_validation.py` 解释 CSV/PDF 的 Refund.other 汇总差异，`settlement_validation.py` 验证原币分页及账号过滤；它们没有 CSV 与 V2 订单科目事件的逐行桥。本轮只补这一项，读取 2026-10-10 的既有 8 月快照，不调用生产 API、不再搜索银行、不修改月度 runner 或工作簿。

新增 `payout_activity_bridge.py` 的 `build_bridge` 是纯函数，复用 SKU 空白归一和私有输出保护。CLI 只读输入，在仓库外输出报告。没有删除重复记录、按品牌猜账号、选择财务口径或强制两个报表总额相等。

## 键与候选

CSV 文件通过既有精确 shop 清单及补充证据清单连接 `sellerId + marketplaceId`。订单键为该稳定账号对、原始订单号、归一 SKU、交易类型、原币；订单号不裁剪父子单后缀。仅 Order、Refund、Refund_Retrocharge、Chargeback Refund 建候选，其余明确保留为非订单记录。

V2 同键的行按 `settlementId + siteTimeStr + postedDateTimeStr + reportType` 聚为科目事件。不同结算或时间不合并；同一事件内的原始明细仍逐行保留。一个 CSV 对一个事件且反向只有这一个 CSV，才标记 `unique_event_evidence`。多个事件、多个 CSV、缺 SKU、缺币种、账号无映射、键未匹配分别报状态。这里的唯一是候选数量，不是已经确认交易身份或银行到账。

输入币种为空时只可用已有逐文件原币证据，并记录来源；CSV 币种与证据冲突报错状态，不覆盖。scope 文件 basename 重复立即报错。V2 稳定账号内重复 ID 按原行保留并阻止唯一科目比较，不能去重隐藏。

## 科目与时间

科目使用 `amountType + amountDescription` 白名单，区分 ItemPrice.Principal 与 Promotion.Principal。当前直接比较商品、税、运费、礼品包装、促销、佣金、FBA 每件履约费及平台代扣税；不把未知费用猜成 other。原始有符号金额通过 Decimal 聚合；缺金额、NaN 或无穷不能变成零。科目比较只展示 CSV、V2 和有符号差值，不输出净额相等判定。事件有未知或非法科目时 `subject_projection_complete=false`；非法金额阻止差额计算，缺 CSV 科目同样不给差额。

分别比较 CSV 活动日期及释放日期与 V2 站点墙钟。CSV 保留原 offset；V2 站点时间不擅自赋予 UTC 或使用机器时区。V2 posted 时间原文也保留。日期不解析、CSV 无 offset、站点时间意外带 offset、墙钟不同均可追溯。墙钟相同仅为证据，不等于跨来源时区或归期规则已经确认。

## 真实快照复跑

| CSV 状态 | 行数 |
|---|---:|
| 唯一双向事件证据 | 6,652 |
| 多个 V2 事件候选 | 35 |
| 多个 CSV 候选 | 18 |
| 键未匹配 | 3,412 |
| 非订单类型 | 1,462 |
| 缺 SKU | 1 |
| 合计 | 11,580 |

| V2 明细状态 | 行数 |
|---|---:|
| 唯一双向事件证据 | 30,103 |
| 多个 CSV 候选 | 272 |
| 多个事件候选 | 7 |
| 键未匹配 | 15,264 |
| 非订单类型 | 2,346 |
| 缺 SKU | 3 |
| 合计 | 47,995 |

V2 聚合 10,146 个订单科目事件。白名单之外的订单科目原始行 740，非法金额 0，重复稳定 ID 原始行 0。CSV 原币统计为 USD 10,655、CAD 12、EUR 891、GBP 13、MXN 4、SEK 5；V2 为 USD 43,565、CAD 21、EUR 4,384、GBP 20、SEK 5，PLN 显式零行快照保留在来源清单。

6,652 个唯一候选中，活动墙钟与 V2 相同 417、不相同 6,235；释放墙钟相同 6,285、不相同 367。这提供了 deferred/released 时间差异的直接技术证据，不把未匹配解释为漏结算，不依据活动行改写 payout 月份。现有 V2 只含站点 8 月窗口，无法证明释放至 9 月的 CSV 没有后续结算；不能依据本桥自动退款成本冲回或选择申报归期。

## 输出与复跑

私有报告 `payout_activity_bridge/payout_activity_bridge.json` 与既有私有快照同目录，包含 summary、csv_evidence、v2_evidence、events、duplicate_native_identity_groups、sources 和 limits。两侧原始索引、文件行号或 V2 ID、稳定账号、订单/SKU、币种、原日期与候选索引可追溯回原输入；未匹配及非订单原始金额留在对应快照，报告保留 CSV total 和 V2 amount。

```powershell
uv --project <主仓库> run python -m sellfox_settlement.payout_activity_bridge --transactions <私有目录>/normalized_transactions.json --native-dir <私有目录>/settlement --scope <私有目录>/account_shop_scope.json --scope <私有目录>/additional_shop_scope.json --currency-map <私有目录>/currency_map.json --out <私有目录>/payout_activity_bridge
uv --project <主仓库> run python -m pytest tests/sellfox_settlement/test_payout_activity_bridge.py -q
```

新增 11 项合成测试覆盖白名单有符号科目差异、重复 CSV/结算事件、多账号/币种/订单类型隔离、未知科目、缺键、活动/释放时间、重复 V2 ID、NaN、币种冲突和输入不变性。先观察缺模块失败，再观察新增边界测试失败，随后实现。与既有 settlement 和输出保护测试合跑 29 项通过。原始数据、订单标识、稳定账号和金额明细均未写入 Git，索引及统一提交由协调 agent 处理。
