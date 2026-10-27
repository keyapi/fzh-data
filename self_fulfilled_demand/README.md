# self_fulfilled_demand — 自发货需求增量接入（en-demand-v1）

从 EN（ERPNext）`Tongtool Order` **只读**拉取终端订单头/SKU 行/包裹，写到本地 Parquet；
再把旧的 GS 月表（407,898 行，发货口径至 2026-09-30）与 10 月起的 EN 增量拼成统一需求序列。

> 不做补货内核、不下单、不写 EN、不碰 Jack 的 SO→生产→DN→Shipment/PO 链路。
> FBA 消费需求不并入自发货序列；FBA 的工厂物料预留只作为上游约束记录。

## 快速开始

```bash
# 1) 离线测试（不联网）
uv run pytest self_fulfilled_demand/tests -q

# 2) 真实增量（只读；默认写 D:/Work/fzh-order-store/en-demand-v1）
uv run python -m self_fulfilled_demand.ingest \
  --sale-since "2026-10-01 00:00:00" \
  --modified-since "2026-10-01 00:00:00" \
  --validate-sept-sample 200 \
  --max-orders 30000

# 3) 把已有根目录 Parquet 收编成快照 + 离线审计（不重新拉取）
uv run python -m self_fulfilled_demand.finalize_store \
  --run-report D:/Work/fzh-order-store/en-demand-v1/runs/<run_id>.json \
  --expected-sale-orders 6800 --expected-modified-orders 27503

# 4) 生成统一消费输出
uv run python -m self_fulfilled_demand.consumer \
  --start 2026-09-01 --end 2026-10-31
```

凭证从 `EN_API/.env`（父仓库）或 `ERP_API_KEY` / `ERP_API_SECRET` 环境变量读取，
不打印、不落盘。默认环境是生产只读。

## 产出

```
D:/Work/fzh-order-store/en-demand-v1/
├── CURRENT                      # 最后成功提交的快照指针
├── snapshots/<commit_id>/       # 五张表 + commit.json
├── runs/<run_id>.json           # 每次运行的数量对账/失败/覆盖
├── manifest.json                # 水位、源覆盖、partial、文件哈希
├── finalize_report.json         # 收编+审计结果
└── consumer/                    # demand / deferred / fba / quarantine / overlap …
```

## 关键口径

- 拆单 `_1`/`_2`：行主键用完整单据名，`base_order_id` 只做分组，不合并。
- 行身份：优先 `raw_data.orderDetails[].orderDetailsId`；回退键含 `idx`，同单同 SKU 多行不吞。
- 取消：`invalid=1`（EN 状态字段没有「已取消」）。
- 组件：`is_deliver_good=0` → `embedded_component`，不算成品需求。
- 皮壳/半成品/成品分列 `demand_kind`，不合成「成品需求」。
- 代发/unknown：有效即保留；默认不进主建议时进 `deferred` 并给责任原因。
- GS 是发货口径：9 月下单 10 月发货、旧单取消/改量由 EN 补入或覆盖（行级，可审计）。
- UOM 未知保留 null，不猜；补货聚合已按 SKU×仓×日给出。

规范层：SKU→EN 物料、仓库旧名/子仓、EN Item.stock_uom；未知保持原因并阻断净额。
详细文档：[docs/index.md](docs/index.md) ·
[canonical](docs/reference/canonical-demand.md) ·
[EN schema](docs/reference/en-order-schema.md) ·
[消费接口](docs/reference/consumer-interface.md)
