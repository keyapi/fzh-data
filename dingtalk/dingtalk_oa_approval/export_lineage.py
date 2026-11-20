# -*- coding: utf-8 -*-
"""D01：账期导出 N→M 守恒。

钉钉/aflow 导出的读取与过滤历史上有多处静默丢弃：缺日期行在读取阶段被
``df[df["账期日期"].notna()]`` 直接删掉、无表头的 sheet 被 ``continue`` 跳过、
非法日期行既不算本月也不算「其他月」。本模块把这些行全部保留下来，并给出
**互斥分区**的逐条计数，断言：

    N(读取行 + 读取失败行)
      = 保留 + 其他月 + 无效月/日期 + 审批状态排除 + 迟交排除 + 读取失败

每个分区都保留原始行（含 ``_sheet`` 与原始审批编号），没有「静默消失」。
只在内存里算，不写任何文件。写入前由 ``ExportLineage.is_publishable()`` 决定
是否允许产出正式定稿：读取失败、重复唯一键、或「有金额但缺/非法日期」任一出现
即拒绝，宁可不出文件也不出半截表。
"""
from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from parse import keep_approval

# 分区的固定名字（顺序即报告顺序）
KEPT = "kept"
OTHER_MONTH = "other_month"
INVALID_MONTH = "invalid_month"
EXCLUDED_STATUS = "excluded_status"
EXCLUDED_LATE = "excluded_late"
BUCKETS = (KEPT, OTHER_MONTH, INVALID_MONTH, EXCLUDED_STATUS, EXCLUDED_LATE)
READ_FAILED = "read_failed"

# 只要其中任一列有值，就认为这行「有金额」——缺日期有金额的行尤其危险。
AMOUNT_COLS = ("账期收款额", "销售额", "应收金额", "应收账款")

_EMPTY_COLUMNS = ["账期日期", "发起时间", "审批编号", "审批状态", "审批结果", "账期月", "_key"]


def empty_enriched_frame() -> pd.DataFrame:
    """读不到任何数据行（但有 sheet 失败）时用的空带列 frame，便于统一走分区。"""
    return pd.DataFrame(columns=_EMPTY_COLUMNS)


def _cell_text(value) -> str:
    if value is None:
        return ""
    try:
        if pd.isna(value):
            return ""
    except (TypeError, ValueError):
        pass
    return str(value).strip()


def row_has_amount(row) -> bool:
    """该行是否有金额：任一金额列非空即算（不要求能解析，解析另有门禁）。"""
    for col in AMOUNT_COLS:
        if _cell_text(row.get(col)) not in {"", "nan", "none"}:
            return True
    return False


def _status_ok(row) -> bool:
    return keep_approval(_cell_text(row.get("审批状态")), _cell_text(row.get("审批结果")))


def _is_real_key(key) -> bool:
    """业务键必须带审批编号；``审批编号`` 为空时不算可判重的键。"""
    text = str(key or "")
    approval = text.split("|", 1)[0].strip()
    return approval != ""


def classify_export_rows(
    df: pd.DataFrame, period: str, keys: set[str] | None = None
) -> dict[str, pd.DataFrame]:
    """把已 ``enrich`` 的行切成互斥分区。所有输入行都会落入恰好一个分区。"""
    if "账期月" not in df.columns:
        raise ValueError("classify_export_rows 需要先 enrich() 得到「账期月」列")
    keys = {str(k) for k in (keys or set())}

    month = df["账期月"].fillna("").astype(str)
    invalid = month == ""
    valid = ~invalid
    other = valid & (month != str(period))
    in_period = valid & (month == str(period))

    period_df = df.loc[in_period]
    if period_df.empty:
        status_ok = pd.Series(dtype=bool)
    else:
        status_ok = period_df.apply(_status_ok, axis=1).astype(bool)

    status_ok_rows = period_df.loc[status_ok] if not period_df.empty else period_df
    excluded_status = period_df.loc[~status_ok] if not period_df.empty else period_df

    if status_ok_rows.empty or not keys:
        late_mask = pd.Series(False, index=status_ok_rows.index)
    else:
        key_series = status_ok_rows["_key"].astype(str) if "_key" in status_ok_rows.columns else pd.Series("", index=status_ok_rows.index)
        late_mask = key_series.isin(keys).astype(bool)

    excluded_late = status_ok_rows.loc[late_mask]
    kept = status_ok_rows.loc[~late_mask]

    return {
        KEPT: kept,
        OTHER_MONTH: df.loc[other],
        INVALID_MONTH: df.loc[invalid],
        EXCLUDED_STATUS: excluded_status,
        EXCLUDED_LATE: excluded_late,
    }


def duplicate_keys(df: pd.DataFrame) -> list[str]:
    """保留分区里出现多次的业务唯一键（空键不算）。"""
    if df.empty or "_key" not in df.columns:
        return []
    keys = df["_key"].astype(str)
    keys = keys[keys.map(_is_real_key)]
    if keys.empty:
        return []
    dup = keys[keys.duplicated(keep=False)]
    return sorted({str(k) for k in dup.tolist()})


@dataclass
class ExportLineage:
    period: str
    partitions: dict[str, pd.DataFrame]
    counts: dict[str, int]
    n_total: int
    read_report: dict = field(default_factory=dict)
    duplicate_keys: list[str] = field(default_factory=list)
    keys: set[str] = field(default_factory=set)

    def late_key_hits(self) -> dict:
        """迟交登记逐键命中：matched 是真剔掉的键，unmatched 是没对上的陈旧键。"""
        late = self.partitions.get(EXCLUDED_LATE)
        matched = set()
        if late is not None and not late.empty and "_key" in late.columns:
            matched = {str(k) for k in late["_key"].tolist()}
        return {"matched": sorted(matched), "unmatched": sorted(self.keys - matched)}

    # ---------------------------------------------------------------- 计数
    @property
    def n_parsed(self) -> int:
        return int(sum(self.counts.get(b, 0) for b in BUCKETS))

    @property
    def n_read_failed(self) -> int:
        return int(self.counts.get(READ_FAILED, 0))

    @property
    def n_invalid_with_amount(self) -> int:
        invalid = self.partitions.get(INVALID_MONTH)
        if invalid is None or invalid.empty:
            return 0
        return int(sum(1 for _, row in invalid.iterrows() if row_has_amount(row)))

    def assert_conserved(self) -> "ExportLineage":
        """N = 保留 + 其他月 + 无效 + 状态排除 + 迟交排除 + 读取失败。"""
        bucket_sum = self.n_parsed
        expected = bucket_sum + self.n_read_failed
        if expected != self.n_total:
            raise AssertionError(
                f"D01 守恒失败: N={self.n_total} != 分区和({bucket_sum}) + 读取失败({self.n_read_failed})"
            )
        if bucket_sum != sum(self.counts[b] for b in BUCKETS):
            raise AssertionError("D01 分区计数与分区行数不一致")
        return self

    # ---------------------------------------------------------------- 门禁
    def blockers(self) -> list[str]:
        problems: list[str] = []
        if self.n_read_failed:
            sheets = [f"{f.get('sheet')!r}({f.get('reason')})" for f in self.read_report.get("failed", [])]
            problems.append(f"读取失败 {self.n_read_failed} 行/sheet: {', '.join(sheets[:5])}")
        if self.duplicate_keys:
            problems.append(f"重复唯一键 {len(self.duplicate_keys)}: {self.duplicate_keys[:5]}")
        n_amt = self.n_invalid_with_amount
        if n_amt:
            problems.append(f"缺/非法日期但有金额的行 {n_amt} 行（不得进入正式定稿）")
        n_corrupt = int(self.read_report.get("corrupted_id_rows", 0))
        if n_corrupt:
            problems.append(f"审批编号被浮点化（禁止伪恢复）{n_corrupt} 行")
        return problems

    def is_publishable(self) -> bool:
        return not self.blockers()

    def summary(self) -> str:
        parts = [f"period={self.period}", f"N={self.n_total}"]
        for b in BUCKETS:
            parts.append(f"{b}={self.counts.get(b, 0)}")
        parts.append(f"{READ_FAILED}={self.n_read_failed}")
        if self.keys:
            hits = self.late_key_hits()
            parts.append(f"late_keys_hit={len(hits['matched'])}/{len(self.keys)}")
        parts.append("publishable=" + ("yes" if self.is_publishable() else "no"))
        return " ".join(parts)


def build_export_lineage(
    df: pd.DataFrame,
    period: str,
    keys: set[str] | None = None,
    read_report: dict | None = None,
) -> ExportLineage:
    """构造并自校验一条 N→M 分区。``df`` 必须已 ``enrich``。"""
    partitions = classify_export_rows(df, period, keys)
    counts = {b: int(len(partitions[b])) for b in BUCKETS}
    report = read_report or {"failed": [], "rows_failed": 0}
    counts[READ_FAILED] = int(report.get("rows_failed", 0))
    n_total = int(len(df)) + counts[READ_FAILED]
    lineage = ExportLineage(
        period=str(period),
        partitions=partitions,
        counts=counts,
        n_total=n_total,
        read_report=report,
        duplicate_keys=duplicate_keys(partitions[KEPT]),
        keys={str(k) for k in (keys or set())},
    )
    return lineage.assert_conserved()
