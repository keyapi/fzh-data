# -*- coding: utf-8 -*-
"""账期定稿修正凭据：从不可变原件生成 corrected 副本（不覆盖原件、不写 OA/GSheet）。

C02（gate_remediation_plan_20261120.md U-E2 / E2.3）在原有「审批编号 + 行指纹」
匹配之上补齐**凭据校验**，任何一项不满足都在写任何文件之前失败：

- schema：``schema_version`` / ``revision`` / ``created_at`` / ``source_files`` / ``corrections``；
- 授权状态：只有 ``status == approved`` 且带 ``confirmed_by`` 的修正能应用；
- 源与附件 hash：源 xlsx md5 必须与 ``source_files[period].md5`` 一致（防止传入已覆盖的
  corrected 副本），附件必须存在且 md5 与凭据一致；
- 目标期：``scope.period`` 必须等于请求期，``scope.bucket`` 必须映射到同一 YYYYMM；
- 字段类型：文本列（账户/账号/平台/币种/日期）必须是字符串，金额列必须是有限十进制；
- 空 period 集合不产出 corrected 副本；preview/draft 凭据禁止走正式写入口；
- 行指纹必须恰好命中 1 行；``before`` 必须与当前单元格一致；同一 (行, 列) 不能被两条
  修正同时改（重复应用）。
"""
from __future__ import annotations

import hashlib
import json
import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path

import openpyxl

from bucket_meta import bucket_yyyymm

SCHEMA_VERSION = 1
APPROVED = "approved"

# 顶层 status/mode 命中这些即视为「预览/草案」，不能用于正式写入口。
_PREVIEW_MARKERS = {"preview", "draft", "pending", "rejected", "revoked", "cancelled", "canceled"}

_MD5_RE = re.compile(r"^[0-9a-f]{32}$")

# 这些列按文本比较/写入；其余按十进制数值。
_TEXT_HINTS = ("账户", "账号", "平台", "币种", "日期")


class RemediationError(ValueError):
    """凭据/匹配/授权不满足时的硬失败。"""


def _text(value) -> str:
    if isinstance(value, (datetime, date)):
        return value.strftime("%Y-%m-%d")
    return "" if value is None else str(value).strip()


def _is_text_column(col) -> bool:
    return any(h in str(col) for h in _TEXT_HINTS)


def md5_file(path: Path) -> str:
    h = hashlib.md5()
    with Path(path).open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def load_corrections(path: Path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _periods(corrections: dict) -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = {}
    for item in corrections.get("corrections", []) or []:
        period = str(((item or {}).get("scope") or {}).get("period", ""))
        out.setdefault(period, []).append(item)
    return out


def _as_decimal(value, *, label: str) -> Decimal:
    if isinstance(value, bool):
        raise RemediationError(f"{label} 不能是布尔值")
    if not isinstance(value, (str, int, float, Decimal)):
        raise RemediationError(f"{label} 类型非法: {type(value).__name__}")
    text = str(value).strip()
    if text == "":
        raise RemediationError(f"{label} 为空")
    try:
        d = Decimal(text)
    except (InvalidOperation, ValueError):
        raise RemediationError(f"{label} 不是合法十进制: {value!r}") from None
    if not d.is_finite():
        raise RemediationError(f"{label} 非有限值: {value!r}")
    return d


def _validate_field_change(correction_id: str, col: str, change) -> None:
    if not isinstance(change, (list, tuple)) or len(change) != 2:
        raise RemediationError(f"{correction_id}.{col}: 必须是 [before, after] 二元组")
    before, after = change
    for side, val in (("before", before), ("after", after)):
        if isinstance(val, bool) or isinstance(val, (dict, list)):
            raise RemediationError(f"{correction_id}.{col}: {side} 类型非法")
        if val is None:
            raise RemediationError(f"{correction_id}.{col}: {side} 不能为空")
    if _is_text_column(col):
        if not isinstance(after, str):
            raise RemediationError(f"{correction_id}.{col}: 文本列 after 必须是字符串")
        if not after.strip():
            raise RemediationError(f"{correction_id}.{col}: 文本列 after 不能为空")
    else:
        _as_decimal(before, label=f"{correction_id}.{col}.before")
        _as_decimal(after, label=f"{correction_id}.{col}.after")


def _value_equal(col, actual, want) -> bool:
    """单元格与凭据值比较：文本列按去空白字符串，数值列按 Decimal（19920 == 19920.0）。"""
    if _is_text_column(col):
        return _text(actual) == _text(want)
    try:
        return Decimal(_text(actual)) == Decimal(_text(want))
    except (InvalidOperation, ValueError):
        return _text(actual) == _text(want)


def _validate_item(item: dict, period: str, evidence_root: Path | None) -> None:
    cid = str(item.get("correction_id") or "").strip()
    scope = item.get("scope") or {}
    if str(scope.get("period", "")) != str(period):
        raise RemediationError(f"{cid}: scope.period={scope.get('period')!r} 与请求期 {period!r} 不符")
    bucket = scope.get("bucket")
    if bucket:
        yyyymm = bucket_yyyymm(str(bucket))
        if yyyymm != str(period):
            raise RemediationError(f"{cid}: scope.bucket={bucket!r} 映射月 {yyyymm} != {period}")

    status = str(item.get("status") or "").strip().lower()
    if status != APPROVED:
        raise RemediationError(f"{cid}: 状态 {status!r} 未获批准（只有 {APPROVED!r} 可应用）")
    if not str(item.get("confirmed_by") or "").strip():
        raise RemediationError(f"{cid}: 缺 confirmed_by（授权人）")
    if not str(item.get("approval_id") or "").strip():
        raise RemediationError(f"{cid}: 缺 approval_id")

    key = item.get("source_row_key")
    if not isinstance(key, dict) or not key:
        raise RemediationError(f"{cid}: source_row_key 必须是非空对象（不能只用审批编号定位）")
    for k, v in key.items():
        if isinstance(v, (dict, list)):
            raise RemediationError(f"{cid}: source_row_key.{k} 类型非法")

    changes = item.get("field_changes")
    if not isinstance(changes, dict) or not changes:
        raise RemediationError(f"{cid}: field_changes 必须是非空对象")
    for col, change in changes.items():
        _validate_field_change(cid, col, change)

    evidence = item.get("evidence") or {}
    attachment = str(evidence.get("attachment") or "").strip()
    attachment_md5 = str(evidence.get("attachment_md5") or "").strip().lower()
    if not attachment:
        raise RemediationError(f"{cid}: evidence.attachment 为空")
    if not _MD5_RE.match(attachment_md5):
        raise RemediationError(f"{cid}: evidence.attachment_md5 不是 32 位 md5")
    if evidence_root is None:
        raise RemediationError(f"{cid}: 未提供 evidence_root，无法核验附件 hash")
    att_path = Path(evidence_root) / attachment
    if not att_path.is_file():
        raise RemediationError(f"{cid}: 附件不存在: {att_path}")
    actual = md5_file(att_path)
    if actual.lower() != attachment_md5:
        raise RemediationError(f"{cid}: 附件 md5 不符: {actual} != {attachment_md5}")


def validate_corrections(
    corrections: dict,
    *,
    period: str,
    src: Path,
    evidence_root: Path | None = None,
    src_md5: str | None = None,
) -> dict:
    """校验整份凭据里属于 ``period`` 的修正，返回可应用清单；任一不满足直接抛错。"""
    if not isinstance(corrections, dict):
        raise RemediationError("corrections 顶层必须是对象")
    if corrections.get("schema_version") != SCHEMA_VERSION:
        raise RemediationError(
            f"schema_version={corrections.get('schema_version')!r} 不受支持（需要 {SCHEMA_VERSION}）"
        )
    if not str(corrections.get("revision") or "").strip():
        raise RemediationError("缺 revision")
    created = corrections.get("created_at")
    if created is not None:
        try:
            datetime.fromisoformat(str(created))
        except ValueError:
            raise RemediationError(f"created_at 不是 ISO 时间: {created!r}") from None

    mode = str(corrections.get("status") or corrections.get("mode") or "").strip().lower()
    if mode in _PREVIEW_MARKERS:
        raise RemediationError(f"凭据状态 {mode!r}：preview/draft 不能走正式写入口")

    items = corrections.get("corrections")
    if not isinstance(items, list) or not items:
        raise RemediationError("corrections 必须是非空数组")
    ids: list[str] = []
    for item in items:
        if not isinstance(item, dict):
            raise RemediationError("corrections 元素必须是对象")
        cid = str(item.get("correction_id") or "").strip()
        if not cid:
            raise RemediationError("存在缺 correction_id 的修正")
        ids.append(cid)
    if len(set(ids)) != len(ids):
        dup = sorted({x for x in ids if ids.count(x) > 1})
        raise RemediationError(f"correction_id 重复: {dup}")

    period_items = [
        i for i in items if str(((i.get("scope") or {}).get("period", ""))) == str(period)
    ]
    if not period_items:
        raise RemediationError(f"period {period!r} 没有任何 corrections；拒绝产出空 corrected 副本")

    source_files = corrections.get("source_files")
    if not isinstance(source_files, dict):
        raise RemediationError("缺 source_files")
    meta = source_files.get(str(period))
    if not isinstance(meta, dict) or not str(meta.get("md5") or "").strip():
        raise RemediationError(f"source_files[{period!r}] 缺 md5")
    recorded = str(meta["md5"]).strip().lower()
    if not _MD5_RE.match(recorded):
        raise RemediationError(f"source_files[{period!r}].md5 不是 32 位 md5")
    actual = (src_md5 or md5_file(src)).lower()
    if recorded != actual:
        raise RemediationError(
            f"源文件 md5 不符（凭据 {recorded} != 实际 {actual}）；"
            "可能源已被覆盖或传入的是 corrected 副本"
        )

    for item in period_items:
        _validate_item(item, str(period), evidence_root)

    return {"period": str(period), "source_md5": actual, "items": period_items}


def _match_row(ws, idx: dict, approval: str, key: dict) -> int:
    matches: list[int] = []
    for row in range(2, ws.max_row + 1):
        if _text(ws.cell(row=row, column=idx["审批编号"]).value) != approval:
            continue
        if all(
            col in idx and _value_equal(col, ws.cell(row=row, column=idx[col]).value, want)
            for col, want in key.items()
        ):
            matches.append(row)
    if len(matches) != 1:
        raise RemediationError(f"审批 {approval} 命中 {len(matches)} 行（要求恰好 1 行）: {matches}")
    return matches[0]


def apply_corrections(
    *,
    src: Path,
    corrections: dict,
    period: str,
    out: Path,
    evidence_root: Path | None = None,
    preview: bool = False,
    src_md5: str | None = None,
) -> dict:
    """应用指定账期的修正，写 corrected 副本，返回应用清单。

    ``preview=True`` 只计算将改哪些格，**不写任何文件**；正式模式才会保存 ``out``。
    所有校验在打开工作簿前后、保存之前完成，失败不会留下半截副本。
    """
    src = Path(src)
    out = Path(out)
    if src.resolve() == out.resolve():
        raise RemediationError(f"src 与 out 不能是同一个文件: {src}")

    validation = validate_corrections(
        corrections, period=period, src=src, evidence_root=evidence_root, src_md5=src_md5
    )

    wb = openpyxl.load_workbook(src)
    ws = wb["核算行"] if "核算行" in wb.sheetnames else wb[wb.sheetnames[0]]
    header = [_text(c.value) for c in ws[1]]
    idx = {name: i + 1 for i, name in enumerate(header) if name}
    if "审批编号" not in idx:
        raise RemediationError(f"{src} 缺少 审批编号 列")

    applied: list[dict] = []
    seen_targets: set[tuple[int, int]] = set()
    for item in validation["items"]:
        cid = str(item["correction_id"])
        approval = _text(item["approval_id"])
        row = _match_row(ws, idx, approval, item["source_row_key"])
        diffs = []
        for col, change in item["field_changes"].items():
            if col not in idx:
                raise RemediationError(f"{cid}: 修正列不存在: {col}")
            before, after = change
            col_no = idx[col]
            if (row, col_no) in seen_targets:
                raise RemediationError(f"{cid}: 同一行同一列被重复修正: 第 {row} 行 {col}")
            seen_targets.add((row, col_no))
            cell = ws.cell(row=row, column=col_no)
            if not _value_equal(col, cell.value, before):
                raise RemediationError(
                    f"{cid}: 列 {col} before 不符: 当前 {_text(cell.value)!r} != 凭据 {before!r}"
                )
            cell.value = str(after) if _is_text_column(col) else float(_as_decimal(after, label=f"{cid}.{col}"))
            diffs.append({"column": col, "before": before, "after": after})
        applied.append(
            {
                "correction_id": cid,
                "excel_row": row,
                "approval_id": approval,
                "diffs": diffs,
            }
        )

    if preview:
        return {
            "period": str(period),
            "preview": True,
            "src": str(src),
            "source_md5": validation["source_md5"],
            "out": None,
            "applied": applied,
        }

    out.parent.mkdir(parents=True, exist_ok=True)
    wb.save(out)
    return {
        "period": str(period),
        "preview": False,
        "src": str(src),
        "out": str(out),
        "source_md5": validation["source_md5"],
        "out_md5": md5_file(out),
        "applied": applied,
    }
