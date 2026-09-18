"""FedEx 官方 Track API 批量查询工具（仿 ups_track）。

- 生产 env：FEDEX_API_KEY / FEDEX_SECRET_KEY / FEDEX_ACCOUNT_NUMBER（FEDEX_ENV=production）
- sandbox env：FEDEX_ENV=sandbox（用 2023 TEST key）
- 每请求最多 30 个跟踪号；保留完整 scanEvents 历史（销售核查关键节点用）。
"""

__version__ = "0.1.0"
