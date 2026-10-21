---
okf: v0.1
type: Review
title: DN/WO/JC/SE 离线扩样 10 SKU 覆盖评估（目标 100）
date: 2026-10-21
reviewer: claude
verdict: partial-offline-ceiling
---

# DN/WO/JC/SE 离线扩样 10 SKU 覆盖评估

## 结论

- **可用离线快照只有 10 个 SKU**，距离 Codex 任务书的目标 100 差 **90 个**。
- 用已验收代码 `4b7ec55f` 原样回放 10 个快照，**C1（SO↔DN 同单位逐行守恒）10/10 全部通过**。
- **C2/C3 只有原 5 个 SKU 完整**；新增 5 个 SKU 的 SE 行明细不在快照里，离线无法补齐，
  238 个 SE 全部 `unverified`，因此整体 `status=partial`、`audit_ok=false`、`evidence_complete=false`。
- 本轮 0 次网络请求，未访问生产，未改代码，未改已验收证据。

## 输入与方法

- 代码：`4b7ec55f` 的 `g1b_dn_wo_jc_se.py`，未修改。
- 快照：`out/g1b_en_top_1..9.json` + `out/g1b_en_rr2.json`，共 10 个；
  由 `g1b_en_extract.py` 于 2026-10-20/21 离线抓取。
- 命令：`g1b_dn_wo_jc_se.py --snapshot ... (10 个) --out-dir out/dn_wo_jc_se_expand10 --reuse-se-details`
- SE 明细：复用已验收 `out/dn_wo_jc_se/se_details.json`（覆盖原 5 个 SKU）；
  新增 5 个无明细，**未开启 `--enrich-se`**（不访问生产）。
- 运行：2.5 秒，HTTP 预算 0/500，0 事件。

## 逐 SKU 结果

| SKU | 行数 | C1 | C2（可比/通过/失真） | C3 求值 | SE 覆盖 |
|---|---:|---|---:|---:|---|
| CENCord995-DKGrey-97 | 359 | 18/19 +1 excluded | 22/22/0 | 87 | 87/87 |
| CEN003-DPBLUE-100 | 367 | 14/15 +1 excluded | 20/19/**1** | 101 | 101/101 |
| C/Linen-Natural-100-688-wow | 218 | 19/19 | 0（17 unverified） | 0 | 0/49 |
| C/Cord-DKBlue-100-713-wow | 170 | 16/16 | 0（13 unverified） | 0 | 0/47 |
| C/Linen-Natural-153-688-wow | 321 | 27/28 +1 excluded | 0（23 unverified） | 0 | 0/66 |
| C/Velvet-Grey-100-705-wow | 183 | 15/15 | 0（13 unverified） | 0 | 0/36 |
| C/Cord-Grey-100-710-wow | 304 | 18/18 | 16/15/**1** | 63 | 63/63 |
| C/Linen-White-100-662-WOW | 166 | 16/17 +1 excluded | 0（13 unverified） | 0 | 0/40 |
| TT0000671K0063721 | 610 | 40/42 +2 excluded | 39/39/0 | 111 | 111/111 |
| C/Linen-Natural-194-688-wow | 400 | 25/26 +1 excluded | 20/20/0 | 63 | 63/63 |
| **合计** | **3,098** | **208/215 +7 excluded，0 fail** | **115/117 通过，2 失真** | **425** | **425 完整 / 238 未验证** |

输入行账：`so_line 215/215`、`dn_line 507/507`、`wo 214/214`、`se 663/663`；
派生 `se_line 558`、`jc_operation 941`，0 静默丢弃。

## 关键发现

1. **C1 在 10 个 SKU 上稳定成立**：逐行全精度、无跨 UOM 合计、无正负抵消；
   7 条 excluded 均因作废/超窗口等显式原因，没有 fail。
2. **C2 的两处失真与 v4 一致**：`CEN003-DPBLUE-100`、`C/Cord-Grey-100-710-wow`
   各 1 张 `produced_qty` 失真，继续支持“`Work Order.produced_qty` 不可当完工账”。
3. **离线证据天花板是 5 个 SKU 的 C2/C3**：新增 5 个 SKU 的 SE 行明细不在快照中，
   C2/C3 只能全部 `unverified`。这不是契约失败，而是**输入不完整**。
4. 要到 100 SKU，必须新增两件事，二者都需要明确授权：
   - 有界 EN 只读抓取 90 个新 SKU 快照；
   - 对缺 line 明细的 SE 做有界只读补齐（类似 v4 的 362 次 GET）。
   仅靠现有离线文件，最大只能做到 10 个。

## 证据

- 输出目录（本地，不入库）：`out/dn_wo_jc_se_expand10/`
- `association_manifest.json` `a7663e77a97515f5af94…`
- `line_dispositions.jsonl` `67e10909dcfc535a587e…`
- `snapshots_manifest.json` `3f83de8961fb667309af…`
- `stable_sha256` `5aa41e8e60606ad4…`
- 两轮一致性：本轮仅跑一次；离线输入未变，重跑应一致（未声明已验证两轮）。

## 边界

- 只证明这 10 个 SKU 的关联/守恒覆盖，不是 100 SKU 验收，不是全 family，不是 G1。
- 不构成需求/补货结论；G2/G3 仍阻塞。
- 未访问生产、未写生产、未合并 PR。
