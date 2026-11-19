# -*- coding: utf-8 -*-
"""账期定稿修正凭据：从不可变原件生成 corrected 副本（不覆盖原件、不写 OA/GSheet）。

设计见 `reports/remediation_plan_20261119.md` §2。匹配用「审批编号 + 行指纹（日期/账户/金额）」，
命中必须恰好 1 行，否则直接失败。
"""
from __future__ import annotations

import json
from datetime import datetime, date
from pathlib import Path

import openpyxl


def _text(value) -> str:
    if isinstance(value, (datetime, date)):
        return value.strftime("%Y-%m-%d")
    return "" if value is None else str(value).strip()


def load_corrections(path: Path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _periods(corrections: dict) -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = {}
    for item in corrections.get("corrections", []):
        period = str(item.get("scope", {}).get("period", ""))
        out.setdefault(period, []).append(item)
    return out


def apply_corrections(
    *,
    src: Path,
    corrections: dict,
    period: str,
    out: Path,
) -> dict:
    """应用指定账期的修正，写 corrected 副本，返回应用清单。"""
    wb = openpyxl.load_workbook(src)
    ws = wb["核算行"] if "核算行" in wb.sheetnames else wb[wb.sheetnames[0]]
    header = [_text(c.value) for c in ws[1]]
    idx = {name: i + 1 for i, name in enumerate(header) if name}
    if "审批编号" not in idx:
        raise KeyError(f"{src} 缺少 审批编号 列")

    applied = []
    for item in _periods(corrections).get(period, []):
        approval = str(item["approval_id"]).strip()
        key = item.get("source_row_key", {})
        matches = []
        for row in range(2, ws.max_row + 1):
            if _text(ws.cell(row=row, column=idx["审批编号"]).value) != approval:
                continue
            ok = True
            for col, want in key.items():
                if col not in idx:
                    raise KeyError(f"行指纹列不存在: {col}")
                if _text(ws.cell(row=row, column=idx[col]).value) != _text(want):
                    ok = False
                    break
            if ok:
                matches.append(row)
        if len(matches) != 1:
            raise ValueError(f"{item['correction_id']} 命中 {len(matches)} 行（要求恰好 1 行）: {matches}")

        row = matches[0]
        diffs = []
        for col, (before, after) in item.get("field_changes", {}).items():
            if col not in idx:
                raise KeyError(f"修正列不存在: {col}")
            cell = ws.cell(row=row, column=idx[col])
            current = _text(cell.value)
            if current != _text(before):
                raise ValueError(
                    f"{item['correction_id']} 列 {col} before 不符: 当前 {current!r} != 凭据 {before!r}"
                )
            try:
                cell.value = float(after)
            except (TypeError, ValueError):
                cell.value = after
            diffs.append({"column": col, "before": before, "after": after})
        applied.append(
            {
                "correction_id": item["correction_id"],
                "excel_row": row,
                "approval_id": approval,
                "diffs": diffs,
            }
        )

    out.parent.mkdir(parents=True, exist_ok=True)
    wb.save(out)
    return {
        "period": period,
        "src": str(src),
        "out": str(out),
        "applied": applied,
    }
