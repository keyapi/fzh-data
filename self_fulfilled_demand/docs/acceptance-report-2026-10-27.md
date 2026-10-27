---
okf: v0.1
type: Report
title: 自发货需求增量接入 — 验收报告（2026-10-27）
description: 真实采集数量对账、离线交叉验证、测试结果、剩余阻塞与冻结状态
tags: [acceptance, demand, en-demand-v1, report]
date: 2026-10-27
status: frozen-for-review
---

# 验收报告（2026-10-27）

## 结论

1. **真实采集成功**：EN `Tongtool Order` 27,503 单 / 28,823 行 / 24,323 包裹已落盘；
   窗口 A（`sale_time >= 2026-10-01`）6,800 单，窗口 B（`modified >= 2026-10-01` 且
   `sale_time < 2026-10-01`）20,703 单，合计与 EN 独立计数完全一致。
2. **交叉验证通过**：9 月末 1,816 条 GS 行全部在 EN 找到同单同 SKU 行，
   数量差为 0（1,816/1,816 相等），`gs_only = 0`。
3. **初次运行的 `overlap_validation` 失败已解释并离线重做**：失败原因是采集进程启动于
   分页/快照修复前，进程内 `ParquetStore` 是旧类，而 `consumer` 从磁盘加载了新代码
   （`AttributeError: 'ParquetStore' object has no attribute 'pinned'`）。初次报告保留不改；
   `finalize_store` 用新版固定快照代码离线重做并通过，不重复拉取。
4. **代码/测试冻结待复核**：离线 fixture 22 个通过；未 push、未开 PR。

> 本报告不把「测试通过」当作「旧进程数据完整」的证据；完整性由 **EN 独立计数** +
> **头行一致性审计** + **9 月末行级交集** 三项独立验证。

## 1. 运行版本与指纹

| 项 | 值 |
|---|---|
| 初次采集 run_id | `20261027T125935-7cb8d1` |
| 初次采集开始 / 结束 | 2026-10-27 12:59:35 → 13:13 左右 |
| 初次采集代码 | 分页/快照修复前的版本（`READER_VERSION` 未写入报告） |
| git HEAD（本次冻结基线） | `6fcc0b32` |
| 收编/复核 | `python -m self_fulfilled_demand.finalize_store`（新代码） |
| 快照 commit | `legacy-adopt-20261027T131556` |
| manifest | `D:/Work/fzh-order-store/en-demand-v1/manifest.json` |
| 初次报告（保留） | `en-demand-v1/runs/20261027T125935-7cb8d1.json` |
| 收编报告 | `en-demand-v1/finalize_report.json` |

manifest 关键字段：

```json
{
  "status": "success",
  "data_fetch_status": "success",
  "validation_status": "passed",
  "partial": false,
  "watermarks": {"modified_max": "2026-10-27 12:59:35", "watermark_advanced": true},
  "source_coverage.en.reader_version": "pre-2026-10-27-pagination-snapshot-fix",
  "source_coverage.en.coverage_verified_by_counts": true,
  "source_coverage.offline_overlap_validation.matched_lines": 1816
}
```

## 2. 数量对账

| 指标 | 期望（EN 独立计数） | 实际 | 结果 |
|---|---|---|---|
| `sale_time >= 2026-10-01` | 6,800 | 6,800 | ✅ |
| `modified >= 2026-10-01`（A∪B） | 27,503 | 27,503 | ✅ |
| 订单头唯一 | — | 27,503 / 唯一 | ✅ |
| 行唯一（`line_key`） | — | 28,823 / 唯一 | ✅ |
| 头 `line_count` vs 行表 | — | 0 不一致 | ✅ |
| 头 `line_qty_total` vs 行和 | — | 0 不一致 | ✅ |
| 包裹行 | — | 24,323 | — |
| 事件 | — | 27,503（全部 created） | — |

按 scope：

| scope | 订单 | 销售日期范围 |
|---|---|---|
| `self_fulfilled_candidate` | 24,634 | 2023-01-26 → 2026-10-26 |
| `fba` | 2,437 | 2025-09-23 → 2026-10-26 |
| `third_party_or_dropship` | 432 | 2026-08-26 → 2026-10-26 |
| `unknown` | 0 | — |

分页：A 14 页、B 42 页，无错误、无预算耗尽；请求 57 次。

## 3. 交叉验证（9 月末）

窗口 `2026-09-20 → 2026-10-01`：

| 指标 | 值 |
|---|---|
| EN 订单 / 行 | 2,850 / 2,968 |
| GS 订单 / 行 | 1,796 / 1,816 |
| 匹配行 | 1,816 |
| GS-only 行 | 0 |
| EN-only 行 | 1,152（抽样窗口外的正常差集） |
| 匹配行数量差绝对值 | 0.0 |
| 数量完全相等的匹配行 | 1,816 / 1,816 |

## 4. 统一消费输出（2026-09-01 → 2026-10-31）

路径：`D:/Work/fzh-order-store/en-demand-v1/consumer/`

| 帧 | 行数 | 数量 | 说明 |
|---|---|---|---|
| `demand_lines` | 10,823 | 11,823 | 主建议口径（self） |
| `demand_by_day_sku` | 7,089 | 11,823 | 日期×SKU×需求类型 |
| `demand_by_day_sku_warehouse` | 7,243 | 11,823 | 加仓库；UOM 未知保留 null |
| `demand_all_non_fba` | 11,228 | — | 含代发/unknown 有效需求 |
| `deferred` | 405 | 456 | 代发，默认口径外，原因已标 |
| `fba` | 2,443 | 2,547 | 不进入自发货需求 |
| `quarantine` | 917 | — | 取消 680 / 退款 16 / 嵌入组件 221 |
| `returns` | 0 | 0 | — |
| `date_unknown` | 0 | 0 | — |
| `overlap` | 13,064 | — | 含被替代原始行 |

需求来源：GS 历史 5,893；EN 增量 5,698；EN 迟到补洞 232。
需求形态：皮壳 4,314；成品 704；半成品 637；GS 无发货方式 6,168。
仓库：美中-FZH-DANEEY 5,423；美东-CENTRADE 3,512；波兰-FZHPoland-covers 2,774；
退货仓 105。

## 5. 测试

```
uv run pytest self_fulfilled_demand/tests -q
22 passed
```

覆盖：重复运行幂等、同单同 SKU 多行、拆单 `_1/_2`、旧单更新/取消、跨 GS 行级重叠、
跨切点同量不双计、真正多行/拆包、GS-only、FBA 分流、unknown 责任待定、代发可纳入、
数量缺失不填 0、`sale_date` 缺失单列、空历史窗口、分页预算耗尽、同时间戳完整分页、
损坏快照拒绝、写盘失败保留上一快照、GS 缺列报错、manifest partial。

## 6. 明确保留的问题 / 剩余阻塞

1. **初次采集使用修复前读取器**：完整性已由独立计数与交集验证，但读取器版本不同；
   后续增量请用当前代码（`READER_VERSION=2026-10-27-pagination-snapshot-v2`），
   不要用新测试为旧进程背书。
2. **421 行 `line_key` 带 `|dup` 后缀**（350 组同单共享 `orderDetailsId`，源数据一套沙发
   拆多物料行）。行未丢失、键唯一；新代码已改为回退键 + `source_id_shared` 标记，
   当前快照未重写这 421 行（不重复拉取、不做无必要的派生重写）。
3. **UOM 全部未知**：订单行无单位字段，`uom=null`、`uom_status=unknown`；
   补货分桶需后续 join EN `Item.stock_uom`，本模块不猜、不填 0。
4. **GS 历史段无 `shipping_method`**：`demand_kind=unknown`，不能反推成品/组件。
5. **9 月末交集是抽样/变更窗口**，`coverage_status=sample`，不代表整月完整覆盖。
6. **代发默认不进主建议**：405 行在 `deferred`，责任待业务确认。
7. **FBA 上游约束未接入**：只记录 FBA 订单，不把工厂物料预留/共享产能加进终端销量。
8. **本模块不含补货内核**：供应分桶由独立 Codex 接 `SupplyRow`，此处不扩展。

## 7. 冻结状态

- 分支：`keyapi/self-fulfilled-demand-oct29`
- 实现提交：`3cfc585c`（feat(supply-chain): EN 终端订单只读增量与旧 GS 统一消费接口）
- 改动：`self_fulfilled_demand/`（代码/测试/文档）、`AGENTS.md` 模块索引、`index.md` 自动更新、
  `pyproject.toml`/`uv.lock`（新增 `pyarrow`）
- 未 push、未开 PR；等待外部复核。
