---
okf: v0.1
type: Research
title: Amazon 非 V2 Summary PDF 技术验证
description: 65 份单页文字层账单的坐标抽取、币种与期间证据及控制科目覆盖
tags: [amazon, settlement, pdf, technical-validation]
timestamp: 2026-10-10
resource: sellfox_settlement/pdf_validation.py
---

# Amazon 非 V2 Summary PDF 技术验证

65 份 PDF 全部可读取四大净额 Income / Expenses / Tax / Transfers。逐分区将已识别明细的有符号金额相加，260 个分区均与 PDF 印出的净额一致。5 个明细金额单元格为空，仍保留为未确认，不因净额相符而补零。此验证证明 PDF 抽取内部一致性，CSV 对账由调用方另外完成。

| 检查 | 输入 | 成功 | 未完整 / 未确认 | 失败 |
|---|---:|---:|---:|---:|
| 单页文字层读取 | 65 | 65 | 0 | 0 |
| 四大控制净额 | 260 | 260 | 0 | 0 |
| 分区已读明细与净额残差为零 | 260 | 260 | 5 分区含空白金额，完整标记为 false | 0 |
| 起止日期 | 65 | 65 | 0 | 0 |
| 完整期间末时刻 | 65 | 55 | 10 份标题尾部截断 | 0 |
| 币种直接证据 | 65 | 61 | 4 份瑞典语 `kr` 推断为 SEK | 0 |
| 金额未知标签 / 歧义映射 | 已读全部 | 全部 | 0 | 0 |

完整私有输出保存于原始账单目录之外的受控技术验证目录，含原文件路径、店名、法定名称、科目金额与坐标；这些数据不进入 Git。仓库仅保存解析规则、合成测试和统计结果。

## 方法与证据

先复用 [PyMuPDF 官方文字层接口](https://pymupdf.readthedocs.io/en/latest/app1.html) 的 `get_text("dict")`，读取每个 span 的原词与 `bbox`，按实际坐标关联标签和右侧金额。不能把内容流顺序当作表格阅读顺序；本批文件默认文本流中标题、科目和数字穿插明显。

使用已审阅的语言标签映射，覆盖英语、美加与英国措辞变体、德语、意大利语、法语/比利时变体、荷兰语、西班牙语/墨西哥变体、波兰语和瑞典语。波兰语文字层自身缺部分变音字符，比利时退款标签自身截断，因此映射保留文字层实际原词。映射不包含真实客户名称、账号、地址或金额。

金额使用 `Decimal`，支持欧美千分位与小数分隔符、不可断空格和瑞典 PDF 的 Unicode 减号。格式不明确的金额拒绝解析。一个科目若同时有 Debit 与 Credit，控制值为两者有符号之和，证据仍分别保存。

本批 CAD 模板的 `FBA inventory and inbound services fees` 金额单元格确实为空：已渲染代表性页面检查，非文本层漏读。5 份均产生 `missing_amount_row`；调用方不可默认视为 0。西班牙语与瑞典语的 10 份标题最后时分截断，日期仍完整，不自行补 `23:59`。

## 接口

`extract_pdf(path)` 返回字典：

- `controls: dict[str, Decimal]`：销售、退款、运费、促销、佣金、FBA、服务费、广告、税、转账等；`income/expenses/tax/transfers` 取 PDF 印出值。`totals` 为四大净额派生求和，并明确标记证据。
- `control_evidence`：每个控制值对应的原标签、标签坐标、一个或多个金额原词/坐标/值。所有金额带原始符号。
- `raw_rows`：所有已关联金额的标签行；未知科目不会静默丢弃。
- `section_checks`：分区 `residual`、`complete` 和空白金额行；残差为 0 不等于完整。
- `period_start/period_end`：ISO 日期；`period_start_time/period_end_time`、`timezone` 分开保存，截断值为 `None`；`period_evidence` 保留标题原文与坐标。
- `currency/currency_evidence`：直接证据与推断明确区别；`kr` 对应 SEK 只按瑞典语标注推断，不当作显式 ISO 币种。
- `display_name/legal_name`：仅作原始标识证据，不推出报税法人归属；请仅写入私有报告。
- `issues`：空白金额、未知/歧义科目、重复控制、期间截断、元数据缺失、分区净额不一致等。

缺失或重复控制不进入 `controls`，不能用 `.get(key, 0)` 消解证据缺口。当前仅支持单页、双栏的已观察 Summary 家族；多页会报错，其他布局需重新验证。PDF 科目标签与 CSV 科目维度可能不同，调用方应基于科目定义构建比较，不直接要求每列等于每项。

## 验证

`tests/sellfox_settlement/test_pdf_validation.py` 共 21 个合成坐标/金额测试，覆盖内容流乱序、跨栏误配、同一数值行歧义、重复标签、未知科目、空白金额、Debit+Credit、大小写变体、欧美金额、Unicode 负号、币种推断与期间截断，以及 CSV 的合并退款桶、Deferred、广告/订阅/Chargeback 分组、税字段不同模板及必需列验证，全部通过。仅在瑞典语标题明确出现 `Alla belopp i kr` 时推断 SEK；裸 `kr` 无法区分北欧币种，保持未定。测试不含原始账单或客户/财务数据。

复跑入口由月度验证调用方串联，既可直接调用 `extract_pdf`，也可先用 `parse_spans` 对合成坐标或已保存文字层证据做回归。原始 PDF 始终只读。

## CSV / PDF 退款差额技术解释

增加 `csv_controls(rows)`，输入同一币种的标准化 CSV 行，返回 `controls/control_evidence/unallocated/comparison_groups`。所有状态包括 Deferred 都保留；费用根据交易类型投影，不将订阅费、广告或清算费用全部当作订单佣金。CSV 的 `collected_sales_tax` 综合税字段与细分商品/运费/礼品/促销税模板分别读取，避免漏算或重复计税。输入缺必需列或混币种会报错。

本批可构建 1,941 个金额比较：1,918 个完整零差、5 个加拿大 FBA 费用组合的候选残差为零但受空白金额限制、18 个显式差额。18 个差额包含 8 个产品退款、6 个运费退款、2 个退税和 2 个税净额；不通过修改 PDF 原值或强行分配 CSV 金额消差。65 份销售两种履约方式、账户总活动净额，以及可完整读取的净订单佣金/FBA 费用组合均一致。

对 65 份文件逐份验证以下**聚合解释桥**，残差全部为零：

```text
CSV 所有 Refund 行 other 合计
= (PDF 产品退款 - CSV 产品退款)
+ (PDF 运费退款 - CSV 运费退款)
+ (PDF 礼品包装退款 - CSV 礼品包装退款)
+ (PDF 促销退款 - CSV 促销退款)
+ (PDF 退税 - CSV 退税)
```

这说明 `Refund.other` 为跨科目的合并桶，不能简单全部加到产品退款。其中负 `other` 可出现在商品退款原列为零的行；FBA 正 `other` 可回补产品退款；FBM 正 `other` 同时可能影响产品、运费和税。CSV 只保留商品描述，当前不足以逐单确定这些成分，因此所有非零 Refund.other 行都保存为 `unallocated`，聚合桥不能代替逐单分类证据，也不能直接作为报税收入规则。

后续若需要逐单分解，可用 Amazon [Finances API 的退款事件及 Charge/Fee 调整明细](https://developer-docs.amazon/sp-api/reference/listfinancialevents)或 Seller Central 退款交易详情补证据。官方[卖家自配送退货说明](https://sellercentral.amazon.com/help/hub/reference/external/G201725630?itemid=51)提到退货运费与 restocking fee 场景，但该资料不能证明本批每条 `other` 的具体组成。详细原行、金额桥与差额保存在受控私有目录，不提交仓库。
