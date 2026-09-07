"""把 UPS / FedEx batch Record 收成统一 summary 行。"""

from __future__ import annotations

from typing import Any

import pandas as pd

from parcel_track.classify import (
    HANDLING_DAYS,
    TRANSIT_SEVERE_DAYS,
    _late_level,
    _to_ts,
    bizdays,
)
from parcel_track.classify import CLASS
from parcel_track.classify import _cat as _cat_shared

ACTION = {
    "missing_not_handed": "通知仓库/货代核查是否漏发或未交接",
    "fresh_no_pickup": "持续关注是否转漏发；与仓确认交接",
    "late_handover": "交接SLA复盘；对已延误买家提前告知",
    "carrier_slow": "记录；超过严重阈值→开承运商 trace/索赔",
    "fedex_slow": "记录；超过严重阈值→开FedEx trace/索赔",
    "stuck": "开承运商 trace；超14天→索赔+重发/退款",
    "cancelled": "确认取消原因，按需退款或重下",
    "not_found": "核查通途源数据；非本承运商改走对应渠道",
    "reused_no_label": "复用号旧票，以有建标那票为准",
    "delivered_ok": "—",
    "in_transit": "—",
    "parked": "v1 不查询；配 GLS 账号或 GOFO/VITE 跟踪后再纳入",
}
SHEET = {
    "missing_not_handed": "漏发未交接",
    "fresh_no_pickup": "漏发未交接",
    "late_handover": "迟发",
    "carrier_slow": "承运异常",
    "fedex_slow": "承运异常",
    "stuck": "承运异常",
    "cancelled": "取消·其他",
    "not_found": "取消·其他",
}


def ups_record_to_summaries(rec: Any) -> list[dict]:
    row = rec.to_summary_row()
    row["承运商"] = "ups"
    row["站点收件时间"] = row.get("实际发货时间") or ""
    row["交付时间"] = row.get("交付日期") or row.get("交付时间") or ""
    row["已取消"] = row.get("已取消") or ""
    return [row]


def fedex_record_to_summaries(rec: Any) -> list[dict]:
    rows = []
    for row in rec.to_summary_rows():
        row = dict(row)
        row["承运商"] = "fedex"
        rows.append(row)
    return rows


def classified_row(summary: dict, ident: dict, now, carrier: str) -> dict:
    n = summary.get("跟踪号") or ""
    dev = _to_ts(summary.get("交付时间") or summary.get("交付日期"))
    pu = _to_ts(summary.get("站点收件时间") or summary.get("实际发货时间"))
    label = _to_ts(summary.get("建标时间"))
    last_event = _to_ts(summary.get("最近节点时间"))
    ship = _to_ts(ident.get("发货日期"))
    cat_key = _cat_shared(dev, pu, label, ship, now, last_event=last_event)
    if str(summary.get("已取消") or "") == "是" and pd.isna(dev):
        cat_key = "cancelled"
    if summary.get("当前状态") == "查无此号":
        cat_key = "not_found"
    zh, en, _ = CLASS[cat_key]
    overdue = None
    bd = bizdays(label, pu)
    if bd is not None:
        overdue = bd - HANDLING_DAYS
    trans = None
    if not pd.isna(pu) and not pd.isna(dev):
        trans = bizdays(pu, dev)
    if cat_key == "late_handover":
        level = _late_level(overdue)
    elif cat_key == "carrier_slow":
        level = "严重延误" if (trans is not None and trans > TRANSIT_SEVERE_DAYS) else "承运延误"
    else:
        level = zh
    amazon = ""
    ch = (ident.get("渠道") or ident.get("销售站点") or "").lower()
    if overdue is not None and ("amazon" in ch or "amz" in ch):
        amazon = "是" if overdue > 0 else "否"
    elif overdue is not None:
        amazon = "否" if overdue <= 0 else ""
    caldays = ""
    try:
        if pu is not None and label is not None and str(pu) != "NaT" and str(label) != "NaT":
            caldays = int((pu - label).days)
    except Exception:
        caldays = ""
    return {
        "跟踪号": n,
        "承运商": carrier,
        "分类(EN)": en,
        "分类(中文)": zh,
        "等级": level,
        "订单号": ident.get("订单号", ""),
        "包裹号": ident.get("包裹号", ""),
        "渠道账号": ident.get("渠道账号", ""),
        "渠道": ident.get("渠道", ""),
        "平台SKU": ident.get("平台SKU", ""),
        "通途SKU": ident.get("通途SKU", ""),
        "产品名称": (ident.get("产品名称") or "")[:40],
        "发货仓库": ident.get("发货仓库", ""),
        "执行发货人": ident.get("执行发货人", ""),
        "是否补发货": ident.get("是否补发货", ""),
        "销售站点": ident.get("销售站点", ""),
        "买家姓名": ident.get("买家姓名", ""),
        "国家": ident.get("国家/地区", ""),
        "城市": ident.get("城市", ""),
        "省/州": ident.get("省/州", ""),
        "发货日期": ident.get("发货日期", ""),
        "建标时间": label,
        "站点收件时间": pu,
        "交付时间": dev,
        "日历延迟(天)": caldays,
        "营业日延迟(天)": overdue,
        "承运延迟(营业日)": trans,
        "Amazon是否判迟": amazon,
        "所属Sheet": SHEET.get(cat_key, ""),
        "建议动作": ACTION.get(cat_key, ""),
        "处理状态": "",
        "_key": cat_key,
    }
