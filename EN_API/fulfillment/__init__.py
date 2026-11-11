"""统一履约查询入口 —— 在 item_shipment_status 引擎之上做 多输入 / 阶段 / 证据分层 / 异常与下一行动。

分层（蓝图 §10）::

    ERPNextSource  =  EN_API/item_shipment_status.py （已验证的查询函数，本包**不改**它）
    本包（fulfillment/）
      codes    输入解析（客户码 / 物料码，逐输入保留命中与未命中）
      assemble 逐输入查询 → 并集 → 事实层（SO/PP/WO/JC/DN）+ 复用引擎的 classify_anomalies
      stages   阶段 0–3 状态机（蓝图 §3）
      quantities 数量阶梯 + 对账（蓝图 §3.1）
      evidence 事实/推导/估算 分层（蓝图 §4）
      rules    异常 §8 结构 + 下一行动（蓝图 §8）
      report   §9 统一查询结果分区 + §9.1 顶部摘要
      render   JSON(权威) / 控制台 / Excel 三个适配器
      cli      编排

设计取舍：**包裹引擎而非整体搬迁**。引擎带 fixture 断言与单测（`tests/test_item_shipment_status.py`
用 `monkeypatch.setattr(iss, "api_get_status")` 打桩，要求 `paginated_get` 与 `api_get_status`
同处一个模块命名空间），整体搬迁会让该打桩失效且回归风险高。包裹则引擎与测试零改动。
"""
import sys
from pathlib import Path

# 允许 `import item_shipment_status`（引擎）+ `import fulfillment.*` 同时工作
_EN_DIR = Path(__file__).resolve().parents[1]
if str(_EN_DIR) not in sys.path:
    sys.path.insert(0, str(_EN_DIR))

__all__ = ["run_query", "FulfillmentQueryResult"]
