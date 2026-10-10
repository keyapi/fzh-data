---
okf: v0.1
type: Reference
title: Amazon 非 V2 报税技术验证：已证实边界与禁止推断
date: 2026-10-10
category: tooling-decisions
module: sellfox_settlement
problem_type: tooling_decision
component: tooling
severity: high
applies_when:
  - "继续 2026-08 Amazon 非 V2 月度报表的国内报税自动化"
  - "要把 CSV、PDF、渠道账号、EN 成本或银行到账接成申报数"
tags: [amazon, tax, settlement, non-v2, validation]
---

# Amazon 非 V2 报税技术验证：已证实边界与禁止推断

## Context

财务负责人 ZJ 尚未填写底稿第 2 节。技术侧已对 2026 年 8 月 Amazon 非 V2 月度交易 CSV 与 Summary PDF 做完只读验证，原始账单、订单号、金额和银行标识都留在仓库外。Codex 对话「查看 PR284 报税账期分析」在用户要求收尾提交时额度用尽，验证代码与三份调研当时尚未入库。

底稿与填写通道仍以 [2026-10-09 分析](../../../sellfox_settlement/docs/research/2026-10-09-amazon-non-v2-monthly-tax-analysis.md) 和 [外部问卷约定](../conventions/external-questionnaire-via-notion.md) 为准。本篇只记录技术验证已经钉死的边界，避免下一次把探针结果写成申报数。

## Guidance

验证脚本在 `sellfox_settlement/`：`non_v2_validation.py`、`pdf_validation.py`、`monthly_validation.py`、`account_validation.py`、`cost_validation.py`、`settlement_validation.py`，外加 `validation_paths.py`（拒绝把业务明细写进 Git 工作树）。表头别名在 `non_v2_header_aliases.json` 与 `non_v2_header_profiles.json`。测试在 `tests/sellfox_settlement/`。实测计数与复跑命令写在三份调研里，不要把计数从本篇再抄一份去对账：

- [账号、稳定键与法人](../../../sellfox_settlement/docs/research/2026-10-10-account-technical-validation.md)
- [订单与成本](../../../sellfox_settlement/docs/research/2026-10-10-cost-technical-validation.md)
- [Summary PDF 与 CSV 控制科目](../../../sellfox_settlement/docs/research/2026-10-10-pdf-technical-validation.md)

继续做之前先保住这些结论：

1. **行数守恒。** 65 对 CSV/PDF、11,580 行交易全部保留。Released 与 Deferred 分列。未定汇率前禁止跨币种相加。
2. **退款 `other` 是合并桶。** 65 份文件上，CSV 所有 Refund 行的 `other` 合计等于 PDF 与 CSV 在产品退款、运费退款、礼品包装退款、促销退款、退税上的差额之和。这不能反推每一笔退款的商品、运费和税。非零 `Refund.other` 保持未分配。
3. **PDF 净额一致不等于科目完整。** 五大控制分区的已读明细可以加回印出净额；加拿大模板里空白的 FBA 费用单元格仍然是缺失，不能补 0。瑞典语标题里的 `kr` 只在全文语境下推断为 SEK，裸 `kr` 不能当 ISO 币种。
4. **账号匹配不是申报主体。** 运营渠道账号、EN Channel Account、赛狐 shop 是三套键。Seller ID + marketplace ID 只能做补充定位，不能冒充已登记的标准渠道账号，也不能推出法人。EN 账户币种全是 CNY，不能当账单原币。赛狐 `region` 是 `eu`/`na`，不是国家站点。
5. **当前成本不是 8 月历史成本。** FBA 的通用 `item_cost` 在本批样本为正值的个数是 0；产品和头程看 Cost Review 分量。FBA 不叠加 FBM 尾程。生产 BOM 快照晚于账单月，离线调用计算函数只证明当前链路能跑，不证明申报月成本。父子单并存、SKU 不符、缺单都保持分行，不删行消歧。
6. **银行实际到账仍缺输入。** 共享账期目录里核到的银行 PDF 不是 8 月 Amazon 入账。平台付款通知和结算 flatfile 的 `deposit-date` 都不能代替银行操作日。不要假定银行流水号等于 Settlement `traceId`。
7. **私有输出不入库。** 脚本拒绝向 Git 工作树写业务明细。账号调研提到的 `bank_evidence_probe.py` 与 `bank_evidence_finish.py` 不在本分支文件清单里；若它们在账单旁的私有目录，留在那里。

## Why This Matters

这些检查各自都能通过，合在一起却仍不是申报表。把店铺匹配写成法人、把当前 BOM 写成 8 月成本、把 `Refund.other` 整笔计入商品退款，或把结算日期写成银行到账日，都会在财务未答复时把候选值变成唯一口径。

## When to Apply

- 接手 `feature/amazon-non-v2-tech-validation` 或 [PR 284](https://github.com/keyapi/fzh-data/pull/284) 之后的报税自动化。
- 有人要求「把 8 月销售额和成本算出来」而 ZJ 的 F01—F20 仍空着。
- 要复跑验证，或把新月份接到同一套脚本。

财务口径、历史 BOM、未登记账号和银行流水仍然要人提供。技术侧只并列候选，不替财务选定。

## Examples

```powershell
uv run pytest tests/sellfox_settlement -q
uv run python -m sellfox_settlement.run_technical_month --input <8月账单目录> --out <仓库外私有目录> --month 2026-08
```

`finance_rules.yaml` 的 `status` 在 ZJ 确认前必须是 `pending_ZJ`。配置若写下已选定的收入候选，加载会直接报错。月度命令重跑文件覆盖、PDF 科目、账号匹配和订单连接，并写出 8 张工作表；Settlement 与通途 FBA 探针复用已完成的只读快照，不刷新生产、不部署 EN enrichment。

2026-10-10 对 8 月目录跑过一次：65 份 PDF 成功，1,941 个科目比较中 1,918 个完整、5 个空白金额、18 个差额保留，账号候选 64/65，订单连接 9,969/10,116。工作簿留在账单旁的私有目录，文件名 `2026-08-technical-workbook.xlsx`。

## Related

- [2026-08 报税分析底稿](../../../sellfox_settlement/docs/research/2026-10-09-amazon-non-v2-monthly-tax-analysis.md)
- [赛狐结算中心与列式报表取舍](amazon-settlement-autofetch-sellfox.md)
- [外部问卷：仓库 MD + Notion 访客](../conventions/external-questionnaire-via-notion.md)
