"""共享尾程异常分类（Amazon 营业日口径）。

从 fedex_track.ops_report 抽出。_cat 对慢在途返回 carrier_slow；
FedEx 旧报表把该 key 映射为 fedex_slow 以保持中文「FedEx延误」。
"""

from __future__ import annotations

import datetime as _dt
import re

import numpy as np
import pandas as pd

HANDLING_DAYS = 3
TRANSIT_SLOW_DAYS = 6
TRANSIT_SEVERE_DAYS = 12
STUCK_DAYS = 7
STUCK_SEVERE_DAYS = 14
MISSING_AFTER_DAYS = 3
US_HOLIDAYS = [
    "2026-01-01", "2026-01-19", "2026-02-16", "2026-05-25", "2026-06-19",
    "2026-07-03", "2026-09-07", "2026-10-12", "2026-11-11", "2026-11-26", "2026-12-25",
]
# GLS 起运/交接在波兰；12/24 Wigilia 自 2025 起法定。来源见 gls_track/ops_report.py。
PL_HOLIDAYS_2026 = [
    "2026-01-01", "2026-01-06", "2026-04-06", "2026-05-01", "2026-05-03",
    "2026-06-04", "2026-08-15", "2026-11-01", "2026-11-11",
    "2026-12-24", "2026-12-25", "2026-12-26",
]
GLS_HANDLING_DAYS = HANDLING_DAYS


def policy_for(carrier: str) -> tuple[int, list[str]]:
    """(handling_days, holidays)。处理天数 UPS/FedEx/GLS 均为 3；假日历仍按承运商。"""
    if (carrier or "").lower() == "gls":
        return GLS_HANDLING_DAYS, PL_HOLIDAYS_2026
    return HANDLING_DAYS, US_HOLIDAYS

CLASS = {
    "missing_not_handed": ("漏发/未交接", "not_handed", "red"),
    "fresh_no_pickup": ("建标未收件", "label_no_pickup", "yellow"),
    "late_handover": ("迟发", "late_handover", "orange"),
    "carrier_slow": ("承运延误", "carrier_slow", "orange"),
    "fedex_slow": ("FedEx延误", "fedex_slow", "orange"),
    "stuck": ("卡件", "stuck", "red"),
    "cancelled": ("已取消", "cancelled", "gray"),
    "not_found": ("数据异常/查无", "not_found", "gray"),
    "reused_no_label": ("复用旧票(缺建标)", "reused_no_label", "blue"),
    "delivered_ok": ("正常交付", "delivered_ok", "green"),
    "in_transit": ("在途", "in_transit", "yellow"),
    "parked": ("未支持/停放", "parked", "gray"),
}

TT_PICK = {
    "订单号": "订单号", "包裹号": "包裹号", "渠道账号": "渠道账号", "渠道": "渠道",
    "平台SKU": "平台SKU", "通途SKU": "通途SKU", "产品名称": "产品名称", "品类": "品类",
    "发货仓库": "发货仓库", "执行发货人": "执行发货人", "是否补发货": "是否补发货",
    "销售站点": "销售站点", "买家姓名": "买家姓名", "国家/地区": "国家/地区", "城市": "城市",
    "省/州": "省/州", "邮编": "邮编", "订单总售价": "订单总售价", "利润": "利润",
    "发货日期": "发货日期", "发货时间": "发货时间", "邮寄方式": "邮寄方式",
}


def bizdays(d1, d2, holidays=None):
    if pd.isna(d1) or pd.isna(d2):
        return None
    hols = US_HOLIDAYS if holidays is None else holidays
    try:
        return int(np.busday_count(np.datetime64(d1.date()), np.datetime64(d2.date()), holidays=hols))
    except Exception:
        return None


def _to_ts(v):
    try:
        return pd.to_datetime(v, errors="coerce")
    except Exception:
        return pd.NaT


def load_tt_identity(xlsx: str) -> dict[str, dict]:
    df = pd.read_excel(xlsx, sheet_name=0)
    tc = next(c for c in df.columns if "跟踪号" in str(c))
    num = df[tc].fillna("").astype(str).str.upper().str.replace(r"[-\s_]", "", regex=True)
    out: dict[str, dict] = {}
    for val, row in zip(num, df.to_dict("records")):
        if not val or val in out:
            continue
        ident = {}
        for k, src in TT_PICK.items():
            v = row.get(src)
            ident[k] = "" if pd.isna(v) else str(v).strip()
        out[val] = ident
    return out


def _bare_tracking(n: str) -> str:
    return re.sub(r"\[\d+\]$", "", str(n or "").strip())


def _late_level(overdue) -> str:
    if overdue is None:
        return "迟发"
    if overdue <= 0:
        return "准时"
    if overdue <= 2:
        return "轻度迟发"
    if overdue <= 5:
        return "中度迟发"
    return "重度迟发"


def _cat(dev, pu, label, ship, now, last_event=None, *, handling_days: int | None = None, holidays=None):
    """分类 key。迟发=建标→收件营业日；承运延误=收件→交付；卡件看最近扫描；延误优先于迟发。"""
    handling = HANDLING_DAYS if handling_days is None else handling_days
    if pu is pd.NaT:
        if dev is not pd.NaT:
            return "reused_no_label" if label is pd.NaT else "delivered_ok"
        if ship is not pd.NaT and (now - ship).days > MISSING_AFTER_DAYS:
            return "missing_not_handed"
        return "fresh_no_pickup"
    if label is pd.NaT:
        return "reused_no_label"

    late = False
    bd = bizdays(label, pu, holidays=holidays)
    if bd is not None and (bd - handling) > 0:
        late = True

    if dev is pd.NaT:
        scan = last_event if last_event is not pd.NaT and last_event is not None else label
        if scan is not pd.NaT and (now - scan).days > STUCK_DAYS:
            return "stuck"
        return "late_handover" if late else "in_transit"

    trans = bizdays(pu, dev, holidays=holidays)
    if trans is not None and trans > TRANSIT_SLOW_DAYS:
        return "carrier_slow"
    if late:
        return "late_handover"
    return "delivered_ok"


def classify_summary_row(r: dict, ident: dict, now: pd.Timestamp, *, slow_key: str = "carrier_slow") -> tuple[str, dict]:
    """summary 行 + 通途身份 → (cat_key, 报表行字典的分类字段)。"""
    n = str(r.get("跟踪号") or "")
    dev = _to_ts(r.get("交付时间") or r.get("交付日期"))
    pu = _to_ts(r.get("站点收件时间") or r.get("实际发货时间"))
    label = _to_ts(r.get("建标时间"))
    last_event = _to_ts(r.get("最近节点时间"))
    ship = pd.NaT
    remark = str(r.get("备注") or "")
    m = re.search(r"发货日期=([0-9-]+)", remark)
    if m:
        ship = pd.to_datetime(m.group(1), errors="coerce")
    if (ship is pd.NaT or pd.isna(ship)) and ident.get("发货日期"):
        ship = pd.to_datetime(ident.get("发货日期"), errors="coerce")
    cat_key = _cat(dev, pu, label, ship, now, last_event=last_event)
    cancelled = str(r.get("已取消") or "")
    if cancelled == "是" and dev is pd.NaT:
        cat_key = "cancelled"
    status = str(r.get("当前状态") or "")
    if status == "查无此号":
        cat_key = "not_found"
    if cat_key == "carrier_slow":
        cat_key = slow_key
    return cat_key, {
        "跟踪号": n,
        "建标时间": label,
        "站点收件时间": pu,
        "交付时间": dev,
        "发货日期": ship.date() if ship is not pd.NaT and not pd.isna(ship) else "",
        "ident": ident,
    }
