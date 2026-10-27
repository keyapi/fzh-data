"""EN 终端订单只读增量接入（en-demand-v1）。

职责边界
- 只读 EN（ERPNext）``Tongtool Order`` 及其子表，不写生产、不下单、不改单据。
- 产出本地 Parquet：raw + 标准化订单/行/包裹 + 变更事件 + manifest。
- 不改造 Jack 的 SO→生产→DN→Shipment/PO 链路；不把 Sales Order 当终端订单。
- FBA 订单单独标记，不进入自发货需求序列。

入口
- ``ingest.py``  增量拉取（CLI：``python -m self_fulfilled_demand.ingest``）
- ``consumer.py`` 旧 GS 407,898 行与 10 月增量的统一消费接口
"""

SCHEMA_VERSION = "en-demand-v1"

# 读取器版本：用于区分「旧进程拉的数据」与「修复后代码的验证」
READER_VERSION = "2026-10-27-pagination-snapshot-v2"
