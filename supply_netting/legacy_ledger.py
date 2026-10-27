"""逐桶前向账的数量数学（原样引入，不重写）。

来源：commit ``aa93773b`` 的
``docs/research/supply-chain/2026-10-20/claude/experiments/business_phase/forward_net.py``
中的 ``bucket_gaps`` / ``assert_bucket_identities`` / ``allocate_so``。

只搬运这三个纯函数，**没有**搬运同一文件的 ``compute_row``（首桶塞全部供应）
与 ``harvest_total``（按运单号粗去重）——那两条正是本次任务明令禁止复用的逻辑。
搬入时仅去掉文档串里的实验脚本上下文，函数体逐字未改。
"""

from __future__ import annotations


def allocate_so(so_total, forecast_b, mode="earliest"):
    """Allocate the outstanding SO into buckets WITHOUT depending on a non-zero
    forecast. `proportional` falls back to `earliest` when the forecast is 0."""
    n = len(forecast_b)
    so_total = float(max(0.0, so_total or 0))
    if n == 0 or so_total == 0:
        return [0.0] * n
    total = float(sum(forecast_b))
    if mode == "earliest" or total <= 0:
        out = [0.0] * n
        out[0] = so_total
        return out
    if mode == "proportional":
        return [so_total * (f / total) for f in forecast_b]
    raise ValueError(f"unknown SO allocation mode: {mode}")


def bucket_gaps(buckets):
    out = []
    prev_closing = 0.0
    carried = 0.0
    for b in buckets:
        opening = float(b["opening"]) if b.get("opening") is not None else prev_closing
        receipts = float(b.get("receipts") or 0.0)
        demand = float(b.get("demand") or 0.0) + carried
        fulfilled = min(demand, opening + receipts)
        closing = opening + receipts - fulfilled
        unserved = demand - fulfilled
        out.append(dict(name=b.get("name", ""), opening=opening, receipts=receipts,
                        demand=demand, fulfilled=fulfilled, closing=closing,
                        unserved=unserved, gap=max(0.0, unserved)))
        prev_closing = closing
        carried = unserved
    return out


def assert_bucket_identities(bucket_row, tol=1e-9):
    lhs = bucket_row["opening"] + bucket_row["receipts"] - bucket_row["fulfilled"]
    assert abs(lhs - bucket_row["closing"]) <= tol, "opening+receipts-fulfilled != closing"
    rhs = bucket_row["demand"] - bucket_row["fulfilled"]
    assert abs(rhs - bucket_row["unserved"]) <= tol, "total_demand-fulfilled != unserved"
