# -*- coding: utf-8 -*-
"""非 Amazon 附件最小证据（N1–N5）：CSV/XLSX 金额出现性 + 人工签字清单。

对应 ``gate_remediation_plan_20261120.md`` U-N：

- **N1** 关联按 ``processInstanceId`` + 子行稳定指纹 + ``fileId``，不只按附件名。
- **N2** CSV 必须声明 encoding/delimiter/decimal/thousands；XLSX 逐 sheet 逐单元格解析
  成有限 Decimal，保留 sheet/行/列/原值。**禁止 substring**：``100`` 不命中 ``1000``、
  ``+10`` 不命中 ``-10``、歧义的 ``1,23`` 不猜 ``123``。
- **N3** 0 命中 → ``mismatch``；>1 候选 → ``ambiguous``；恰好 1 → ``occurrence_only``。
  ``occurrence_only`` **仍需人工签字**，不会自动升级成语义核对。
- **N4** PDF / 图片 / 未知格式 / occurrence_only 统一进人工签字清单；缺附件、缺签字或
  hash 变化一律不通过。本模块**没有任何自动 approve 路径**。
- **N5** 同账号/币种/周期历史中位数 >10 倍或 <0.1 倍只作提示（样本 ≥3），不替代逐笔签字。

只读：不写 GSheet / NAS / Excel。
"""
from __future__ import annotations

import csv
import hashlib
import io
import math
import re
from dataclasses import dataclass, field, replace
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Iterable

from amounts import parse_amount_strict

AMOUNT_TOLERANCE = Decimal("0.01")

# 图片/PDF/未知格式一律人工；不因库不支持就从分母里消失。
UNSUPPORTED_SUFFIXES = {".pdf", ".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".heic", ".tif", ".tiff", ".zip", ".xls"}
CSV_SUFFIXES = {".csv", ".tsv"}

# 纯字符串金额的保守判定：带小数/千分位，或不超过 9 位纯数字（更长的一律当 ID）。
_MONEY_STRING = re.compile(r"^[+-]?(?:\d{1,3}(?:[,.]\d{3})+(?:[.,]\d+)?|\d+[.,]\d+|\d{1,9})$")


@dataclass(frozen=True)
class AmountFormat:
    """CSV/XLSX 的**声明式**格式；不声明就不猜区域写法。"""

    encoding: str = "utf-8-sig"
    delimiter: str | None = None  # None → 按文件内容嗅探（只认 , ; \\t |）
    decimal_separator: str = "auto"
    thousands: str = ","
    header_row: int = 1


@dataclass(frozen=True)
class AmountOccurrence:
    sheet: str
    row: int
    col: int
    cell: str
    header: str
    raw: str
    value: Decimal

    def to_dict(self) -> dict:
        return {
            "sheet": self.sheet,
            "row": self.row,
            "col": self.col,
            "cell": self.cell,
            "header": self.header,
            "raw": self.raw,
            "value": str(self.value),
        }


@dataclass
class OccurrenceResult:
    path: str
    sha256: str
    kind: str  # csv / xlsx / unsupported
    status: str  # mismatch / occurrence_only / ambiguous / unsupported
    occurrences: list[AmountOccurrence] = field(default_factory=list)
    reason: str | None = None
    target: Decimal | None = None

    def to_dict(self) -> dict:
        return {
            "path": self.path,
            "sha256": self.sha256,
            "kind": self.kind,
            "status": self.status,
            "reason": self.reason,
            "target": None if self.target is None else str(self.target),
            "occurrences": [o.to_dict() for o in self.occurrences],
        }


def sha256_file(path: str | Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _decode(raw: bytes, fmt: AmountFormat) -> str:
    for enc in (fmt.encoding, "utf-8-sig", "utf-8", "gbk", "latin-1"):
        try:
            return raw.decode(enc)
        except (UnicodeDecodeError, LookupError):
            continue
    return raw.decode("latin-1", errors="replace")


def _sniff_delimiter(sample: str) -> str:
    counts = {d: sample.count(d) for d in (",", ";", "\t", "|")}
    best = max(counts, key=counts.get)
    return best if counts[best] else ","


def _cell_decimal(value, fmt: AmountFormat) -> Decimal | None:
    """单元格 → Decimal；只接受明确的数值，不做 substring / 日期 / ID 误判。"""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, Decimal):
        return value if value.is_finite() else None
    if isinstance(value, int):
        return Decimal(value)
    if isinstance(value, float):
        if not math.isfinite(value):
            return None
        return Decimal(str(value))
    s = str(value).strip()
    if not s or not _MONEY_STRING.match(s):
        return None
    try:
        parsed = parse_amount_strict(s, decimal_separator=fmt.decimal_separator)
    except ValueError:
        return None
    return None if parsed is None else Decimal(str(parsed))


def _scan_csv(path: Path, fmt: AmountFormat, target: Decimal) -> OccurrenceResult:
    raw = path.read_bytes()
    text = _decode(raw, fmt)
    delimiter = fmt.delimiter or _sniff_delimiter(text.splitlines()[0] if text.splitlines() else "")
    reader = csv.reader(io.StringIO(text), delimiter=delimiter)
    rows = list(reader)
    header: list[str] = rows[fmt.header_row - 1] if len(rows) >= fmt.header_row else []
    hits: list[AmountOccurrence] = []
    for r_idx, row in enumerate(rows, start=1):
        if r_idx <= fmt.header_row:
            continue
        for c_idx, cell in enumerate(row, start=1):
            val = _cell_decimal(cell, fmt)
            if val is None:
                continue
            if abs(val - target) <= AMOUNT_TOLERANCE:
                col_letter = ""
                if c_idx <= len(header):
                    col_letter = str(header[c_idx - 1]).strip()
                hits.append(
                    AmountOccurrence(
                        sheet="csv",
                        row=r_idx,
                        col=c_idx,
                        cell=f"R{r_idx}C{c_idx}",
                        header=col_letter,
                        raw=str(cell),
                        value=val,
                    )
                )
    return OccurrenceResult(
        path=str(path),
        sha256=hashlib.sha256(raw).hexdigest(),
        kind="csv",
        status=_status_for(hits),
        occurrences=hits,
        target=target,
    )


def _scan_xlsx(path: Path, fmt: AmountFormat, target: Decimal) -> OccurrenceResult:
    from openpyxl import load_workbook  # 延迟导入：只在真的扫 XLSX 时需要

    raw = path.read_bytes()
    wb = load_workbook(io.BytesIO(raw), read_only=True, data_only=True)
    hits: list[AmountOccurrence] = []
    for ws in wb.worksheets:
        header: list[str] = []
        for r_idx, row in enumerate(ws.iter_rows(values_only=True), start=1):
            if r_idx == fmt.header_row:
                header = ["" if v is None else str(v).strip() for v in row]
                continue
            if r_idx < fmt.header_row:
                continue
            for c_idx, value in enumerate(row, start=1):
                val = _cell_decimal(value, fmt)
                if val is None:
                    continue
                if abs(val - target) <= AMOUNT_TOLERANCE:
                    hdr = header[c_idx - 1] if c_idx <= len(header) else ""
                    hits.append(
                        AmountOccurrence(
                            sheet=ws.title,
                            row=r_idx,
                            col=c_idx,
                            cell=f"{_col_letter(c_idx)}{r_idx}",
                            header=hdr,
                            raw="" if value is None else str(value),
                            value=val,
                        )
                    )
    wb.close()
    return OccurrenceResult(
        path=str(path),
        sha256=hashlib.sha256(raw).hexdigest(),
        kind="xlsx",
        status=_status_for(hits),
        occurrences=hits,
        target=target,
    )


def _col_letter(idx: int) -> str:
    letters = ""
    while idx > 0:
        idx, rem = divmod(idx - 1, 26)
        letters = chr(65 + rem) + letters
    return letters


def _status_for(hits: list[AmountOccurrence]) -> str:
    if len(hits) == 0:
        return "mismatch"
    if len(hits) > 1:
        return "ambiguous"
    return "occurrence_only"


def find_amount_occurrences(
    path: str | Path,
    target: Decimal | str | float | int,
    *,
    fmt: AmountFormat | None = None,
    tolerance: Decimal = AMOUNT_TOLERANCE,
) -> OccurrenceResult:
    """在附件里找**一个**目标金额的精确出现位置（不猜、不 substring）。"""
    p = Path(path)
    fmt = fmt or AmountFormat()
    if isinstance(target, Decimal):
        target_d = target
    elif isinstance(target, bool):
        raise ValueError("布尔值不是金额")
    elif isinstance(target, (int, float)):
        target_d = Decimal(str(target))
    else:
        target_d = Decimal(str(target).strip())
    suffix = p.suffix.lower()
    if suffix in CSV_SUFFIXES:
        return _scan_csv(p, fmt, target_d)
    if suffix in {".xlsx", ".xlsm"}:
        return _scan_xlsx(p, fmt, target_d)
    raw = p.read_bytes() if p.is_file() else b""
    return OccurrenceResult(
        path=str(p),
        sha256=hashlib.sha256(raw).hexdigest() if raw else "",
        kind="unsupported",
        status="unsupported",
        reason=f"unsupported_format:{suffix or 'none'}",
        target=target_d,
    )


# --------------------------------------------------------------- 人工签字清单

PENDING = "pending"
SIGNED = "signed"
REJECTED = "rejected"


@dataclass
class ManualEntry:
    """人工签字一行。没有签字字段就是 pending；不会自动 approve。"""

    row_id: str
    platform: str
    account: str
    currency: str
    oa_amount: Decimal | None
    attachment_name: str
    attachment_sha256: str
    location: str = ""
    reason: str = ""
    transcribed_value: Decimal | None = None
    transcribed_note: str = ""
    checker: str = ""
    finance_reviewer: str = ""
    approved_at: str = ""
    valid_until: str = ""
    proposal_hash: str = ""
    status: str = PENDING

    def is_signed(
        self,
        *,
        today: date | None = None,
        observed_sha256: str | None = None,
        observed_proposal_hash: str | None = None,
    ) -> tuple[bool, str]:
        today = today or date.today()
        if self.status != SIGNED:
            return False, "not_signed"
        missing = [
            name
            for name, value in (
                ("checker", self.checker),
                ("finance_reviewer", self.finance_reviewer),
                ("approved_at", self.approved_at),
                ("proposal_hash", self.proposal_hash),
                ("transcribed_value", self.transcribed_value),
            )
            if value in (None, "")
        ]
        if missing:
            return False, f"signature_incomplete:{','.join(missing)}"
        if observed_sha256 and self.attachment_sha256 and observed_sha256 != self.attachment_sha256:
            return False, "attachment_hash_changed"
        if self.oa_amount is not None and self.transcribed_value is not None:
            if abs(Decimal(self.transcribed_value) - Decimal(self.oa_amount)) > AMOUNT_TOLERANCE:
                return False, "transcribed_amount_mismatch"
        if self.valid_until:
            try:
                until = date.fromisoformat(self.valid_until[:10])
            except ValueError:
                return False, "bad_valid_until"
            if today > until:
                return False, "signature_expired"
        if observed_proposal_hash and observed_proposal_hash != self.proposal_hash:
            return False, "proposal_hash_changed"
        return True, "signed"

    def to_dict(self) -> dict:
        return {
            "row_id": self.row_id,
            "platform": self.platform,
            "account": self.account,
            "currency": self.currency,
            "oa_amount": None if self.oa_amount is None else str(self.oa_amount),
            "attachment_name": self.attachment_name,
            "attachment_sha256": self.attachment_sha256,
            "location": self.location,
            "reason": self.reason,
            "transcribed_value": None if self.transcribed_value is None else str(self.transcribed_value),
            "transcribed_note": self.transcribed_note,
            "checker": self.checker,
            "finance_reviewer": self.finance_reviewer,
            "approved_at": self.approved_at,
            "valid_until": self.valid_until,
            "proposal_hash": self.proposal_hash,
            "status": self.status,
        }


def build_entry(
    *,
    row_id: str,
    platform: str,
    account: str,
    currency: str,
    oa_amount: Decimal | None,
    attachment_name: str,
    attachment_sha256: str,
    result: OccurrenceResult | None = None,
    reason: str = "",
) -> ManualEntry:
    """把附件扫描结果转成待签清单项；脚本不会填写签字字段。"""
    location = ""
    if result and result.occurrences:
        first = result.occurrences[0]
        location = f"{first.sheet}!{first.cell}"
        if len(result.occurrences) > 1:
            location = "; ".join(f"{o.sheet}!{o.cell}" for o in result.occurrences)
    return ManualEntry(
        row_id=row_id,
        platform=platform,
        account=account,
        currency=currency,
        oa_amount=oa_amount,
        attachment_name=attachment_name,
        attachment_sha256=attachment_sha256,
        location=location,
        reason=reason or (result.reason if result and result.reason else (result.status if result else "")),
        status=PENDING,
    )


def sign_entry(
    entry: ManualEntry,
    *,
    transcribed_value: Decimal | str,
    checker: str,
    finance_reviewer: str,
    approved_at: str,
    proposal_hash: str,
    valid_until: str = "",
    transcribed_note: str = "",
) -> ManualEntry:
    """显式人工签字（仅在人工核对后调用；不提供任何自动路径）。"""
    value = transcribed_value if isinstance(transcribed_value, Decimal) else Decimal(str(transcribed_value))
    return replace(
        entry,
        transcribed_value=value,
        transcribed_note=transcribed_note,
        checker=checker,
        finance_reviewer=finance_reviewer,
        approved_at=approved_at,
        valid_until=valid_until,
        proposal_hash=proposal_hash,
        status=SIGNED,
    )


def worklist_summary(entries: Iterable[ManualEntry], *, today: date | None = None) -> dict:
    today = today or date.today()
    entries = list(entries)
    pending = [e for e in entries if not e.is_signed(today=today)[0]]
    return {
        "total": len(entries),
        "signed_valid": len(entries) - len(pending),
        "pending": len(pending),
        "pending_rows": [e.row_id for e in pending],
        "blocking": bool(pending),
    }


def history_anomaly_hint(amount: Decimal, history: Iterable[Decimal]) -> dict:
    """N5：同账号/币种/周期历史中位数对比，仅提示，不参与批准。"""
    values = sorted(Decimal(x) for x in history)
    if len(values) < 3:
        return {"status": "insufficient_history", "samples": len(values)}
    mid = len(values) // 2
    median = values[mid] if len(values) % 2 else (values[mid - 1] + values[mid]) / 2
    if median == 0:
        return {"status": "insufficient_history", "samples": len(values), "reason": "median_zero"}
    ratio = abs(amount) / abs(median)
    hint = "normal"
    if ratio > 10:
        hint = "high_10x"
    elif ratio < Decimal("0.1"):
        hint = "low_0.1x"
    return {"status": hint, "samples": len(values), "median": str(median), "ratio": str(ratio.quantize(Decimal("0.0001")))}
