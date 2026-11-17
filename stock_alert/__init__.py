"""通途库存低库存汇总 → 钉钉推送。

取数走通途 ERP2 库存接口 `erp2_stocks_stocksquery`（按仓库分页拉全量），
按「可用库存 < 阈值」筛出低库存 SKU，按仓汇总后用钉钉自定义机器人推送。

口径与限流说明见 docs/index.md。
"""

__all__ = ["client", "scan", "notify"]
