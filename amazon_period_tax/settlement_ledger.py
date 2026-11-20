# -*- coding: utf-8 -*-
"""结算台账：扫描全部账期桶，按 settlement-id / 内容 md5 找跨桶重复（**只报告，不删不改**）。

用途：同一个 Amazon 结算文件被复制进相邻两个账期桶（例如 7 月结算副本落到 8 月桶），
Tax 会被跨月重复计入。本模块只产清单，人工确认后再处理文件。

    uv run python amazon_period_tax/scripts/settlement_ledger.py --root "D:\\NAS与我共享\\2023年度账期资料"
"""
from __future__ import annotations

import hashlib
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
_PKG = Path(__file__).resolve().parent
_DING = _REPO / "dingtalk" / "dingtalk_oa_approval"
for _p in (_PKG, _DING):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from bucket_meta import bucket_period_range  # noqa: E402
from read_amz_txt import (  # noqa: E402
    DEFAULT_EXCLUDE_FOLDERS,
    parse_settlement_meta,
    settlement_window_date,
)


def _account_from_name(file_name: str) -> str:
    from read_amz_txt import _account_from_filename  # 复用同一套渠道账号规范化

    return _account_from_filename(file_name)


def scan_bucket(
    bucket_dir: Path,
    *,
    exclude_folders: tuple[str, ...] = DEFAULT_EXCLUDE_FOLDERS,
) -> list[dict]:
    """扫描一个账期桶（一级人名文件夹）→ 每个 AMZ txt 一条记录。读失败记 error 记录。"""
    records: list[dict] = []
    if not bucket_dir.is_dir():
        return records
    window = bucket_period_range(bucket_dir.name)
    for sub in sorted(p for p in bucket_dir.iterdir() if p.is_dir() and not p.name.startswith(".")):
        if sub.name in exclude_folders:
            continue
        for f in sorted(sub.iterdir()):
            if not f.is_file() or not f.name.upper().startswith("AMZ") or not f.name.lower().endswith(".txt"):
                continue
            rel = f"{sub.name}/{f.name}"
            try:
                raw = f.read_bytes()
            except OSError as e:
                records.append(
                    {"bucket": bucket_dir.name, "rel": rel, "error": str(e), "md5": None, "settlement_id": None}
                )
                continue
            try:
                text = raw.decode("utf-8")
            except UnicodeDecodeError:
                text = raw.decode("latin-1")
            sid, end_raw = parse_settlement_meta(text)
            window_date, end, deposit = settlement_window_date(text)
            records.append(
                {
                    "bucket": bucket_dir.name,
                    "rel": rel,
                    "md5": hashlib.md5(raw).hexdigest(),
                    "settlement_id": sid,
                    "settlement_end_date": end.isoformat() if end else None,
                    "deposit_date": deposit.isoformat() if deposit else None,
                    "window_date": window_date.isoformat() if window_date else None,
                    "end_raw": end_raw,
                    "account": _account_from_name(f.name),
                    "in_bucket_window": (
                        (window[0] <= window_date <= window[1]) if (window and window_date) else None
                    ),
                    "error": None,
                }
            )
    return records


def scan_buckets(root: Path, *, exclude_folders: tuple[str, ...] = DEFAULT_EXCLUDE_FOLDERS) -> list[dict]:
    """扫描根目录下所有 ``账期*`` 桶。"""
    records: list[dict] = []
    for bucket in sorted(p for p in Path(root).iterdir() if p.is_dir() and p.name.startswith("账期")):
        records.extend(scan_bucket(bucket, exclude_folders=exclude_folders))
    return records


def find_duplicates(records: list[dict]) -> list[dict]:
    """按 settlement-id（主）和 md5（兜底）找重复组；组内文件 ≥2 或跨桶即报告。"""
    out: list[dict] = []
    ok = [r for r in records if not r.get("error")]

    by_sid: dict[str, list[dict]] = {}
    for r in ok:
        if r.get("settlement_id"):
            by_sid.setdefault(str(r["settlement_id"]), []).append(r)
    for sid, group in sorted(by_sid.items()):
        buckets = sorted({r["bucket"] for r in group})
        if len(group) < 2:
            continue
        out.append(
            {
                "type": "settlement-id",
                "key": sid,
                "buckets": buckets,
                "cross_bucket": len(buckets) > 1,
                "files": sorted(f"{r['bucket']}/{r['rel']}" for r in group),
                "settlement_end_dates": sorted(
                    {r.get("settlement_end_date") or "?" for r in group}
                ),
            }
        )

    by_md5: dict[str, list[dict]] = {}
    for r in ok:
        if r.get("md5"):
            by_md5.setdefault(str(r["md5"]), []).append(r)
    reported_sids = {d["key"] for d in out if d["type"] == "settlement-id"}
    for md5, group in sorted(by_md5.items()):
        buckets = sorted({r["bucket"] for r in group})
        if len(group) < 2:
            continue
        # settlement-id 已覆盖的组不重复报；md5 组只在「id 缺失/不一致」时补充
        sids = {str(r["settlement_id"]) for r in group if r.get("settlement_id")}
        if len(sids) == 1 and next(iter(sids)) in reported_sids:
            continue
        out.append(
            {
                "type": "md5",
                "key": md5,
                "buckets": buckets,
                "cross_bucket": len(buckets) > 1,
                "files": sorted(f"{r['bucket']}/{r['rel']}" for r in group),
                "settlement_end_dates": sorted(
                    {r.get("settlement_end_date") or "?" for r in group}
                ),
            }
        )
    return out


def format_report(records: list[dict], duplicates: list[dict]) -> list[str]:
    lines = [f"扫描 txt 记录 {len(records)} 条（读取失败 {sum(1 for r in records if r.get('error'))} 条）"]
    out_of_window = [r for r in records if r.get("in_bucket_window") is False]
    lines.append(f"内部结算日不在所属桶窗口内: {len(out_of_window)} 条")
    for r in out_of_window:
        lines.append(
            f"  OUT-OF-PERIOD {r['bucket']}/{r['rel']} window={r.get('window_date')} "
            f"end={r.get('settlement_end_date')} deposit={r.get('deposit_date')}"
        )
    if not duplicates:
        lines.append("重复结算: 无")
    else:
        lines.append(f"重复结算: {len(duplicates)} 组")
        for d in duplicates:
            tag = "跨桶" if d["cross_bucket"] else "同桶"
            lines.append(
                f"  [{d['type']} {tag}] {d['key']} 出现在 {len(d['buckets'])} 个桶: "
                + " / ".join(d["buckets"])
            )
            for f in d["files"]:
                lines.append(f"      {f}")
    return lines
