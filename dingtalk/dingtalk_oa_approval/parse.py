# -*- coding: utf-8 -*-
"""账期窗口、表单解析、附件展开、文件名安全化。"""
from __future__ import annotations

import json
import re
from datetime import date, datetime, timedelta
from pathlib import Path

import pandas as pd


def ym(v) -> str:
    d = pd.to_datetime(v, errors="coerce")
    if pd.isna(d):
        return ""
    return f"{d.year:04d}-{d.month:02d}"


def submit_bucket_label(d) -> str:
    """发起日所在 4号~下月3号 桶 → 文件夹名 账期YYYYMMDD-YYYYMMDD。"""
    if d is None or pd.isna(d):
        return ""
    if isinstance(d, str):
        d = pd.to_datetime(d, errors="coerce")
        if pd.isna(d):
            return ""
    if d.day >= 4:
        start = date(d.year, d.month, 4)
    else:
        y, m = d.year, d.month - 1
        if m == 0:
            y, m = y - 1, 12
        start = date(y, m, 4)
    if start.month == 12:
        end = date(start.year + 1, 1, 3)
    else:
        end = date(start.year, start.month + 1, 3)
    return f"账期{start.strftime('%Y%m%d')}-{end.strftime('%Y%m%d')}"


def filename_period_month(name: str) -> str:
    """文件名里的结算日 → YYYY-MM。先匹配 20260708 / 2026-07-08，再匹配末尾 8.11。"""
    stem = Path(name or "").stem
    m = re.search(r"(20\d{2})[-._]?([01]?\d)[-._]?([0-3]?\d)", stem)
    if m:
        y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if 1 <= mo <= 12 and 1 <= d <= 31:
            return f"{y:04d}-{mo:02d}"
    m = re.search(r"(?:^|[-_])(\d{1,2})[.\-](\d{1,2})$", stem)
    if m:
        mo, d = int(m.group(1)), int(m.group(2))
        if 1 <= mo <= 12 and 1 <= d <= 31:
            return f"2026-{mo:02d}"
    return ""


def parse_amz_channel(name: str) -> dict | None:
    """AMZ 文件名 → brand/site/账期月。非 Amazon 前缀返回 None。"""
    stem = Path(name or "").stem
    stem = re.sub(r"\s+", "", stem)
    stem = re.sub(r"\(\d+\)$", "", stem)
    if not re.match(r"^AMZ", stem, re.I):
        return None
    body = re.sub(r"^AMZ[-_]?", "", stem, flags=re.I)
    fm = filename_period_month(stem)
    mdate = re.search(
        r"(20\d{2}[-._]?\d{1,2}[-._]?\d{1,2}|\d{1,2}[.\-]\d{1,2})$",
        body,
    )
    acct = body[: mdate.start()].rstrip("-_.") if mdate else body
    ms = re.search(
        r"(US|UK|DE|FR|IT|ES|CA|MX|BE|NL|SE|PL|AU|JP|IN|IE|AT)$",
        acct,
        re.I,
    )
    if ms:
        site = ms.group(1).upper()
        brand = acct[: ms.start()].rstrip("-_ ")
    else:
        site, brand = "", acct
    key = f"{brand}-{site}".strip("-").upper() if site else brand.upper()
    return {"brand": brand, "site": site, "channel": key, "period_month": fm, "date_raw": mdate.group(0) if mdate else ""}


def period_month_bucket(period_ym: str) -> str:
    """账期日期自然月 → DRM 风格桶名（该月4号~下月3号）。"""
    if not period_ym or len(period_ym) < 7:
        return ""
    y, m = int(period_ym[:4]), int(period_ym[5:7])
    start = date(y, m, 4)
    if m == 12:
        end = date(y + 1, 1, 3)
    else:
        end = date(y, m + 1, 3)
    return f"账期{start.strftime('%Y%m%d')}-{end.strftime('%Y%m%d')}"


def originator_from_title(title: str) -> str:
    title = (title or "").strip()
    m = re.match(r"^(.+?)的销售收款确认单$", title)
    return m.group(1) if m else title


def safe_filename(name: str) -> str:
    name = (name or "unnamed").strip() or "unnamed"
    name = re.sub(r'[\\/:*?"<>|]', "_", name)
    return name[:180]


def _maybe_json(v):
    if isinstance(v, (dict, list)):
        return v
    if isinstance(v, str) and v[:1] in "[{":
        try:
            return json.loads(v)
        except json.JSONDecodeError:
            return v
    return v


def parse_table_rows(form_values: list) -> list[dict]:
    rows = []
    for comp in form_values or []:
        if (comp.get("componentType") or "") != "TableField":
            continue
        raw = _maybe_json(comp.get("value"))
        if not isinstance(raw, list):
            continue
        for item in raw:
            if not isinstance(item, dict):
                continue
            rec = {}
            for cell in item.get("rowValue") or []:
                lab = str(cell.get("label") or "").strip()
                rec[lab] = cell.get("value")
            if rec:
                rows.append(rec)
    return rows


def collect_dd_attachments(form_values: list) -> list[dict]:
    found = []
    for comp in form_values or []:
        ctype = str(comp.get("componentType") or "")
        name = str(comp.get("name") or "")
        cid = str(comp.get("id") or "")
        val = _maybe_json(comp.get("value"))
        if ctype == "DDAttachment":
            items = val if isinstance(val, list) else []
            for it in items:
                if not isinstance(it, dict):
                    continue
                found.append(
                    {
                        "kind": "账期明细" if "明细" in name else name or "附件",
                        "component": name,
                        "component_id": cid,
                        "fileId": str(it.get("fileId") or ""),
                        "fileName": str(it.get("fileName") or ""),
                        "fileType": str(it.get("fileType") or ""),
                        "fileSize": it.get("fileSize"),
                        "spaceId": str(it.get("spaceId") or ""),
                    }
                )
        elif ctype == "DDPhotoField":
            urls = val if isinstance(val, list) else []
            for i, u in enumerate(urls):
                if not isinstance(u, str) or not u.startswith("http"):
                    continue
                found.append(
                    {
                        "kind": "图片",
                        "component": name,
                        "component_id": cid,
                        "fileId": "",
                        "fileName": Path(u.split("?")[0]).name or f"photo_{i}.png",
                        "fileType": "png",
                        "fileSize": None,
                        "spaceId": "",
                        "url": u,
                    }
                )
    return found


STATUS_CN = {
    "COMPLETED": "完成",
    "RUNNING": "审批中",
    "NEW": "审批中",
    "TERMINATED": "已撤销",
    "CANCELED": "已撤销",
    "CANCELLED": "已撤销",
    "完成": "完成",
    "审批中": "审批中",
    "已撤销": "已撤销",
    "已终止": "已撤销",
}
RESULT_CN = {
    "agree": "同意",
    "refuse": "拒绝",
    "同意": "同意",
    "拒绝": "拒绝",
}
PARSE_SUFFIXES = {".txt", ".csv", ".tsv", ".xlsx", ".xls", ".xlsm", ".xlsb", ".pdf"}
IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".heic", ".tif", ".tiff"}


def status_cn(status: str) -> str:
    s = (status or "").strip()
    return STATUS_CN.get(s, s)


def result_cn(result: str) -> str:
    s = (result or "").strip()
    return RESULT_CN.get(s, s)


def keep_approval(status: str, result: str) -> bool:
    """与钉钉导出口径一致：完成/审批中，且结果不是拒绝。已撤销/拒绝不下附件。"""
    st = status_cn(status)
    res = result_cn(result)
    return st in {"完成", "审批中"} and res != "拒绝"


def keep_attachment(att: dict) -> bool:
    """解析用：账期明细里的 txt/csv/excel/pdf；跳过图片控件和图片后缀。"""
    if (att.get("kind") or "") == "图片":
        return False
    name = str(att.get("fileName") or att.get("path") or "")
    suf = Path(name).suffix.lower()
    if suf in IMAGE_SUFFIXES:
        return False
    if suf and suf not in PARSE_SUFFIXES:
        return suf not in IMAGE_SUFFIXES
    return True


def instance_summary(inst: dict) -> dict:
    title = inst.get("title") or ""
    created = inst.get("createTime") or inst.get("create_time")
    form = inst.get("formComponentValues") or inst.get("form_component_values") or []
    table_rows = parse_table_rows(form)
    period_dates = sorted({str(r.get("账期日期") or "")[:10] for r in table_rows if r.get("账期日期")})
    platforms = sorted({str(r.get("选择平台") or "").strip() for r in table_rows if r.get("选择平台")})
    period_months = sorted({ym(d) for d in period_dates if ym(d)})
    should_buckets = sorted({period_month_bucket(m) for m in period_months if period_month_bucket(m)})
    created_ts = pd.to_datetime(created, errors="coerce", utc=True)
    if pd.notna(created_ts):
        created_local = created_ts.tz_convert("Asia/Shanghai").tz_localize(None)
    else:
        created_local = pd.NaT
    return {
        "processInstanceId": inst.get("processInstanceId") or inst.get("businessId"),
        "businessId": inst.get("businessId") or "",
        "title": title,
        "originator": originator_from_title(title),
        "originatorUserId": inst.get("originatorUserId") or "",
        "status": inst.get("status") or "",
        "result": inst.get("result") or "",
        "status_cn": status_cn(inst.get("status") or ""),
        "result_cn": result_cn(inst.get("result") or ""),
        "keep": keep_approval(inst.get("status") or "", inst.get("result") or ""),
        "createTime": str(created_local) if pd.notna(created_local) else str(created or ""),
        "submit_bucket": submit_bucket_label(created_local) if pd.notna(created_local) else "",
        "period_dates": period_dates,
        "period_months": period_months,
        "should_buckets": should_buckets,
        "platforms": platforms,
        "table_row_count": len(table_rows),
        "misplaced": bool(
            should_buckets
            and pd.notna(created_local)
            and submit_bucket_label(created_local) not in should_buckets
        ),
    }
