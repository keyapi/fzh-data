---
okf: v0.1
type: Research
title: 2026 年 8 月 Settlement V2 原币与站点时间分页验证
description: 61 个已定位店铺按账单原币查询，并以站点时间保留 8 月明细
timestamp: 2026-10-10
resource: sellfox_settlement/settlement_validation.py
tags: [amazon, settlement, native-currency, pagination, read-only, technical-validation]
---

# Settlement V2 原币明细验证

本次只读验证覆盖 60 个运营表精确映射店铺及 1 个有独立 PDF 和稳定键证据的补充店铺，共 61 个。另 4 份账单未定位店铺继续保留缺口，没有扩大到当前赛狐全部店铺。

## 原币与时间范围

原始 `currency_map` 以 CSV 文件名为键，而账号 scope 使用绝对文件路径。现支持完整路径精确键和 Windows 文件名键；二者币种不同、同一稳定店铺键对应不同币种、缺少币种证据均在创建 API 客户端前阻止。启用 `--include-details` 时 `--currency-map` 必须在任何 API 请求前提供。

按 CSV/PDF 证据分成 6 个原币组，每次请求只传该币种组的 `shopIds` 和 `marketplaceIds`，并对返回的 Seller ID + marketplace ID 再过滤。不能将「请求 currency=EUR」误当「仅取 EUR 站点」：API 可把其他国家的明细换算到所指定币种。合成测试验证跨币请求隔离及上游混入其他国家时的返回过滤。

API 请求日期使用 UTC 缓冲范围 2026-07-31 至 2026-09-02；保留完整返回后，依据 `siteTimeStr` 的 `2026-08-` 日期前缀另输出站点自然月明细。`postedDateTimeStr` 与 `siteTimeStr` 同时原样保留，避免混用 UTC 日界线与站点日界线。原始 CSV 的 8 月分母没有改变。

| 原币 | 店铺数 | 缓冲范围返回行 | 站点 8 月行 | 边界其他月份行 |
|---|---:|---:|---:|---:|
| CAD | 5 | 23 | 21 | 2 |
| EUR | 31 | 5,053 | 4,384 | 669 |
| GBP | 5 | 22 | 20 | 2 |
| PLN | 4 | 0 | 0 | 0 |
| SEK | 4 | 5 | 5 | 0 |
| USD | 12 | 48,892 | 43,565 | 5,327 |
| 合计 | 61 | 53,995 | 47,995 | 6,000 |

返回币种不符、稳定键范围外、缺少站点时间均为 0。所有 53,995 行均有 amount 字段。6,000 行边界数据留在私有完整证据中，没有静默丢弃。

行数单位是 V2 科目明细，不是 CSV 的交易行；不能把 47,995 与 11,580 直接视为数量不符，也不能强制把 payout 与 activity 所有类别一一配平。金额/状态差异需要按账号、订单、科目、Posted/Released/Deferred 和时间口径另建桥。

## 分页与零行契约

`fetch_complete` 使用上游返回的 totalSize/total，分页长度 200。USD 完整读取 245 页、EUR 26 页，其余币种各 1 页。保护包括：总数变化报错、短页未达到总数报错、整页重复报错、跨页或页内同 ID 重复报错；没有 ID 的行按完整内容检查重复。重复不是静默去重；发现时应保留问题并阻止假通过。

PLN 的真实 API 结构为 `detailPageVoList: null`，并且 `totalSize: 0`、`totalPage: 0`、`pageNo: 0`、`pageSize: 0`。这是明确的零行结果。已按真实契约增加红绿测试：只有已知行列表字段存在且为 null、总数明确为 0 时才允许空列表；字段缺失或没有明确零总数仍报错。4 个 PLN 店铺的零行结果按成功验证保留，不从范围中删除。

## 私有证据和复跑

`settlement_validation_summary.json` 保留原 group/plugin 摘要，附加 `details` 数组、`details_complete`、`details_pending_currencies` 和 `details_row_totals`。本次 `details_complete=true`，6 币均完成，errors 为空。

- `settlement_details_<currency>.json`：完整时间缓冲范围、已过滤稳定键的原币行。
- `settlement_details_<currency>_site_august.json`：站点自然月 8 月行；PLN 为明确的空列表。
- `settlement_detail_evidence/<currency>_raw.json`：完整 API 返回。
- `settlement_detail_evidence/<currency>_outside_scope.json`：范围外记录，本次均空。

明细保留 `id`、`settlementId`、Seller/marketplace 稳定键、`currency`、两种时间、交易类型、科目、`amount` 和数量等原始字段。私有明细、主体名称、账号和金额不进入 Git；所有输出目录通过任意 `.git` 祖先检查。

```powershell
uv --project <主仓库> run python sellfox_settlement/settlement_validation.py --scope <精确scope.json> --additional-scope <补充scope.json> --data-root <主仓库> --out <仓库外私有目录> --include-details --currency-map <CSV和PDF币种证据.json> --detail-start 2026-07-31 --detail-end 2026-09-02
uv --project <主仓库> run pytest tests/sellfox_settlement/test_settlement_validation.py -q
```

复跑整个 CLI 会重复查询 group/plugin；本次续跑复用已保存摘要，调用 `native_currency_scopes` 和 `fetch_native_details` 完成原币明细，再追加摘要。私有续跑脚本和 PLN 显式零行探测记录均已保存。本次 15 个 Settlement 测试通过。

这些是平台结算证据，不是独立银行实际到账记录。银行实收验证仍需银行/支付处理商的实际入账明细及 reference 桥，不能把 V2 的 arrivalAmount 或 transferAmount 自动当成银行证据。
