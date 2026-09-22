---
okf: v0.1
type: Reference
title: 承运商批量导入面单的字段长度上限——UPS Reference 35 字符、FedEx poNumber 30（多 SKU 合并后必须主动截断）
date: 2026-09-22
category: integration-issues
module: tongtool_order_shipping
problem_type: integration_issue
component: tracking-integration
severity: high
applies_when:
  - "把「一个包裹多个仓库 SKU」合并成一行，再导入 UPS / FedEx 批量面单模板"
  - "批量导入报 Invalid Package Reference Value，或整批被拒 / 字段被悄悄截断"
  - "要在承运商批量模板里查某个字段的官方长度上限（而不是靠猜）"
tags: [ups, fedex, carrier-label, field-length, batch-import, csv]
---

# 承运商批量导入面单的字段长度上限

## Context

组合商品订单在仓库侧会炸成多个 SKU（成品 = 皮壳 `-Cover` + 海绵 `-Foam`），而**一个包裹只能贴一个面单标签**。所以给承运商批量导入的 CSV 必须「每包裹一行」——把该包裹内所有 SKU 拼进同一个 Reference 字段；同时给仓库的背贴要显示全部 SKU。

这个拼接串随 SKU 数量**线性变长**，而承运商批量模板对每个字段有硬上限。超限不是「截断一下就好」，行为因承运商而异：

| 承运商 | 字段 | 官方上限 | 超限行为 |
|---|---|---|---|
| UPS | Reference 1~5 | **各 35 字符** | **整批被拒**（报 `Invalid Package Reference Value`） |
| FedEx | `poNumber` | **String(30)** | 按上限截断（承运商侧切，位置不受控） |
| FedEx | `reference` | String(30) | 同上 |
| FedEx | `itemDescription` | **String(450)** | 余量极大，同一拼接串放得下 |
| FedEx | `harmonizedCode` | String(35) | — |
| FedEx | `documentDescription` | String(52) | — |

> 注意 UPS 与 FedEx 的差异是**失败模式**不同，不是「多长」不同：UPS 是 fail-loud（整批拒绝），FedEx 是 fail-silent（悄悄切）。两者都要在拼完后自己截。

## Guidance（本学习沉淀的做法）

**1. 查上限要读官方模板里的字段定义表，不要猜。**
承运商的批量模板通常自带一张字段说明表，那里就是权威：

- **UPS**：`CSV File Guide V5` / `Flat File Guide V5` 里逐字段列了 `Maximum Field Length`（Reference 1~5 均为 35）。
- **FedEx**：官方批量模板 xlsx 的 **`Available headers`** sheet 里每行是 `COLUMN HEADER | REQUIRED | DESCRIPTION | DATA TYPE | EXAMPLE`，`DATA TYPE` 直接写 `String(30)` / `String(450)`。**这张表就在本地模板文件里，不用翻文档站。**

**2. 截断写在拼接之后，且要留痕。**

```python
REF2_MAX = 35  # UPS Reference 字段硬上限（官方 CSV / Flat File Guide 均为 35）
first_row['Reference 2'] = merged_sku[:REF2_MAX]
```

同时在报告里打印「哪个包裹被截断、从多少字符切到多少」，否则这个字段会**静默变短**，下次没人知道为什么标签少了半个 SKU。

**3. 用「历史已接受文件的最长值」做交叉验证。**
官方上限是理论值；想确认现网实际拿到过多长，就去扫承运商**已接受**的历史文件该字段的最大长度：

- 某批次 UPS 已接受文件的 Reference 2 最长 **30**；
- 同期 FedEx 已生成文件的 `poNumber` 最长 **29**。

两者都紧贴上限 ⇒ 「一直没出问题」不等于「没有风险」，只是**还没撞上多 SKU 订单**。

**4. 上限是针对「拼接后的整串」，不是单个 SKU。**
旧模板「每包裹一行」时，一个包裹只有一个 SKU，拼接是**空操作**（最长 32 字符），所以这个坑长期不存在。模板改成「每货品一行」后，同一包裹出现多行，拼接才第一次生效 —— 风险是新引入的，别去历史里找先例。

## Why This Matters

- UPS 超限是**整批失败**：一批几十个包裹，因为其中一个的拼接串超了，全部导不进去。
- FedEx 是**静默截断**：不报错、能出单，但字段内容被承运商在你不控制的位置切断 —— 比报错更难发现。
- 两者都会让面单上的信息与实际包裹内容不一致，而面单是给分拣/客服看的，错了要人工回溯。

## When to Apply

- 做「多 SKU 合并成一行」的承运商批量导入文件时（`merged[:LIMIT]`）。
- 拿到一个新的承运商批量模板时，**第一件事**是读它的字段定义表，把要填的每个字段的上限抄下来。
- 任何「把多个值拼进一个字段」的场景 —— 先问这个字段有多长。

## Examples

拼接后的真实值（55 字符）超过 UPS 的 35：

```
TT0031249K0064109-Cover x 1, TT0312588K0064183-Foam x 1     ← 55 字符，UPS 会整批拒
TT0031249K0064109-Cover x 1, TT0312                          ← [:35] 之后
```

同一个拼接串放进 FedEx：`itemDescription`（450）绰绰有余，`poNumber`（30）必须截 —— 所以**同一个 `merged` 字符串在不同字段要用不同的上限**，不能一刀切。

## 参考

- UPS `CSV File Guide V5` / `Flat File Guide V5` —— Reference 1~5 各 35 字符
- SendPro Enterprise 支持文章「Error: Invalid Package Reference Value」—— 明确写「UPS API only allows 35 characters in the Content Description, Reference One, and Shipper Reference fields. This is a carrier limitation.」
- FedEx Ship Manager Server Developer Guide —— 字段超长时按 Max Length 截断
- 本仓库同类字段上限（另一承运商，勿混用）：`vite-api/docs/reference/units-and-limits.md`
- 所属模块：`tongtool_order_shipping/AGENT_HANDOFF.md`（通途订单导出的发货侧处理）
- 改这条流水线的工具：`.agents/skills/colab-kit/`（它还在同事的 Colab notebook 里）
- 同批学习：`developer-experience/colab-notebook-drive-api-editing.md`
