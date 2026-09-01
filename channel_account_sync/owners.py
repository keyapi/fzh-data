# -*- coding: utf-8 -*-
"""Collapse monthly Sheet owner columns into change-only EN owner rows."""
from __future__ import annotations

import re

EMPTY_BEFORE_START = {"", "样品", "null"}
WRITE_AS_IS = {"待分配", "待定"}
MONTH_COL_RE = re.compile(r"^运营人员(\d{6})$")


def month_columns(header: list[str]) -> list[str]:
    cols = []
    for h in header or []:
        m = MONTH_COL_RE.match(h or "")
        if m:
            cols.append(h)
    return sorted(cols, key=lambda x: MONTH_COL_RE.match(x).group(1))


def _yms(rec: dict, month_cols: list[str] | None, months: list[str] | None) -> list[str]:
    raw = months if months is not None else month_cols
    if raw is None:
        raw = month_columns(list(rec.keys()))
    out = []
    for item in raw:
        m = MONTH_COL_RE.match(item or "")
        out.append(m.group(1) if m else item)
    return out


def norm_owner(raw: str) -> str:
    return re.sub(r"\s+", "", (raw or "").strip())


def month_value(rec: dict, ym: str) -> str:
    return (rec.get(f"运营人员{ym}") or "").strip()


def effective_owner(raw: str, had_owner: bool) -> str | None:
    """None = skip this month. Empty after go-live becomes 待分配."""
    val = (raw or "").strip()
    if val in WRITE_AS_IS:
        return val
    if val in EMPTY_BEFORE_START:
        if had_owner:
            return "待分配"
        return None
    return val


def collapsed_segments(
    rec: dict, month_cols: list[str] | None = None, months: list[str] | None = None
) -> list[dict]:
    segs: list[dict] = []
    had_owner = False
    prev = None
    for ym in _yms(rec, month_cols, months):
        raw = month_value(rec, ym)
        eff = effective_owner(raw, had_owner)
        if eff is None:
            continue
        had_owner = True
        if prev is None or eff != prev["owner"]:
            segs.append({"from_ym": ym, "from_date": f"{ym[:4]}-{ym[4:6]}-01", "owner": eff})
            prev = segs[-1]
    return segs


def en_last_owner(acc: dict) -> tuple[str | None, str | None]:
    dated = []
    for owner in acc.get("owners") or []:
        fd = str(owner.get("from_date") or "")[:10]
        if not fd:
            continue
        dated.append((fd, (owner.get("user") or "").strip()))
    if not dated:
        return None, None
    fd, user = max(dated, key=lambda x: x[0])
    return fd, user


def needed_for_existing(
    segs: list[dict], en_from: str | None, en_user: str | None
) -> list[dict]:
    """Only keep segments after EN's latest from_date whose owner actually changed."""
    if not en_from:
        return list(segs)
    last = norm_owner(en_user or "")
    out = []
    for seg in segs:
        if seg["from_date"] <= en_from:
            continue
        if norm_owner(seg["owner"]) == last:
            continue
        out.append(seg)
        last = norm_owner(seg["owner"])
    return out
