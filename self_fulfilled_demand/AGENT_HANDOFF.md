# self_fulfilled_demand — Agent Handoff

> 入口：先读 [README.md](README.md)，细节看 [docs/index.md](docs/index.md)。
> 本模块只负责「EN 终端订单 → 本地需求增量」，**不包含补货内核**。

## 1. 任务背景

2026-10-29 要交付大范围自发货补货建议（人工下单），10-30 演示。
旧数据 `D:/Work/fzh-order-store/gs_orders.parquet` 407,898 行、发货口径截至 2026-09-30；
`en_orders.parquet` 只有 2,733 行订单头抽样、无 SKU 明细。本模块补上 10 月起
EN 终端订单（含未发货需求）的只读增量，并给旧 GS 一个统一消费接口。

## 2. 已落地

| 能力 | 入口 |
|---|---|
| EN 只读增量（窗口 A 新增 / B 历史变更 / C 9 月末抽样） | `python -m self_fulfilled_demand.ingest` |
| 本地 Parquet：orders/lines/packages/events/raw | `snapshots/<commit_id>/` |
| 快照 + `CURRENT` 指针，失败批次不冒充成功 | `store.ParquetStore` |
| 旧 GS + EN 拼接、行级覆盖、quarantine | `consumer.build_demand` |
| 收编旧根目录 + 独立计数审计 | `python -m self_fulfilled_demand.finalize_store` |
| 规范 SKU×仓×UOM + 净额资格 | `python -m self_fulfilled_demand.canonical` |
| 离线 fixture 测试（21 个） | `uv run pytest self_fulfilled_demand/tests -q` |

## 3. 必须守住的不变量

1. **只读**：`EnReadOnlyClient` 没有写方法；计数走 `frappe.client.get_count`。
2. **行级**：对账键 `(完整单据名, 通途SKU)`；不按订单号整单覆盖，不按 base 合并。
3. **同单同 SKU 多行**：`line_key` 优先源 `orderDetailsId`，回退 `doc|idx|sku|qty`。
4. **取消 = `invalid=1`**；状态枚举里的「已取消/已退款」实测为 0。
5. **组件不变成品**：`is_deliver_good=0` → `embedded_component`；
   皮壳/半成品/成品分开 `demand_kind`。
6. **代发/unknown 不是无效**：有效需求保留在 `demand_all_non_fba`/`deferred`，
   带 `scope_reason`；默认口径只取 self。
7. **GS 是发货口径**：9 月下单 10 月发货 → `en_late_legacy` 补入；
   旧单取消/改量 → `superseded_cancelled` / `superseded_qty_change` 覆盖（EN 必须在本次增量窗口）。
8. **partial 不推进水位**：分页预算耗尽、子表失败、写盘失败、计数审计不符都标 partial。
9. **UOM 未知不猜**：`uom=null`、`uom_status=unknown`；聚合保留 SKU×仓×日。
10. **规范层不任取映射**：一对多 SKU 标 ambiguous 并阻断净额；子仓无证据不合并；
    `netting_allowed=false` 的行不得直接与供应相减。

## 4. 运行与验证

```bash
uv run pytest self_fulfilled_demand/tests -q          # 离线，21 个用例
uv run python -m self_fulfilled_demand.ingest --help  # 参数
```

真实采集注意：

- 生产 EN 读取要串行、有界（默认 `--page-size 500`、`--min-interval 0.15`）。
- 首次 `modified >= 2026-10-01` 约 27,503 单；`sale_time >= 2026-10-01` 约 6,800 单。
- 如果进程是修复前启动的，**不能**用修复后的单元测试给它背书；用
  `finalize_store` 按独立计数 + 头行一致性审计，不符就保持 partial。

## 5. 本轮审查清单（D01–D08）状态

| ID | 问题 | 状态 |
|---|---|---|
| D01 | 代发被无条件排除 | 已修：履约类型与有效性分离，`deferred` 保留 |
| D02 | GS 按 sale_date 切换丢旧单取消/改量；跨切点同量双计 | 已修：行级覆盖 + `en_late_legacy` + `superseded_cross_cutover` 先按业务行身份裁定 |
| D03 | 分页预算耗尽静默结束、水位前进 | 已修：`EnBudgetExhausted` + partial + 不推水位；同时间戳用 limit_start 推进 |
| D04 | 多文件中断写暴露不一致快照；指针损坏被当空库；消费跨提交混读 | 已修：快照目录 + `CURRENT` + `commit.json`；损坏指针报错；`pinned()` 固定快照 |
| D05 | 仅 10 月窗口/空历史窗口报错 | 已修：空窗口用例通过 |
| D06 | `sale_date=null` 行消失 | 已修：`date_unknown` 单列 + 数量对账 |
| D07 | GS 缺必需列静默填 None | 已修：`load_gs_orders` 列校验报错 |
| D08 | 聚合缺仓库/单位 | 已修：`demand_by_day_sku_warehouse` + UOM 证据字段（未知保留 null） |

## 6. 边界

- 不做补货量计算/供应分桶；下一步由独立 Codex 接 `SupplyRow` 适配。
- 不改 Jack 的 SO→生产→DN→Shipment/PO 链路，不造报表。
- 不把 FBA 消费需求并入自发货；FBA 的工厂预留只作上游约束。
- 不恢复旧调度/watchdog。
