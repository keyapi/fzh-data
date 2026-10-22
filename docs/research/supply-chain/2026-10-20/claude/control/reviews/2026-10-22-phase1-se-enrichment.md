---
okf: v0.1
type: Review
title: 10 SKU 第一阶段 SE 明细补齐（生产只读，闸门 ca27163c）
date: 2026-10-22
reviewer: claude
verdict: complete-10sku
---

# 10 SKU 第一阶段 SE 明细补齐

## 结论

- 在闸门 `ca27163c`（Codex PASS）保护下，完成 238 个缺失 SE 明细的补齐。
- **用量远低于限额**：239 请求（238 enrich + 1 retry）/ 300；
  传输 253,308 B（≈0.24 MiB）/ 32 MiB；解压后 670,069 B（≈0.64 MiB）；
  241 秒 / 900 秒；`exhausted=false`、`stop_reason=null`、`refused=0`。
- **10/10 SKU 的 C1/C2/C3 均完整**；SE 覆盖 663/663 已解决；
  C2 共 195 可比、193 通过、**2 张 `produced_qty` 失真**、1 张 `wo_uom_unresolved`（WO-25-07755，SE 单位桶为空）；
  C3 663/663 通过。
- 两轮离线回放：`stable_sha256`、`row_accounting`、`line_dispositions.jsonl`
  逐字节一致。

## 运行

- 代码：`ca27163c`（闸门）+ `4b7ec55f` 分析逻辑（未改口径）。
- 快照：`g1b_en_top_1..9` + `g1b_en_rr2`，共 10 个。
- 命令要点：`--enrich-se --reuse-se-details --max-requests 300 --max-mib 32
  --max-minutes 15 --min-interval 1`，凭证指向父仓库 `EN_API/.env`。
- 输出：`out/dn_wo_jc_se_expand10_phase1/`；第二轮回放
  `out/dn_wo_jc_se_expand10_phase1_r2/`（0 网络）。
- 未扩 family、未写生产、未合并 PR。

## 结果

| 项 | 值 |
|---|---|
| SKU / 行数 | 10 / 3,416 |
| SE | 663（全部 resolved） |
| SE 行 | 876（补齐后；总行 3,416 = 215+507+214+663+876+941） |
| C1 | 10/10 pass（逐行全精度） |
| C2 | 195 可比 / 193 pass / 2 mismatch / 1 unverified |
| C3 | 663 evaluated / 663 pass / 0 unverified |
| `audit_ok` / `evidence_complete` | true / true |

C2 的 2 处 mismatch 仍在 `CEN003-DPBLUE-100` 与 `C/Cord-Grey-100-710-wow`
（`Work Order.produced_qty` 失真）；1 张 `wo_uom_unresolved`（WO-25-07755，SE 单位桶为空）保持 `unverified`，不强行合计。

## 证据哈希

- `association_manifest.json` `92318843559a8611415eb549729039f3c757027df9bc9e38bef2882d3aa0f97f`
- `line_dispositions.jsonl` `e3ff419f3664003c1acb2d02f08ef033e3a230bbdacd86df09a8c0f2807a3f3e`
- `se_details.json` `983d4babde73d3c8829a70d8fb38432aeb4bffcf6401a3d8f06c8c4afba91c36`
- `prod_budget.json` `176e7856884e7080c10df2b4f55dd2ab55d1dc99046bd5b1fb67df0ed9465ae6`
- `stable_sha256` `1732d5900c8a9ecf8d9b8a9773447912eaa86b5fd5fb09117ca24876be15aa4e`
- 行账：`so 215/215`、`dn 507/507`、`wo 214/214`、`se 663/663`；
  派生 `se_line 876`、`jc_operation 941`，0 静默丢弃。

## 边界与下一步

- **只是 10 个 SKU 的 C2/C3 补齐**，不是 100 SKU、不是全 family、不是 G1 验收。
- 扩样仍暂停：需 ETA/在途、Cover 同池/UOM、业务口径与明确授权。
- 下一步：Codex1 独立复审本证据；Codex2 决定是否继续扩样或转向 ETA/Cover/UOM。
